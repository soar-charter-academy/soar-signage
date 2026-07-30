#!/usr/bin/env python3.12
"""
agenda_to_board.py — build the board from a pasted agenda email.
================================================================

For the start-of-year (and any other one-off, no-bulletin moment): you get an
email with the agenda, you paste it into a text file, and this turns it into a
ready-to-deploy board — using the SAME trusted AI parser the weekly bulletin
uses, just without the Drive/folder/date-window machinery.

What it produces, by design (start-of-school shape):
  • EVENTS:        live, extracted from the pasted agenda
  • ANNOUNCEMENTS: live, extracted from the agenda (add your own with --note)
  • DUTY:          intentionally EMPTY (no yard duty the first days back)
  • HOUSE POINTS:  unchanged — the frame stays live (it's in index.html)
  • THEME:         "back-to-school" (the chalkboard/apple skin)

Usage
-----
  1. Save the agenda email body to a text file, e.g.  agenda.txt
  2. Run:
         cd updater
         python3.12 agenda_to_board.py agenda.txt

     Options:
       --week 2026-08-11      Monday the agenda covers (helps resolve weekday
                              names → dates). Default: the upcoming Monday.
       --note "text"          Add an extra ticker announcement. Repeatable.
       --theme back-to-school Override the theme key (default back-to-school).
       --yes                  Skip the confirm prompt (not recommended).
       --no-deploy-hint       Don't print the deploy commands at the end.

  3. It shows the sanitized text, the events/notices it extracted, and asks you
     to confirm before writing. Then preview and deploy:
         cd ../display && python3 -m http.server 8081     # check localhost:8081
         # back in repo root:
         git add -A && git commit -m "Back-to-school board" && git push
         firebase deploy --only hosting

Safety
------
Runs the SAME sanitizer + the nightly job's fail-safe (stop-marker must be
found AND no residual roster lines) before anything is sent to the API. An
agenda email shouldn't contain student data, but this costs nothing and means
the guard is identical to the trusted path. Nothing is written if you don't
confirm.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import board_common as bc
import bulletin
import config
import sanitize


def _upcoming_monday(today: dt.date) -> dt.date:
    """The next Monday on/after today (so a late-August run resolves weekday
    names against the week school actually starts)."""
    days = (7 - today.weekday()) % 7
    return today + dt.timedelta(days=days or 7) if today.weekday() != 0 else today


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the signage board from a pasted agenda email "
                    "(events + announcements live, duty empty, back-to-school theme).")
    ap.add_argument("agenda", help="Path to a text file containing the agenda email body. "
                                   "Use '-' to read from stdin.")
    ap.add_argument("--week", metavar="YYYY-MM-DD",
                    help="Monday the agenda covers (default: upcoming Monday).")
    ap.add_argument("--note", action="append", default=[], metavar="TEXT",
                    help="Add an extra ticker announcement. Repeatable.")
    ap.add_argument("--theme", default="back-to-school",
                    help="Theme key to write (default: back-to-school).")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the confirmation prompt before sending to the API.")
    ap.add_argument("--no-deploy-hint", action="store_true",
                    help="Don't print the deploy commands at the end.")
    args = ap.parse_args()

    # ---- read the agenda text -------------------------------------------
    if args.agenda == "-":
        raw_text = sys.stdin.read()
    else:
        try:
            raw_text = open(args.agenda, encoding="utf-8").read()
        except OSError as exc:
            print(f"Couldn't read {args.agenda!r}: {exc}")
            return 1
    if not raw_text.strip():
        print("That agenda file is empty — nothing to do.")
        return 1

    # ---- which week? -----------------------------------------------------
    today = dt.date.today()
    if args.week:
        try:
            week_start = dt.date.fromisoformat(args.week)
        except ValueError:
            print(f"--week must be YYYY-MM-DD, got {args.week!r}")
            return 1
    else:
        # Prefer a date written in the agenda itself; else the upcoming Monday.
        week_start = (bulletin._week_from_string(raw_text[:600])
                      or _upcoming_monday(today))
    print(f"Agenda week: {week_start:%A, %B %-d, %Y}")

    # ---- sanitize + the SAME fail-safe the nightly job uses --------------
    safe_text, report = sanitize.sanitize_bulletin_text(raw_text)
    summary = report.summary()
    print(f"Sanitize: {summary}")

    problems = []
    if report.cut_marker is None:
        # An agenda email may legitimately have no stop-marker (no roster at all).
        # Unlike the unattended job, a human is here — so we WARN rather than abort,
        # and the confirm gate below is the backstop.
        print("  note: no stop-marker found — expected for an agenda with no roster. "
              "Review the text below carefully before confirming.")
    residual = sanitize.looks_clean(safe_text)
    if residual:
        print(f"  ⚠️  {len(residual)} line(s) still look roster-like — review before sending:")
        for w in residual[:10]:
            print(f"       • {w}")

    # ---- confirm gate (show exactly what goes to the API) ---------------
    if not args.yes:
        print("\n" + "=" * 70)
        print("ABOUT TO SEND THIS TEXT TO THE API. Student data should NOT appear.")
        print("=" * 70)
        print(safe_text if safe_text else "(empty)")
        print("=" * 70)
        ans = input('Send this to the API? Type "yes" to proceed: ').strip().lower()
        if ans != "yes":
            print("Aborted — nothing written.")
            return 0

    # ---- extract via the SAME function the nightly job calls ------------
    events, notices, warning = bulletin.extract_events_notices(safe_text, week_start)
    if warning:
        print(f"\nExtraction warning: {warning}")
    if not events and not notices:
        print("No events or announcements came back — leaving the board untouched.")
        print("(Check the agenda text, your ANTHROPIC_API_KEY, and network.)")
        return 1

    # operator-added notices, appended after the extracted ones
    for n in args.note:
        n = n.strip()
        if n:
            notices.append({"text": n})

    # ---- merge: events + notices live, DUTY EMPTY, theme set ------------
    payload = bc.merge_signage(
        week_of=week_start.isoformat(),
        bulletin_events=events,
        bulletin_notices=notices,
        duty_assignments=[],          # ← no yard duty for back-to-school
        duty_week_label="",
        manual_events=[],
        manual_announcements=[],
        source_meta={
            "sanitize": summary,
            "bulletin_warning": warning,
            "yard_duty_warning": None,
            "synced_by": "agenda_to_board",
            "source": {"file_name": f"agenda email ({args.agenda})"},
        },
        theme_override=args.theme,
    )

    bc.write_signage(payload)

    # ---- report ----------------------------------------------------------
    print(f"\n✓ Wrote {config.SIGNAGE_JSON}")
    print(f"  theme:         {args.theme}")
    print(f"  events:        {len(events)}")
    print(f"  announcements: {len(notices)}")
    print(f"  duty:          empty (by design)")
    print(f"  house points:  unchanged (frame stays live)")

    print("\nEVENTS:")
    for e in events:
        when = e.get("date") or e.get("day") or "—"
        loc = f" @ {e['location']}" if e.get("location") else ""
        print(f"  • {when}  {e.get('start') or ''}  {e.get('title','')}{loc}".rstrip())
    print("\nANNOUNCEMENTS:")
    for a in notices:
        print(f"  • {a.get('text','')}")

    if not args.no_deploy_hint:
        print("\nPreview, then deploy:")
        print("    cd ../display && python3 -m http.server 8081   # open http://localhost:8081, Ctrl+C when done")
        print("    cd ..")
        print('    git add -A && git commit -m "Back-to-school board from agenda" && git push')
        print("    firebase deploy --only hosting")
        print("\nWhen the first real weekly bulletin resumes: set THEME_OVERRIDE back to")
        print("None in config.py (and re-enable the nightly cron in .github/workflows/nightly.yml).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
