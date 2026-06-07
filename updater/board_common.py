"""
board_common.py — the logic shared by the autonomous sync, the manual updater,
and the mid-week add utility.

It owns the things they all must agree on:
  • loading the manual overlay (extra events/notices, expiry-aware)
  • merging bulletin + duty + manual into the signage.json the display reads
  • a content signature, so we only redeploy when the board would truly differ
plus the atomic file write and the summary emailer.

Manual-overlay items come out tagged  "_manual": true  so they can be told
apart from bulletin-derived ones. The display ignores the flag; the scripts use
it to reuse bulletin content (split_bulletin_manual) without re-calling the API.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import smtplib
from email.message import EmailMessage

import config


# ---------------------------------------------------------------------------
# Manual overlay
# ---------------------------------------------------------------------------
def load_manual_overlay(
    today: dt.date | None = None,
) -> tuple[list[dict], list[dict]]:
    """Read manual.json → (events, announcements), dropping anything whose
    `expires` (YYYY-MM-DD) is in the past. Missing/blank/broken file → empties,
    never an exception (a typo in a hand-edited file shouldn't break the board)."""
    today = today or dt.date.today()
    try:
        data = json.loads(config.MANUAL_OVERLAY.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return [], []

    def live(items: list[dict] | None) -> list[dict]:
        kept = []
        for it in items or []:
            exp = it.get("expires")
            if exp:
                try:
                    if dt.date.fromisoformat(exp) < today:
                        continue  # expired — drop it
                except ValueError:
                    pass          # unparseable date → keep it, don't crash
            kept.append(it)
        return kept

    return live(data.get("events")), live(data.get("announcements"))


def _tag_manual(items: list[dict]) -> list[dict]:
    """Return copies tagged so the output can distinguish manual from bulletin."""
    return [{**it, "_manual": True} for it in items]


def split_bulletin_manual(
    items: list[dict] | None,
) -> tuple[list[dict], list[dict]]:
    """Split a live events/announcements list into (bulletin, manual). Lets the
    scripts reuse the bulletin content already on the board without the API."""
    bulletin, manual = [], []
    for it in items or []:
        (manual if it.get("_manual") else bulletin).append(it)
    return bulletin, manual


# ---------------------------------------------------------------------------
# Merge + change detection
# ---------------------------------------------------------------------------
def merge_signage(
    *,
    week_of: str | None,
    bulletin_events: list[dict],
    bulletin_notices: list[dict],
    duty_assignments: list[dict],
    duty_week_label: str | None,
    manual_events: list[dict],
    manual_announcements: list[dict],
    source_meta: dict | None,
    theme_override: str | None = None,
) -> dict:
    """Assemble the signage.json the display consumes. Bulletin content first,
    manual overlay appended and tagged. `source_meta` carries the nightly job's
    'what did we process' state into diagnostics (the display ignores it)."""
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "week_of": week_of,
        "theme_override": theme_override,
        "events": list(bulletin_events) + _tag_manual(manual_events),
        "yard_duty": {
            "week_label": duty_week_label,
            "assignments": list(duty_assignments),
        },
        "announcements": list(bulletin_notices) + _tag_manual(manual_announcements),
        "diagnostics": dict(source_meta or {}),
    }


def content_signature(signage: dict | None) -> str:
    """Hash of the *displayed* content only — everything except the timestamp and
    diagnostics — so we can tell whether the board would actually look different."""
    meaningful = {
        k: v for k, v in (signage or {}).items()
        if k not in ("generated_at", "diagnostics")
    }
    blob = json.dumps(meaningful, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def write_signage(payload: dict) -> None:
    """Write signage.json atomically (temp file + replace), keeping one
    timestamped backup of whatever was there before."""
    target = config.SIGNAGE_JSON
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(target, target.with_name(f"signage.{stamp}.bak.json"))
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def send_email(subject: str, body: str) -> None:
    """Send a plain-text summary via Gmail SMTP. BEST-EFFORT: a missing address
    or a rejected credential prints a note and returns instead of raising, so a
    notification problem can NEVER crash the run or block the deploy. The board
    going live matters; the heads-up email does not."""
    recipients = [a.strip() for a in (config.MAIL_TO or "").split(",") if a.strip()]
    if not (config.SMTP_USER and config.SMTP_PASSWORD and recipients):
        print("  (email not configured — skipping send)")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        print(f"  emailed: {', '.join(recipients)}")
    except Exception as exc:
        print(f"  (email send failed, continuing anyway: {type(exc).__name__}: {exc})")
