#!/usr/bin/env python3.12
"""
sync_bulletin.py — the autonomous nightly board update.
=======================================================

Runs unattended (GitHub Actions, overnight). Each run:

  1. Reads the LIVE board to see what's currently showing. Its diagnostics carry
     the last-processed state (file id + content hash), so there's no separate
     state file to keep in sync and the job never commits to the repo.
  2. Lists the Shared Drive bulletin folder and picks the right week BY DATE: a
     file may go live only once today is within BULLETIN_LEAD_DAYS of its week.
     The current week therefore holds until the Saturday before the next one.
  3. If that file is new, or its text changed since last time, it re-extracts it
     (same sanitize + API as the manual updater). Otherwise it REUSES the
     bulletin content already on the board — no API call, no cost.
  4. Re-reads duty + the manual overlay, merges, and — only if the result would
     actually look different — writes signage.json and signals a deploy.
  5. Emails a summary on a new week or a mid-week edit, and on failure.

THE SAFETY GATE
---------------
With nobody at the keyboard, the sanitizer is the guard against student data
reaching the API. If it can't find a stop-marker (so it can't confirm the
roster was cut), OR its final paranoid pass still smells a roster, this ABORTS
the send, leaves the board untouched, and emails Jason to process that week by
hand. Normal weeks stay fully autonomous.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import sys
import traceback

import requests

import board_common as bc
import bulletin
import config
import sanitize
import yard_duty


def _monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _set_output(name: str, value: str) -> None:
    """Expose a value to the GitHub Actions workflow (for the conditional deploy)."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def fetch_live_signage() -> dict | None:
    """What's on the board right now — or None if we can't read it (first run,
    or a transient network blip). A cache-buster avoids a stale CDN copy."""
    try:
        url = f"{config.LIVE_SIGNAGE_URL}?t={int(dt.datetime.now().timestamp())}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"  (couldn't read the live board — treating as first run: {exc})")
        return None


def pick_current_file(
    files: list[dict], today: dt.date
) -> tuple[dict | None, list[str], int]:
    """Date-gate. Among the folder's Docs, choose the one whose week has started
    (within the lead window) and is the most recent. The week comes from the
    Doc's title. Returns (file, notes-for-the-log, how-many-had-a-readable-date)."""
    notes: list[str] = []
    eligible: list[tuple[dt.date, dict]] = []
    n_parseable = 0
    for f in files:
        week = bulletin._week_from_string(f.get("name"), numeric_ok=True)
        if not week:
            notes.append(f"skipped (no week date in title): {f.get('name')!r}")
            continue
        n_parseable += 1
        monday = _monday_of(week)
        promote_on = monday - dt.timedelta(days=config.BULLETIN_LEAD_DAYS)
        if promote_on <= today:
            eligible.append((monday, f))
        else:
            notes.append(f"not yet (promotes {promote_on:%b %d}): {f.get('name')!r}")
    if not eligible:
        return None, notes, n_parseable
    eligible.sort(key=lambda t: t[0])      # by the week's Monday, ascending
    return eligible[-1][1], notes, n_parseable           # most recent eligible week wins


def _event_lines(events: list[dict]) -> str:
    if not events:
        return "  (none)"
    out = []
    for e in events:
        when = e.get("date") or "—"
        t = e.get("start") or ""
        loc = f" @ {e['location']}" if e.get("location") else ""
        tag = " [manual]" if e.get("_manual") else ""
        out.append(f"  • {when} {t}  {e.get('title', '')}{loc}{tag}".rstrip())
    return "\n".join(out)


def _notice_lines(notices: list[dict]) -> str:
    if not notices:
        return "  (none)"
    return "\n".join(
        f"  • {a.get('text', '')}{' [manual]' if a.get('_manual') else ''}"
        for a in notices
    )


def main() -> int:
    today = dt.date.today()
    print(f"sync_bulletin — {dt.datetime.now().isoformat(timespec='seconds')}")

    try:
        # ---- what's showing now (and the state we stored last time) ----------
        live = fetch_live_signage()
        last = ((live or {}).get("diagnostics", {}) or {}).get("source", {}) or {}
        live_events, _ = bc.split_bulletin_manual((live or {}).get("events"))
        live_notices, _ = bc.split_bulletin_manual((live or {}).get("announcements"))

        # ---- 1) which file should be showing today? -------------------------
        files = bulletin.list_drive_folder_docs(config.BULLETIN_FOLDER_ID)
        print(f"  folder: {len(files)} file(s) found")
        for f in files:
            mt = f.get("mimeType", "")
            kind = ("Google Doc" if mt == bulletin.GDOC_MIME
                    else "Word" if mt == bulletin.WORD_MIME else mt)
            print(f"    - {f.get('name')!r}  [{kind}]")
        current, notes, n_parseable = pick_current_file(files, today)
        for n in notes:
            print(f"  {n}")
        if not current:
            if files and n_parseable == 0:
                # Files exist but none have a readable date — a naming problem,
                # worth flagging so the board doesn't silently go stale.
                print("  Found bulletins but none have a readable week date in the title.")
                bc.send_email(
                    "SOAR board: bulletin titles need a date",
                    f"The nightly job found {len(files)} file(s) in the bulletin folder "
                    "but couldn't read a week date from any of their titles, so it can't "
                    "tell which week to show.\n\n"
                    'Name them with the week date — e.g. "Week of May 4" (a written '
                    'month is most reliable; "5/4" also works).\n\nFiles seen:\n'
                    + "\n".join(f"  • {f.get('name')}" for f in files),
                )
            else:
                print("  No bulletin is in its window yet — nothing to show. Done.")
            _set_output("changed", "false")
            return 0
        print(f"  current file: {current['name']} ({current['id']})")

        # ---- 2) has the bulletin changed since we last built the board? -----
        text = bulletin.fetch_drive_file_text(current)
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        new_file = current["id"] != last.get("file_id")
        bulletin_changed = new_file or content_hash != last.get("content_hash")
        week_start = bulletin._week_from_string(current["name"], numeric_ok=True) or _monday_of(today)

        sanitize_summary = "(bulletin unchanged — reused)"
        bulletin_warning: str | None = None

        if bulletin_changed:
            print("  bulletin is new/edited — sanitizing + extracting.")
            safe_text, report = sanitize.sanitize_bulletin_text(text)
            sanitize_summary = report.summary()

            # THE FAIL-SAFE — the student-data guard, with no human to back it up.
            problems = []
            if report.cut_marker is None:
                problems.append("no stop-marker found (couldn't confirm the roster was cut)")
            residual = sanitize.looks_clean(safe_text)
            if residual:
                problems.append(f"{len(residual)} line(s) still look roster-like")
            if problems:
                reason = "; ".join(problems)
                print(f"  ✗ FAIL-SAFE held back the send: {reason}")
                bc.send_email(
                    "SOAR board: this week's bulletin needs manual processing",
                    "The nightly job would NOT auto-send this week's bulletin to the "
                    "API because the student-data guard wasn't satisfied:\n\n"
                    f"  {reason}\n\n"
                    f"File: {current['name']}\n\n"
                    "Nothing on the board was changed. Please process this week by hand:\n\n"
                    "  cd ~/Projects/soar-signage/updater\n"
                    "  python3.12 update_signage.py\n\n"
                    "Pick this Doc from the menu; you'll see the sanitized text and can "
                    "approve it before anything is sent.",
                )
                _set_output("changed", "false")
                return 0

            events, notices, bulletin_warning = bulletin.extract_events_notices(
                safe_text, week_start
            )

            # A failed/empty extraction must NOT blank a working board.
            if bulletin_warning and not events:
                print(f"  ✗ extraction problem, board left as-is: {bulletin_warning}")
                bc.send_email(
                    "SOAR board: couldn't read this week's bulletin",
                    "The nightly job couldn't extract events from this week's bulletin, "
                    "so the board was left unchanged:\n\n"
                    f"  {bulletin_warning}\n\n"
                    f"File: {current['name']}\n\n"
                    "It will retry tomorrow night. To push it now, run the updater by hand:\n"
                    "  cd ~/Projects/soar-signage/updater && python3.12 update_signage.py",
                )
                _set_output("changed", "false")
                return 0
        else:
            print("  bulletin unchanged — reusing what's on the board.")
            events, notices = live_events, live_notices

        # ---- 3) duty + manual overlay (fresh every run) ---------------------
        duty = yard_duty.fetch_current()
        if duty.warning:
            print(f"  duty note: {duty.warning}")
        manual_events, manual_announcements = bc.load_manual_overlay(today)

        # ---- 4) merge, then deploy only if the board would truly differ -----
        payload = bc.merge_signage(
            week_of=week_start.isoformat(),
            bulletin_events=events,
            bulletin_notices=notices,
            duty_assignments=[
                {"post": a.post, "name": a.name, "time": a.time,
                 "where": a.where, "part": a.part}
                for a in duty.assignments
            ],
            duty_week_label=duty.week_label,
            manual_events=manual_events,
            manual_announcements=manual_announcements,
            source_meta={
                "source": {
                    "file_id": current["id"],
                    "file_name": current["name"],
                    "content_hash": content_hash,
                },
                "sanitize": sanitize_summary,
                "bulletin_warning": bulletin_warning,
                "yard_duty_warning": duty.warning,
                "synced_by": "nightly",
            },
            theme_override=config.THEME_OVERRIDE,
        )

        if live is not None and bc.content_signature(payload) == bc.content_signature(live):
            print("  No visible change — leaving the board as-is. Done.")
            _set_output("changed", "false")
            return 0

        bc.write_signage(payload)
        _set_output("changed", "true")
        print("  signage.json written — deploy will follow.")

        # ---- 5) tell Jason what's now up ------------------------------------
        subject = (
            f"SOAR board: now showing week of {week_start:%b %-d}"
            if new_file else
            f"SOAR board updated ({week_start:%b %-d} bulletin edited)"
        )
        body = (
            f"{'New week promoted.' if new_file else 'Mid-week edit picked up.'}\n\n"
            f"Week of: {week_start:%A, %B %-d, %Y}\n"
            f"Source:  {current['name']}\n\n"
            f"EVENTS:\n{_event_lines(payload['events'])}\n\n"
            f"TICKER NOTICES:\n{_notice_lines(payload['announcements'])}\n\n"
            f"ON DUTY: {len(duty.assignments)} assignment(s)"
            f"{(' — ' + duty.week_label) if duty.week_label else ''}\n\n"
            f"Sanitize: {sanitize_summary}\n\n"
            "Need to add or fix something mid-week? Run:\n"
            "  cd ~/Projects/soar-signage/updater && python3.12 add_to_board.py"
        )
        bc.send_email(subject, body)
        return 0

    except Exception:
        tb = traceback.format_exc()
        print(tb)
        try:
            bc.send_email(
                "SOAR board: nightly sync FAILED",
                "The nightly signage sync hit an error and did NOT update the board:\n\n"
                + tb,
            )
        except Exception:
            pass
        _set_output("changed", "false")
        return 1


if __name__ == "__main__":
    sys.exit(main())
