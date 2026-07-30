# SOAR Staff Signage

A staff-room digital signage board for SOAR Charter Academy. A small Python
program reads the week's staff bulletin and the yard-duty Google Sheet, and a
self-contained web page renders the week's events, the duty schedule, and a live
house-points display on a hallway TV — refreshing itself and changing its look
with the seasons.

The board runs unattended on a [Vivi](https://www.vivi.io/) signage screen,
pointed at a single Firebase-hosted URL. Keeping it current takes one person a
couple of minutes a week.

> _Screenshot: add `docs/board.png` here once captured — a live shot of the board
> is the fastest way for a reader to understand the project._

---

## Overview

Every week the front office publishes a staff bulletin (a Word document) and
maintains a yard-duty rotation (a Google Sheet). That information was previously
trapped in documents nobody opened. This project surfaces it on a screen staff
actually walk past, with zero manual re-typing.

The design goal was a board that is **effortless to keep live** and **safe by
default** — specifically, one that can read a bulletin full of student names
without any of that data ever leaving the building.

## How It Works

The system is two cooperating halves that share a single data file,
`display/data/signage.json`:

**1. The Updater (`updater/`, Python).** Run once a week from the office Mac. It
opens the week's bulletin, strips out anything resembling student data, asks
Claude (Anthropic's API) to pull out the structured events, reads the current
week's duty assignments from the Google Sheet, collects any typed-in
announcements, and writes the result to `signage.json`.

**2. The Display (`display/`, plain HTML/CSS/JavaScript).** A single web page
that reads `signage.json` and renders the board: a "This Week" schedule, a
live "now / up next" banner, the day's duty roster grouped by morning / midday /
afternoon with the current period highlighted, QR codes for logging house points
and work orders, a scrolling announcements ticker, and an embedded live
house-points panel. It re-reads the data and re-checks the time on a timer, so
the screen stays correct all day without anyone touching it.

The two halves are deliberately decoupled. The Updater can run (or fail) without
affecting a board that's already on screen, and the Display has no dependency on
Python, a server, or a database — it's just files.

```
   Weekly bulletin (.docx) -+
                            +-->  Updater (Python)  -->  signage.json  -->  Display (web)  -->  Firebase  -->  Vivi TV
   Yard-duty Google Sheet --+                                                  ^
                                                                               +-- live house-points iframe
```

## Privacy & Student-Data Protection

The bulletin routinely contains student names (in sections like behavior tallies
or differentiated-assistance lists). None of that is allowed to reach an external
API. Three layers enforce this, in `updater/sanitize.py`:

1. **Hard cut at known markers.** Everything from the first sensitive section
   heading (e.g. "Differentiated Assistance," "House Points") to the end of the
   document is removed before anything else happens.
2. **Pattern scrubbing.** Roster-style lines that survive the cut are stripped by
   regular expression.
3. **A human confirmation gate.** The Updater prints the exact text it is about to
   send and refuses to continue until the operator types `yes`.

Duty names are staff, not students, and come from the Google Sheet — they never
pass through the bulletin pipeline or the API. All credentials live in an
untracked `.env` file and a service-account key that is git-ignored; the Google
service account is **read-only** and is granted access to exactly one Sheet.

## Tech Stack

- **Python 3.12** — the Updater
- **Anthropic Claude API** — extracting structured events from free-form bulletin prose
- **Google Sheets API** via `gspread` + `google-auth` — reading the duty rotation (read-only)
- **`python-docx`** — reading the bulletin
- **Vanilla HTML / CSS / JavaScript** — the Display (no framework, no build step)
- **Firebase Hosting** — serving the board at a stable URL for Vivi

## Repository Structure

```
soar-signage/
|-- firebase.json              # Firebase Hosting config (serves the display/ folder)
|-- updater/                   # the weekly Python program
|   |-- config.py              # * the one file you edit - paths, IDs, post definitions
|   |-- update_signage.py      # orchestrator: pick bulletin -> run pipeline -> write JSON
|   |-- bulletin.py            # read .docx -> sanitize -> confirm -> Claude -> structured events
|   |-- sanitize.py            # the student-data protection layer
|   |-- yard_duty.py           # read the current week's duty from the Google Sheet
|   |-- patch_duty.py          # helper: refresh only the duty data, no bulletin needed
|   |-- run_update.command     # double-click launcher for macOS
|   |-- requirements.txt       # Python dependencies
|   |-- .env                   # secrets (NOT in git) - you create this
|   `-- service-account.json   # Google key (NOT in git) - you download this
`-- display/                   # the web board (this folder is what gets hosted)
    |-- index.html
    |-- style.css
    |-- app.js                 # data loading, rendering, theming, refresh timers
    |-- effects.js             # seasonal particle effects (snow / leaves / confetti)
    |-- themes/
    |   |-- themes.json        # which theme is active on which dates, + effects
    |   `-- themes.css         # the per-season color palettes
    `-- data/
        |-- signage.json       # live data the board reads (written by the Updater)
        `-- signage.sample.json # a realistic example for previewing without a run
```

## Getting Started

### Prerequisites

- macOS with **Python 3.12** (`python3.12 --version` to check)
- A **Google Cloud project** with the **Google Sheets API** enabled
- An **Anthropic API key** (from [console.anthropic.com](https://console.anthropic.com))
- The **Firebase CLI** for deployment (`npm install -g firebase-tools`)

### 1. Install Python dependencies

```bash
pip install --break-system-packages -r updater/requirements.txt
```

### 2. Add your Anthropic API key

Create `updater/.env` (it is git-ignored) and add:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Set up Google Sheets access

The Updater reads the duty Sheet through a **service account** — a robot Google
account that you grant read access to one specific Sheet.

1. In your Google Cloud project, enable the **Google Sheets API**.
2. Create a **service account**, then create a **JSON key** for it and download
   the file. Save it as `updater/service-account.json`.
3. Open the duty Sheet, click **Share**, and add the service account's email
   (it looks like `name@project.iam.gserviceaccount.com`) as a **Viewer**.
4. Add the key's path to `updater/.env`:

```
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
```

No project roles or Drive permissions are needed — sharing the Sheet is what
grants access.

### 4. Configure the project — `updater/config.py`

This is the single file you edit to point the system at your data. It is
organized in numbered sections:

- **Paths** — usually left alone.
- **Anthropic** — the model name (defaults to a current Claude model).
- **Sanitize** — the section headings that trigger the hard cut, and the
  roster-line patterns. Update these if the bulletin's format changes.
- **Yard duty** — the `YARD_DUTY_SHEET_ID` and the Sheet's layout (see below).
- **Post definitions** — maps each duty post label to its time and location.
  The keys here **must match the post labels in column A of the Sheet** (the
  match is case-insensitive). A mismatch silently drops that post's time/location.

#### How the duty Sheet is read

The reader expects one tab per cycle, named like **`Cycle 10`** (it matches any
tab named `Cycle <number>` automatically — you don't reconfigure it each cycle).
Within a tab, weeks sit side by side in column groups, each headed by a cell like
`Week 1 (June 1st - 5th)`:

| Column A       | Column B     | _(gap)_ | Column D       | Column E     |
| -------------- | ------------ | ------- | -------------- | ------------ |
| Week 1 (dates) |              |         | Week 2 (dates) |              |
| _post label_   | _staff name_ |         | _post label_   | _staff name_ |
| ...            | ...          |         | ...            | ...          |

Weeks advance by three columns (A -> D -> G -> J), with the staff name one column
to the right of each post label. Those offsets are all configurable constants in
the **Yard duty** section. The reader finds the week block containing today's
date, or falls back to the next upcoming week (so the board shows next week's
duty over a weekend or break). If it can't read the Sheet, it fails quietly and
leaves the rest of the board working.

### 5. Configure the display — `display/app.js`

At the top of `app.js` is a `CONFIG` object holding the QR-code form URLs (House
Points, Spirit Tally, Work Order) and the `countdownTo` date shown in the header.
Update these to your own links and dates.

## Weekly Workflow

1. Double-click **`updater/run_update.command`** (the first time, you may need to
   run `chmod +x updater/run_update.command` to allow it).
2. Choose this week's bulletin `.docx` in the file picker.
3. Review the sanitized text it prints, and type `yes` to send it.
4. Add any announcements when prompted (prefix one with `!` to mark it
   high-priority in the ticker).
5. It writes the new `signage.json`.
6. Publish it (see Deployment).

To refresh **only** the duty roster mid-week without re-running a bulletin, run
`python3.12 updater/patch_duty.py` — it pulls fresh assignments from the Sheet
and updates `signage.json` in place.

## Deployment (Firebase Hosting)

The `display/` folder is hosted on Firebase. To publish the current `signage.json`
(or any change):

```bash
firebase deploy --only hosting
```

That pushes the board to its public URL, which Vivi displays. A deploy takes
about a minute to go live.

## Theming

The board changes its palette and ambient effect by date, configured in
`display/themes/themes.json` — each theme has a label, an effect (snow, leaves,
confetti, or none), and the date windows it's active. Palettes live in
`themes/themes.css`. The default skin is SOAR's navy / red / gold. New seasons
are added by editing those two files; no code changes are required.

## Author

Built by **Jason Hicks**, Education Technology Specialist, SOAR Charter Academy.

---

_This board handles only staff-facing scheduling and recognition data. See
**Privacy & Student-Data Protection** above for how student information is kept
out of the pipeline entirely._

