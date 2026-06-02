"""
yard_duty.py — Read "who is on duty this week" from the Google Sheet.
=====================================================================

The bulletin only defines the posts; the people are in the Sheet. This module
finds the right tab, locates the week-block whose date range contains today,
and reads the post→name pairs out of it.

It is deliberately FORGIVING. The Sheet is a living human document, so anything
that goes wrong here (bad creds, layout drift, no current week) returns an empty
list plus a clear warning rather than crashing the whole update. A missing
yard-duty panel is a small problem; a crashed updater on a Monday morning is a
big one.

Layout assumptions live in config.py (section 4) so you can retune offsets
without touching this logic.

Dependencies: `gspread` + `google-auth` (see requirements.txt). If they're not
installed, we say so and return empty.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

import config


@dataclass
class DutyAssignment:
    """One person on one post, with the stable time/location joined in."""

    post: str
    name: str
    time: str
    where: str
    part: str  # "am" | "mid" | "pm" — lets the display group the board


@dataclass
class DutyResult:
    assignments: list[DutyAssignment]
    week_label: str | None        # e.g. "Week 3 (May 18th - 22nd)" for display
    warning: str | None = None    # human-readable problem, if any


# Month name → number, covering the abbreviations the office tends to use.
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches a week header like "Week 1 (May 4th - 8th)" and grabs the date part.
_WEEK_HEADER = re.compile(r"week\s*\d+\s*\((?P<dates>[^)]*)\)", re.IGNORECASE)

# Pulls "<month> <day>" pairs out of a date range. Month is optional on the
# second date ("May 4th - 8th"), so we carry the last-seen month forward.
_DATE_TOKEN = re.compile(
    r"(?:(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec)\w*\s*)?"
    r"(?P<day>\d{1,2})",
    re.IGNORECASE,
)


def _assume_year() -> int:
    return config.YARD_DUTY_ASSUME_YEAR or dt.date.today().year


def _parse_date_range(date_text: str) -> tuple[dt.date, dt.date] | None:
    """
    Turn "May 4th - 8th" or "May 28th - June 1st" into (start, end) dates.

    Returns None if we can't make sense of it (caller treats that as "skip
    this block" rather than guessing).
    """
    year = _assume_year()
    tokens = list(_DATE_TOKEN.finditer(date_text))
    if len(tokens) < 2:
        return None

    last_month: int | None = None
    parsed: list[dt.date] = []
    for tok in tokens:
        mon_raw = tok.group("mon")
        if mon_raw:
            last_month = _MONTHS.get(mon_raw.lower()[:4]) or _MONTHS.get(
                mon_raw.lower()[:3]
            )
        if last_month is None:
            return None  # a day with no month context — give up cleanly
        day = int(tok.group("day"))
        try:
            parsed.append(dt.date(year, last_month, day))
        except ValueError:
            return None  # e.g. day 32 — malformed, skip

    start, end = parsed[0], parsed[-1]
    # Handle a range that crosses New Year (start in Dec, end in Jan).
    if end < start:
        end = end.replace(year=end.year + 1)
    return start, end


def _target_worksheets(spreadsheet):
    """Pick which tab(s) to scan, honoring the override in config."""
    if config.YARD_DUTY_TAB_OVERRIDE:
        try:
            return [spreadsheet.worksheet(config.YARD_DUTY_TAB_OVERRIDE)]
        except Exception:
            return []  # named override missing; caller will warn

    pattern = re.compile(config.YARD_DUTY_TAB_PATTERN)
    return [ws for ws in spreadsheet.worksheets() if pattern.match(ws.title)]


def _read_block(grid: list[list[str]], label_col: int) -> tuple[str | None, list[tuple[str, str]]]:
    """
    Read one week-block starting at `label_col`. Returns (week_label, pairs)
    where pairs is a list of (post_label, name). Stops at the first blank label.
    """
    header_row = config.YARD_DUTY_HEADER_ROW
    name_col = label_col + config.YARD_DUTY_NAME_COL_OFFSET

    def cell(r: int, c: int) -> str:
        if r < len(grid) and c < len(grid[r]):
            return (grid[r][c] or "").strip()
        return ""

    week_label = cell(header_row, label_col) or None

    pairs: list[tuple[str, str]] = []
    for offset in range(1, config.YARD_DUTY_MAX_POSTS + 1):
        r = header_row + offset
        post = cell(r, label_col)
        if not post:
            break  # blank label = end of this block
        name = cell(r, name_col)
        if name:  # skip posts nobody is assigned to
            pairs.append((post, name))
    return week_label, pairs


def _join_definitions(pairs: list[tuple[str, str]]) -> list[DutyAssignment]:
    """Attach the stable time/where from config to each (post, name)."""
    # Case-insensitive lookup of post definitions.
    defs = {k.lower(): v for k, v in config.POST_DEFINITIONS.items()}
    out: list[DutyAssignment] = []
    for post, name in pairs:
        meta = defs.get(post.lower(), {})
        out.append(
            DutyAssignment(
                post=post,
                name=name,
                time=meta.get("time", ""),
                where=meta.get("where", ""),
                part=meta.get("part", "mid"),
            )
        )
    return out


def fetch_current(today: dt.date | None = None) -> DutyResult:
    """
    Main entry point. Find today's duty assignments. Never raises — problems
    come back as `.warning` with an empty `.assignments`.
    """
    today = today or dt.date.today()

    # --- credentials / dependency guard ----------------------------------
    if not config.GOOGLE_SERVICE_ACCOUNT_FILE:
        return DutyResult([], None, "no GOOGLE_SERVICE_ACCOUNT_FILE set — skipping yard duty")

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return DutyResult([], None, "gspread/google-auth not installed — skipping yard duty")

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    try:
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(config.YARD_DUTY_SHEET_ID)
    except Exception as exc:  # auth, network, sharing, wrong ID…
        return DutyResult([], None, f"could not open the Sheet ({exc})")

    worksheets = _target_worksheets(spreadsheet)
    if not worksheets:
        return DutyResult([], None, "no matching duty tab found (check YARD_DUTY_TAB_PATTERN)")

    # --- scan every candidate tab/block for the one containing today -----
    nearest_upcoming: tuple[dt.date, str | None, list[tuple[str, str]]] | None = None

    for ws in worksheets:
        grid = ws.get_all_values()  # one network call per tab; tabs are few
        for week_i in range(config.YARD_DUTY_MAX_WEEKS):
            label_col = config.YARD_DUTY_FIRST_BLOCK_COL + week_i * config.YARD_DUTY_BLOCK_STRIDE
            week_label, pairs = _read_block(grid, label_col)
            if not week_label or not pairs:
                continue

            header_match = _WEEK_HEADER.search(week_label)
            if not header_match:
                continue
            date_range = _parse_date_range(header_match.group("dates"))
            if not date_range:
                continue

            start, end = date_range
            if start <= today <= end:
                # Direct hit — this is the current week.
                return DutyResult(_join_definitions(pairs), week_label)

            # Otherwise remember the soonest future block as a fallback so the
            # board can show "next week's" duty over a weekend/break.
            if start > today and (nearest_upcoming is None or start < nearest_upcoming[0]):
                nearest_upcoming = (start, week_label, pairs)

    if nearest_upcoming is not None:
        _, label, pairs = nearest_upcoming
        return DutyResult(
            _join_definitions(pairs),
            label,
            "no week contains today — showing the next scheduled week",
        )

    return DutyResult([], None, "found duty tabs but no week matched today (off-cycle / summer?)")


# ── Dry-run ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    from dotenv import load_dotenv
    load_dotenv()          # picks up GOOGLE_SERVICE_ACCOUNT_FILE from .env

    result = fetch_current()

    if result.warning:
        print(f"⚠  Warning: {result.warning}\n")

    if not result.assignments:
        print("No assignments returned — check the warning above and your Sheet sharing.")
    else:
        print(f"Week: {result.week_label}\n")
        for a in result.assignments:
            print(f"  {a.part:<12} {a.post:<30} {a.name:<25} {a.where}")

    print("\n--- raw JSON that would go into signage.json ---")
    print(json.dumps([vars(a) for a in result.assignments], indent=2))
