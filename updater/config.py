"""
config.py — Everything you'll ever need to tweak lives here.
=============================================================

This is the ONE file you should expect to edit regularly. The other modules
read their settings from here so you never have to go spelunking through logic
to change a path, a column offset, or a model name.

Read the comments top-to-bottom once; after that it's just knobs.

Secrets (API keys, etc.) do NOT live here. They live in a `.env` file next to
this one (see README). We load that file automatically below so you can keep
credentials out of git.
"""

from __future__ import annotations

import os
from pathlib import Path

# python-dotenv lets us keep secrets in a .env file instead of in code or in
# your shell profile. If it isn't installed we degrade gracefully and just rely
# on real environment variables.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover - optional dependency
    # Not fatal. You can still export the vars in your shell. README explains.
    pass


# ---------------------------------------------------------------------------
# 1. PATHS
# ---------------------------------------------------------------------------
# Where things live on disk. Everything is anchored to the repo root so the
# project keeps working no matter where you clone it.

REPO_ROOT = Path(__file__).resolve().parent.parent

# The display reads this file. The updater writes it. This is the contract
# between the two halves of the system — the ONLY thing that crosses the line.
# We write straight into display/data so the kiosk page can fetch it locally.
SIGNAGE_JSON = REPO_ROOT / "display" / "data" / "signage.json"

# When the file picker opens, it starts here. Point it at wherever the weekly
# bulletins get saved/exported so you're never hunting through folders.
# `None` means "default to your home directory".
BULLETIN_START_DIR: Path | None = Path.home() / "Downloads"


# ---------------------------------------------------------------------------
# 2. ANTHROPIC API  (for parsing the bulletin's free-text events)
# ---------------------------------------------------------------------------
# The bulletin is written by a human and the wording drifts week to week, so we
# don't regex it — we hand the (sanitized!) text to the API and get back clean,
# structured events. One document a week ≈ pennies.
#
# The key is read from the environment (.env), never stored here.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model string. Sonnet is a good balance of "reliable at extraction" and cheap.
# Swap to a Haiku-class model to cut cost further, or an Opus-class model if you
# ever feed it really gnarly bulletins. (Model names occasionally change — if a
# call 404s on the model, update this string.)
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# If the key is missing the updater still runs — it just skips event extraction
# and warns you. The display will simply show no auto-events that week (you can
# still type things into the announcements box). This keeps you un-blocked if
# you're offline or haven't set the key up yet.


# ---------------------------------------------------------------------------
# 3. STUDENT-DATA SAFETY  (read this section carefully)
# ---------------------------------------------------------------------------
# HARD RULE: student data must never reach the API.
#
# In the bulletins we've seen, the only student names live in the
# "Differentiated Assistance" roster near the bottom, followed by form links we
# also don't want. So the simplest, most robust strip is: cut everything from
# the first "stop marker" downward. The sensitive block and the junk happen to
# live together at the tail, so one cut handles both.
#
# These markers are matched case-insensitively. If ANY of them appears, every-
# thing from that point to the end of the document is removed before we send a
# single character to the API. When in doubt, add more markers — over-cutting
# is safe, under-cutting is not.
SANITIZE_STOP_MARKERS = [
    "Differentiated Assistance",
    "House Points",          # form link section
    "Spirit Tally",          # form link section
]

# Belt-and-suspenders line-level scrub. Even above the cut line, drop any line
# that looks like a grade-roster entry ("3rd: Name & Name", "RSP- ...", etc.).
# These regexes are applied to EVERY surviving line as a second safety net.
SANITIZE_LINE_PATTERNS = [
    r"^\s*(TK|RSP|Rec Aides|Kinder(garten)?)\b.*:",   # support-program rosters
    r"^\s*\d+(st|nd|rd|th)\s*:",                       # "1st:", "2nd:", grade lists
]

# The updater ALWAYS prints the exact text it is about to send and waits for you
# to type "yes". This human gate is the real guarantee; the auto-strip is just
# convenience so you rarely have to think about it. Set to False only if you're
# running fully unattended and you trust the markers above (not recommended).
REQUIRE_SEND_CONFIRMATION = True


# ---------------------------------------------------------------------------
# 4. GOOGLE SHEET  (yard-duty assignments — the "who is where")
# ---------------------------------------------------------------------------
# The bulletin's duty table only defines the posts. The actual people are in the
# linked Sheet. We read it with a service account (see README for the 5-minute
# setup). No student data here — these are staff names — and it never touches
# the API anyway; it goes straight into the JSON.

# The spreadsheet's ID — the long string in its URL between /d/ and /edit.
# From your link: docs.google.com/spreadsheets/d/<THIS PART>/edit
YARD_DUTY_SHEET_ID = "1E_mAlsLnZlKAcqlEfBrh-jNG9DDIF_Cql2PYBEeQ_KM"

# Path to the service-account JSON key file. Read from .env so it's not in git.
# (You'll download this once from Google Cloud and share the Sheet with the
# service account's email — README walks through it.)
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")

# --- Sheet layout ---------------------------------------------------------
# These describe the SHAPE of the grid so the reader can find "this week".
#
# ⚠️  ASSUMPTIONS FROM YOUR SCREENSHOT — VERIFY THESE WHEN YOU'RE BACK ⚠️
#   • Each cycle is its own tab, named like "Cycle 9".
#   • Inside a tab, weeks sit side-by-side in column PAIRS:
#       col 0 = post label, col 1 = name  (Week 1, columns A/B)
#       then a 1-column gap, then the next week (Week 2, columns D/E), etc.
#   • Row 0 of each block is a header like "Week 1 (May 4th - 8th)".
#   • Posts run down the rows beneath that header.
#
# If your real layout differs, this is the section to fix. It's all offsets;
# no logic to touch.

# Worksheet/tab name pattern. We scan tabs matching this for the current week.
# (Python regex. "Cycle 8", "Cycle 9"… all match.)
YARD_DUTY_TAB_PATTERN = r"^Cycle\s*\d+$"

# If auto-detection ever misbehaves, set this to a specific tab name (e.g.
# "Cycle 9") to force the reader to look only there. None = scan all matches.
YARD_DUTY_TAB_OVERRIDE: str | None = None

# How week-blocks repeat across columns (all 0-indexed):
YARD_DUTY_FIRST_BLOCK_COL = 0   # column A — first week's label column
YARD_DUTY_BLOCK_STRIDE = 3      # A→D→G→J  = +3 columns per week
YARD_DUTY_MAX_WEEKS = 6         # how many week-blocks to look across, max
YARD_DUTY_NAME_COL_OFFSET = 1   # name is 1 column right of the label

# Rows: the header is on this row, posts begin on the next row and run down
# until we hit a blank label or this many posts, whichever comes first.
YARD_DUTY_HEADER_ROW = 0        # row 1 in the Sheet (0-indexed)
YARD_DUTY_MAX_POSTS = 20

# Year to assume for the week date-ranges, which are written without a year
# ("May 4th - 8th"). Defaults to the current year. Override only if a Sheet
# spans a year boundary in a way that confuses things.
YARD_DUTY_ASSUME_YEAR: int | None = None  # None = current calendar year


# ---------------------------------------------------------------------------
# 5. POST DEFINITIONS  (the stable when/where for each duty post)
# ---------------------------------------------------------------------------
# The Sheet gives us WHO. This gives us WHEN and WHERE — the bits that almost
# never change. We deliberately DROP the verbose "active supervision / keep cars
# moving" instructions (not glanceable on a wall) and keep only time + place.
#
# The display joins these: post + time + location + (name from the Sheet).
# Keys must match the post labels in the Sheet exactly (case-insensitive match
# is handled in code, but keep them tidy).
POST_DEFINITIONS = {
    "AM Green 1":          {"time": "7:30–7:45a", "where": "Staff Lot",   "part": "am"},
    "AM Playground 1":     {"time": "7:30–7:45a", "where": "Playground",  "part": "am"},
    "AM Green 2":          {"time": "7:45–7:55a", "where": "Staff Lot",   "part": "am"},
    "AM Playground 2 A":   {"time": "7:45–7:55a", "where": "Playground",  "part": "am"},
    "AM Playground 2 B":   {"time": "7:45–7:55a", "where": "Playground",  "part": "am"},
    "Nutrition A":         {"time": "Nutrition",  "where": "Quad",        "part": "mid"},
    "Nutrition B":         {"time": "Nutrition",  "where": "Quad",        "part": "mid"},
    "PM Primary":          {"time": "Recess",     "where": "Playground",  "part": "mid"},
    "PM Upper":            {"time": "Recess",     "where": "Playground",  "part": "mid"},
    "PM Green 1 A":        {"time": "3:00–3:10p", "where": "Staff Lot",   "part": "pm"},
    "PM Green 1 B":        {"time": "3:00–3:10p", "where": "Staff Lot",   "part": "pm"},
    "PM Green 2 A":        {"time": "3:10–3:20p", "where": "Staff Lot",   "part": "pm"},
    "PM Green 2 B":        {"time": "3:10–3:20p", "where": "Staff Lot",   "part": "pm"},
    "PM Red":              {"time": "3:00–3:15p", "where": "Kinder Gate", "part": "pm"},
}


# ---------------------------------------------------------------------------
# 6. THEME OVERRIDE  (optional)
# ---------------------------------------------------------------------------
# Normally the display picks its seasonal skin automatically from today's date.
# If you ever want to FORCE a skin (e.g. flip to "halloween" early for a spirit
# week, or preview "christmas"), set it here and it gets written into the JSON.
# The display honors it until you set it back to None.
# Valid values are any theme key in display/themes/themes.json.
THEME_OVERRIDE: str | None = None
