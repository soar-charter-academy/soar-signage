# SOAR Staff-Room Signage

A two-part digital signage system for the staff room:

- **`updater/`** — run once a week. It reads the weekly bulletin (`.docx`),
  pulls yard duty from the Google Sheet, lets you type extra announcements, and
  writes **`display/data/signage.json`**.
- **`display/`** — a kiosk web page. It reads that JSON, shows the schedule and
  duty board, and embeds the live **House Cup** directly from
  `soarpoints.web.app/display` (no reinventing the wheel — the cycling
  daily/weekly/monthly/yearly views come along for free).

```
soar-signage/
├── updater/         run weekly  →  writes display/data/signage.json
├── display/
│   ├── index.html   the board
│   ├── style.css    layout; all colors/fonts via CSS variables
│   ├── app.js       CONFIG lives here (form URLs, countdown)
│   ├── themes/
│   │   ├── themes.json   date-range registry (12 skins)
│   │   └── themes.css    12 seasonal skins as variable-override blocks
│   ├── effects.js   optional snow/leaves/confetti (themes opt in)
│   └── data/
│       ├── signage.json         ← this is what the updater writes
│       └── signage.sample.json  ← starting data so the board works immediately
```

---

## The one rule: student data never reaches the API

The bulletin's free-text events are parsed by the Anthropic API (wording drifts
weekly). But student names (the *Differentiated Assistance* roster) must never
be sent. Three layers enforce this:

1. **Cut** — `sanitize.py` deletes everything from the first stop-marker
   (`Differentiated Assistance`, `House Points`, `Spirit Tally`) to end-of-doc.
2. **Scrub** — any remaining line that looks like a roster entry is dropped.
3. **You** — the updater prints the *exact* text it's about to send and waits
   for you to type `yes`. Nothing leaves unseen.

Yard-duty names come straight from the Sheet and never touch the API.

---

## Setup

### 1. Updater

```bash
cd updater
pip install --break-system-packages -r requirements.txt
```

Create `updater/.env` (never commit this):

```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
```

**Google Sheets access (5 min, one-time):**
1. Google Cloud Console → create project → enable **Google Sheets API**.
2. Create a **Service Account** → add a JSON key → download it. Put its path
   in `.env`.
3. Open the yard-duty Sheet → **Share** → paste the service account email
   (`name@project.iam.gserviceaccount.com`) with **Viewer** access.

Run it:

```bash
python3.12 update_signage.py     # or double-click run_update.command
```

> **If you skip the API key** the updater still runs — events just won't be
> auto-extracted. Type things into the announcements box instead.

### 2. Display

Static files — serve the `display/` folder any way you like:

```bash
cd display
python3 -m http.server 8080
# open http://localhost:8080 → F11 fullscreen
```

The board works immediately on `signage.sample.json`. The soarpoints iframe
will show live house points once it confirms framing isn't blocked.

### 3. House Cup iframe — one thing to verify

The House Cup is an iframe pointing at `https://soarpoints.web.app/display`.
Open the board in a browser, then open DevTools (F12) → Console tab. If you
see a "refused to display in a frame" error, the app is sending an
`X-Frame-Options` header. Fix: add this to `firebase.json` in the
**soarpoints** project (not this one) and redeploy:

```json
"headers": [{
  "source": "**",
  "headers": [{ "key": "X-Frame-Options", "value": "ALLOWALL" }]
}]
```

Firebase doesn't set this header by default, so it will probably just work.

### 4. Quick CONFIG edits in `display/app.js`

Near the top of `app.js` is a `CONFIG` object — two things to update:

```js
forms: [
  { label: "House Points", url: "https://forms.gle/YOUR-REAL-LINK" },
  { label: "Spirit Tally", url: "https://forms.gle/YOUR-REAL-LINK" },
],
countdownTo: { label: "Last Day", date: "2026-06-12" },  // update yearly
```

---

## ⚠️ Verify these Sheet assumptions

The yard-duty reader was built from a screenshot. The layout is encoded as
**offsets in `updater/config.py` §4** — fix the numbers there if anything
doesn't match your real Sheet; no logic to touch.

- Each cycle is its own tab named like **`Cycle 9`**.
- Inside a tab, weeks sit side-by-side in column pairs (A/B, then D/E, then
  G/H …) with a one-column gap between. `FIRST_BLOCK_COL=0`, `BLOCK_STRIDE=3`,
  `NAME_COL_OFFSET=1`.
- Row 1 of each block is a header like **`Week 1 (May 4th - 8th)`**.
- Post labels match the keys in `POST_DEFINITIONS` (that's where time/place
  come from — the Sheet only gives you the name).

If auto-detection misbehaves, set `YARD_DUTY_TAB_OVERRIDE = "Cycle 9"` in
`config.py` to force a specific tab. Bad creds or no current week → empty duty
panel + a warning in the run log, never a crash.

---

## Seasonal skins

12 skins in `display/themes/themes.css` as `[data-theme="key"]` blocks. The
display auto-picks one by today's date from `themes.json`. Overlapping windows
use the `order` priority (halloween beats fall, etc.).

- **Preview any skin:** add `?theme=halloween` to the URL.
- **Force a skin for a stretch** (spirit week, etc.): set `THEME_OVERRIDE` in
  `config.py` and re-run the updater.
- **Add art later:** drop files in `themes/<key>/assets/` and reference them:
  ```css
  --bg-image: url("halloween/assets/backdrop.png");
  --deco-tr:  url("halloween/assets/bats.png");
  ```
- The House Cup iframe does **not** follow the skins — intentional; it keeps
  its own look year-round.

---

## The two surprise features

1. **Happening Now / Up Next** — a live banner above the schedule that shows
   what's on right now and what's next, recomputed every 30 seconds from
   today's timed events.
2. **Scan to Log** — QR codes for the House Points and Spirit Tally forms,
   generated from the URLs in `CONFIG.forms`. Staff scan off the wall to log
   from their phones. Paste the real form links in `app.js`.

Bonus from the theme system: an optional **ambient particle layer** (snow for
winter/holidays, leaves for fall, confetti for end-of-year) in `effects.js`.
Themes opt in via `"effect"` in `themes.json`.

---

## Deployment notes

- The display fetches `data/signage.json` relative to itself, so running the
  updater with its default `SIGNAGE_JSON` path (which writes into `display/data/`)
  means "run, done, the board picks it up in ~5 minutes."
- The board never scrolls and uses no browser storage — safe to leave running.
  It re-reads the JSON every 5 minutes (catches a new weekly run automatically)
  and re-checks the date/theme every 30 seconds.
- To run `run_update.command` as a double-click launcher: `chmod +x updater/run_update.command`
