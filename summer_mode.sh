#!/usr/bin/env bash
# =============================================================================
# summer_mode.sh — turn the SOAR signage board into tropical Summer Break mode.
# Run from the repo root:  bash summer_mode.sh
#
# What it does:
#   1. Replaces the summer-break theme block in display/themes/themes.css with a
#      full tropical palette (sand + teal + coral + mango, palm/sun/wave/
#      pineapple corner art — all pure CSS/inline-SVG, no asset files).
#   2. Sets THEME_OVERRIDE = "summer-break" in updater/config.py so the board
#      flips to summer immediately (not waiting for the 07-08 date window).
#   3. Writes a summer signage.json: one warm message, empty events/duty, with
#      commented placeholders for next year baked into a sidecar template.
#   4. Comments out the nightly cron so no "no bulletin" alerts fire all summer.
#
# Nothing here touches layout, the House Points frame, or the font sizes.
# A backup of every edited file is written next to it as <file>.bak-summer.
# Re-running is safe (it restores from .bak first if present).
# =============================================================================
set -euo pipefail

ROOT="$(pwd)"
THEMES="display/themes/themes.css"
CONFIGPY="updater/config.py"
SIGNAGE="display/data/signage.json"
WORKFLOW=".github/workflows/nightly.yml"

for f in "$THEMES" "$CONFIGPY"; do
  [ -f "$f" ] || { echo "ERROR: can't find $f — are you in the repo root?"; exit 1; }
done

backup() { [ -f "$1.bak-summer" ] && cp "$1.bak-summer" "$1" || cp "$1" "$1.bak-summer"; }

# ---- 1. Swap the summer-break theme block --------------------------------
backup "$THEMES"
python3 - "$THEMES" <<'PYEOF'
import re, sys
path = sys.argv[1]
css = open(path).read()
newblock = r'''/* ---- SUMMER BREAK ----------------------------------------------------------
   LIGHT skin — full tropical. Sunrise-over-the-ocean: warm sand field, deep
   teal header band, white panels with seafoam edges, coral "now" + mango hero.
   Pure-CSS sun/sand wash and inline-SVG corner flourishes (palm, sun, wave,
   pineapple) — zero asset files. Vacation mode, but still legible wall-side. */
[data-theme="summer-break"] {
  --bg:        #fff4dd;   /* warm sand field */
  --bg-2:      #ffe2a8;   /* golden sunlight glow */
  --surface:   #ffffff;   /* clean white panels */
  --surface-2: #eafaf6;   /* palest aqua rows */
  --border:    #8fd9cf;   /* soft seafoam hairline */
  --text:      #0f3a44;   /* deep teal-slate text */
  --text-dim:  #5b8a8f;   /* muted teal-grey */
  --accent:    #0aa6c2;   /* bright lagoon teal */
  --accent-2:  #14c8b0;   /* aqua-mint */
  --today:     #ff5a4d;   /* coral / sunset pop */
  --accent-gold: #ffb22e; /* mango sunshine — hero */
  --good:      #1fb574;
  --bad:       #ff6b6b;
  --header-bg: #0c6e7d;   /* deep tropical-ocean teal band */
  --header-text: #ffffff;
  --on-gold:   #5a3000;   /* warm brown text on mango fills */
  --shadow:    0 8px 22px rgba(12, 110, 125, 0.18);
  --font-display: "Pacifico", cursive;
  --display-tracking: 0;

  /* fruit-stand category dots, tuned to pop on white panels */
  --cat-celebration: #ff6fb5;
  --cat-meeting:     #2bb3d4;
  --cat-deadline:    #ff8a3d;
  --cat-trip:        #18c08a;
  --cat-food:        #ffb22e;
  --cat-sports:      #36c5e8;
  --cat-general:     #7fa7ad;

  /* sunrise wash painted under everything (sits behind --bg) */
  --bg-image:
    radial-gradient(ellipse 90% 55% at 85% -10%, rgba(255, 178, 46, 0.35), transparent 60%),
    radial-gradient(ellipse 80% 50% at 0% 110%, rgba(20, 200, 176, 0.22), transparent 55%),
    linear-gradient(180deg, #d8f3ff 0%, #fff4dd 45%);

  /* corner flourishes — inline SVG data-URIs, low-contrast so they decorate
     without fighting the content. sun TR · palm TL · wave BL · pineapple BR */
  --deco-size: 210px;
  --deco-tr: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><g fill="none" stroke="%23ffb22e" stroke-width="7" stroke-linecap="round" opacity="0.55"><circle cx="150" cy="50" r="30" fill="%23ffd87a" stroke="none"/><line x1="150" y1="2" x2="150" y2="13"/><line x1="150" y1="87" x2="150" y2="98"/><line x1="102" y1="50" x2="113" y2="50"/><line x1="187" y1="50" x2="198" y2="50"/><line x1="115" y1="15" x2="123" y2="23"/><line x1="177" y1="77" x2="185" y2="85"/><line x1="185" y1="15" x2="177" y2="23"/><line x1="123" y1="77" x2="115" y2="85"/></g></svg>');
  --deco-tl: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><g fill="%2318c08a" opacity="0.38"><path d="M22 22 Q72 37 97 82 Q62 57 32 62 Q57 52 22 22Z"/><path d="M22 22 Q42 72 37 122 Q27 77 7 67 Q32 62 22 22Z"/><path d="M22 22 Q77 27 122 42 Q82 32 62 47 Q57 27 22 22Z"/></g></svg>');
  --deco-bl: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><g fill="none" stroke="%230aa6c2" stroke-width="6" stroke-linecap="round" opacity="0.40"><path d="M2 152 Q27 132 52 152 T102 152 T152 152"/><path d="M2 172 Q27 152 52 172 T102 172 T152 172"/></g></svg>');
  --deco-br: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><g opacity="0.42"><path d="M150 96 Q135 81 150 61 Q165 81 150 96Z" fill="%2318c08a"/><path d="M150 96 Q133 83 128 71 Q150 79 150 96Z" fill="%2318c08a"/><path d="M150 96 Q167 83 172 71 Q150 79 150 96Z" fill="%2318c08a"/><ellipse cx="150" cy="136" rx="28" ry="40" fill="%23ffb22e"/><g stroke="%23c97e1a" stroke-width="2.5" opacity="0.65"><line x1="130" y1="111" x2="170" y2="151"/><line x1="170" y1="111" x2="130" y2="151"/><line x1="124" y1="136" x2="176" y2="136"/></g></g></svg>');
}'''
pattern = re.compile(r'/\* ---- SUMMER BREAK.*?\n\[data-theme="summer-break"\]\s*\{.*?\n\}', re.S)
out, n = pattern.subn(newblock, css, count=1)
if n != 1:
    sys.exit("ERROR: could not find the summer-break block to replace")
assert out.count('[data-theme="summer-break"]') == 1
open(path, "w").write(out)
print("  [1/4] themes.css — tropical summer-break block installed")
PYEOF

# ---- 2. Force the theme on via THEME_OVERRIDE ----------------------------
backup "$CONFIGPY"
python3 - "$CONFIGPY" <<'PYEOF'
import re, sys
path = sys.argv[1]
src = open(path).read()
out, n = re.subn(r'THEME_OVERRIDE:\s*str\s*\|\s*None\s*=\s*None',
                 'THEME_OVERRIDE: str | None = "summer-break"', src, count=1)
if n != 1:
    # already set, or signature differs — try a looser match
    out, n = re.subn(r'THEME_OVERRIDE\s*=\s*None',
                     'THEME_OVERRIDE = "summer-break"', src, count=1)
if n != 1:
    sys.exit("ERROR: could not set THEME_OVERRIDE in config.py — set it by hand")
open(path, "w").write(out)
print('  [2/4] config.py — THEME_OVERRIDE = "summer-break"')
PYEOF

# ---- 3. Write the summer signage.json ------------------------------------
mkdir -p "$(dirname "$SIGNAGE")"
[ -f "$SIGNAGE" ] && cp "$SIGNAGE" "$SIGNAGE.bak-summer" || true
cat > "$SIGNAGE" <<'JSONEOF'
{
  "generated_at": "2026-06-15T09:00:00",
  "week_of": "2026-06-15",
  "theme_override": "summer-break",
  "events": [],
  "yard_duty": {
    "week_label": "",
    "assignments": []
  },
  "announcements": [
    { "text": "Have a wonderful summer, SOAR staff — see you in August! \u2600", "priority": "high" }
  ],
  "diagnostics": {
    "sanitize": "summer mode — no bulletin processed",
    "bulletin_warning": null,
    "yard_duty_warning": null
  }
}
JSONEOF
echo "  [3/4] signage.json — summer content written (1 message, empty events/duty)"

# ---- 3b. Next-year template (committed, not served) ----------------------
cat > "display/data/signage.summer-template.json" <<'JSONEOF'
{
  "_README": "Next summer, copy this over data/signage.json and fill in. Keep theme_override summer-break. Events/announcements show; empty arrays render clean 'nothing scheduled' states. Dates are ISO YYYY-MM-DD; category is one of celebration|meeting|deadline|trip|food|sports|general.",
  "generated_at": "2027-06-15T09:00:00",
  "week_of": "2027-06-15",
  "theme_override": "summer-break",
  "events": [
    { "_example": true, "title": "Summer School Session 1 Begins", "date": "2027-06-21", "day": "Monday", "start": "08:00", "end": null, "location": "Rooms 12-15", "category": "general", "audience": "Summer school students" }
  ],
  "yard_duty": { "week_label": "", "assignments": [] },
  "announcements": [
    { "text": "Have a wonderful summer, SOAR staff — see you in August!", "priority": "high" },
    { "_example": true, "text": "Front office open 8a-2p, Monday-Thursday.", "priority": "normal" }
  ],
  "diagnostics": { "sanitize": "summer mode — no bulletin processed", "bulletin_warning": null, "yard_duty_warning": null }
}
JSONEOF
echo "        + signage.summer-template.json (placeholders for next year)"

# ---- 4. Silence the nightly cron for the summer --------------------------
if [ -f "$WORKFLOW" ]; then
  backup "$WORKFLOW"
  if grep -qE '^\s*-\s*cron:\s*"0 9 \* \* \*"' "$WORKFLOW"; then
    sed -i.tmp -E 's/^(\s*)(- cron: "0 9 \* \* \*")/\1# \2   # SUMMER: paused — re-enable in August/' "$WORKFLOW"
    rm -f "$WORKFLOW.tmp"
    echo "  [4/4] nightly.yml — cron commented out (manual dispatch still works)"
  else
    echo "  [4/4] nightly.yml — cron line not matched; comment it out by hand if desired"
  fi
else
  echo "  [4/4] nightly.yml not found locally (it's fine; CI is server-side) — skip"
fi

echo
echo "Done. Preview locally before deploying:"
echo "    cd display && python3 -m http.server 8081     # then open http://localhost:8081"
echo
echo "When it looks right, ship it:"
echo "    git add -A"
echo "    git commit -m 'Summer mode: tropical theme + summer content, pause nightly cron'"
echo "    git push"
echo "    firebase deploy --only hosting"
echo
echo "To undo everything: restore the *.bak-summer files, or just flip"
echo "THEME_OVERRIDE back to None and redeploy."
