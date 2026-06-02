"""
bulletin.py — Turn the weekly .docx into clean, structured events.
==================================================================

Flow:
  1. Pull plain text out of the .docx (python-docx) — paragraphs AND tables.
  2. Hand it to sanitize.py so student data is stripped.
  3. Send ONLY the sanitized text to the API and ask for strict JSON events.

The API is good at the messy-human part ("WOW Celebrations Wednesday in MU Room
TK-4th @ 8:30am 5th-8th @ 9:30am") that regex is bad at. We give it the week the
bulletin covers so it can resolve "Wednesday" into a real date.

Everything here fails soft: no key / no network / bad response → empty event
list plus a warning, never a crash.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass

import config
import sanitize


@dataclass
class BulletinResult:
    events: list[dict]            # normalized event dicts (see schema below)
    week_of: str | None           # ISO date string for the Monday of the week
    sanitize_summary: str         # PII-free description of what was stripped
    warning: str | None = None


# The event schema we ask the model to fill. Keeping it here documents the
# contract the display depends on:
#   title     short label              ("WOW Celebration TK–4")
#   date      "YYYY-MM-DD" or null      (null when truly undated)
#   day       weekday name or null      ("Wednesday")
#   start     "HH:MM" 24h or null
#   end       "HH:MM" 24h or null
#   location  room/place or null        ("MU Room")
#   category  one of CATEGORIES         (drives icon/color on the board)
#   audience  who it's for or null      ("TK-4th", "Classified staff")
CATEGORIES = ["celebration", "meeting", "deadline", "trip", "food", "sports", "general"]


def extract_text(docx_path: str) -> str:
    """
    Read a .docx into plain text, including tables (the yard-duty grid is a
    table, and so are some announcements). python-docx exposes paragraphs and
    tables separately, so we walk both.
    """
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise RuntimeError("python-docx not installed — run pip install python-docx") from exc

    document = docx.Document(docx_path)
    chunks: list[str] = []

    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            chunks.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            line = " | ".join(c for c in cells if c)
            if line:
                chunks.append(line)

    return "\n".join(chunks)


def week_of_from_filename(docx_path: str, fallback: dt.date | None = None) -> dt.date:
    """
    The files are named like "Week of June 1.docx", so the date is right there.
    Parse it; fall back to (this) Monday if the name doesn't cooperate.
    """
    fallback = fallback or _monday_of(dt.date.today())
    name = re.sub(r"\.docx$", "", docx_path.split("/")[-1], flags=re.IGNORECASE)

    m = re.search(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{1,2})",
        name,
        re.IGNORECASE,
    )
    if not m:
        return fallback

    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    month = months[m.group(1).lower()[:3]]
    day = int(m.group(2))
    year = dt.date.today().year
    try:
        return dt.date(year, month, day)
    except ValueError:
        return fallback


def _monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _build_prompt(safe_text: str, week_start: dt.date) -> str:
    """The extraction instructions. We pin the week so days resolve to dates."""
    week_end = week_start + dt.timedelta(days=6)
    return f"""You are extracting calendar events from a school staff bulletin so they
can be shown on a lobby display. The bulletin covers the week of
{week_start:%A, %B %-d, %Y} through {week_end:%A, %B %-d, %Y}.

Return ONLY a JSON array — no prose, no markdown fences. Each element:
{{
  "title": "short human label, max ~6 words",
  "date": "YYYY-MM-DD or null",
  "day": "weekday name or null",
  "start": "HH:MM 24-hour or null",
  "end": "HH:MM 24-hour or null",
  "location": "room or place, or null",
  "category": one of {CATEGORIES},
  "audience": "who it's for, or null"
}}

Rules:
- Resolve weekday names to real dates using the week above. Dates with an
  explicit month/day (e.g. "June 9") may fall outside that week — keep them.
- Split one line into multiple events when it clearly lists several (e.g. an
  event with different times for different grades → one event per grade).
- Skip pure instructions, policies, and material-prep notes — only real
  dated/scheduled happenings.
- Skip anything that is just a hyperlink or a form.
- If a time is a range like "11:00-12:30", fill both start and end.
- Be conservative with category; use "general" when unsure.

BULLETIN TEXT:
\"\"\"
{safe_text}
\"\"\"
"""


def _coerce_events(raw: str) -> list[dict]:
    """Parse the model's reply into a list of dicts, tolerating stray fences."""
    cleaned = raw.strip()
    # Strip ```json … ``` if the model added them despite instructions.
    cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of events")

    # Light validation/normalization so the display never sees surprises.
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        category = item.get("category")
        if category not in CATEGORIES:
            category = "general"
        out.append(
            {
                "title": str(item["title"]).strip(),
                "date": item.get("date"),
                "day": item.get("day"),
                "start": item.get("start"),
                "end": item.get("end"),
                "location": item.get("location"),
                "category": category,
                "audience": item.get("audience"),
            }
        )
    return out


def parse(docx_path: str) -> BulletinResult:
    """Main entry point. Extract → sanitize → (confirm) → API → events."""
    week_start = week_of_from_filename(docx_path)

    raw_text = extract_text(docx_path)
    safe_text, report = sanitize.sanitize_bulletin_text(raw_text)
    summary = report.summary()

    # The human confirmation gate. This is the real guarantee.
    if config.REQUIRE_SEND_CONFIRMATION:
        ok = _confirm_send(safe_text)
        if not ok:
            return BulletinResult([], week_start.isoformat(), summary,
                                  "send not confirmed — skipped API event extraction")

    if not config.ANTHROPIC_API_KEY:
        return BulletinResult([], week_start.isoformat(), summary,
                              "no ANTHROPIC_API_KEY — skipped event extraction")

    try:
        import anthropic
    except ImportError:
        return BulletinResult([], week_start.isoformat(), summary,
                              "anthropic SDK not installed — skipped event extraction")

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": _build_prompt(safe_text, week_start)}],
        )
        reply = "".join(block.text for block in message.content if block.type == "text")
        events = _coerce_events(reply)
    except Exception as exc:
        return BulletinResult([], week_start.isoformat(), summary,
                              f"event extraction failed ({exc})")

    return BulletinResult(events, week_start.isoformat(), summary)


def _confirm_send(safe_text: str) -> bool:
    """
    Show EXACTLY what will be sent to the API and require an explicit yes.
    Also surface any lingering roster-pattern warnings in the clear.
    """
    print("\n" + "=" * 70)
    print("ABOUT TO SEND THIS TEXT TO THE API. Student data should NOT appear.")
    print("=" * 70)
    print(safe_text if safe_text else "(empty)")
    print("=" * 70)

    warnings = sanitize.looks_clean(safe_text)
    if warnings:
        print("\n⚠️  HEADS UP — these lines still look roster-ish:")
        for w in warnings:
            print(f"   • {w}")
        print("   Review above. If you see student names, type anything but 'yes'.\n")

    answer = input('Send this to the API? Type "yes" to proceed: ').strip().lower()
    return answer == "yes"
