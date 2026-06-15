#!/usr/bin/env python3
"""Bump all display font sizes for better readability at TV viewing distance.
Run from the repo root: python3 bump_fonts.py
Then verify with: git diff display/style.css
"""
import pathlib

path = pathlib.Path('display/style.css')   # run from repo root
css = path.read_text()
original = css

replacements = [
    # ── Topbar ────────────────────────────────────────────────────────────────
    # SOAR wordmark
    ('font-size: clamp(24px, 2.8vw, 46px);',
     'font-size: clamp(30px, 3.5vw, 58px);'),
    # "End of the Year!" tagline
    ('font-size: clamp(13px, 1.3vw, 22px);',
     'font-size: clamp(16px, 1.7vw, 28px);'),
    # Clock (time)
    ('font-size: clamp(22px, 2.4vw, 40px);',
     'font-size: clamp(28px, 3.1vw, 52px);'),
    # Countdown pill ("3 days to Last Day") — includes trailing context to avoid clock__date
    ('font-size: clamp(11px, 0.9vw, 16px); white-space: nowrap;',
     'font-size: clamp(14px, 1.2vw, 21px); white-space: nowrap;'),

    # ── Now / Up Next banner ──────────────────────────────────────────────────
    # "UP NEXT" / "NOW" label
    ('display: block; font-size: clamp(10px, 0.75vw, 12px);',
     'display: block; font-size: clamp(12px, 0.9vw, 15px);'),
    # Event title inside the banner
    ('font-size: clamp(16px, 1.6vw, 26px); line-height: 1.15;',
     'font-size: clamp(20px, 2.1vw, 34px); line-height: 1.15;'),

    # ── Left column — schedule ────────────────────────────────────────────────
    # "This Week" section header
    ('font-size: clamp(16px, 1.6vw, 28px);',
     'font-size: clamp(20px, 2.1vw, 36px);'),
    # Day name ("TUESDAY", "THURSDAY") — includes trailing context
    ('font-size: clamp(16px, 1.5vw, 26px); text-transform: uppercase; letter-spacing: 0.06em;',
     'font-size: clamp(20px, 2.0vw, 33px); text-transform: uppercase; letter-spacing: 0.06em;'),
    # Day date ("Jun 9") — single-line rule, fully unique
    ('color: var(--text-dim); font-size: clamp(12px, 0.95vw, 16px); }',
     'color: var(--text-dim); font-size: clamp(14px, 1.15vw, 20px); }'),
    # Event time ("5:00p") — includes min-width context
    ('font-size: clamp(14px, 1.2vw, 22px); min-width: clamp(58px, 6vw, 96px);',
     'font-size: clamp(18px, 1.55vw, 28px); min-width: clamp(72px, 7vw, 108px);'),
    # Event title — includes font-weight + flex context
    ('font-size: clamp(15px, 1.3vw, 24px); font-weight: 500; flex: 1; min-width: 0; }',
     'font-size: clamp(19px, 1.65vw, 30px); font-weight: 500; flex: 1; min-width: 0; }'),
    # Event location — single-line rule
    ('.evt__loc { color: var(--text-dim); font-size: clamp(12px, 0.95vw, 17px); }',
     '.evt__loc { color: var(--text-dim); font-size: clamp(14px, 1.15vw, 21px); }'),
    # Event audience — includes white-space context
    ('color: var(--text-dim); font-size: clamp(12px, 0.95vw, 17px);\n  white-space: nowrap; margin-left: auto;',
     'color: var(--text-dim); font-size: clamp(14px, 1.15vw, 21px);\n  white-space: nowrap; margin-left: auto;'),

    # ── Coming-up strip ───────────────────────────────────────────────────────
    # "COMING UP" label — includes flex-shrink context
    ('font-size: clamp(12px, 1vw, 17px); flex-shrink: 0;',
     'font-size: clamp(14px, 1.2vw, 21px); flex-shrink: 0;'),
    # Chip date pill
    ('color: var(--accent); font-weight: 800; font-size: clamp(10px, 0.8vw, 13px);',
     'color: var(--accent); font-weight: 800; font-size: clamp(12px, 1.0vw, 17px);'),
    # Chip title pill
    ('font-weight: 500; font-size: clamp(11px, 0.85vw, 15px);',
     'font-weight: 500; font-size: clamp(13px, 1.05vw, 18px);'),

    # ── Right column — On Duty panel ──────────────────────────────────────────
    # Panel title ("On Duty") — includes letter-spacing context
    ('font-size: clamp(14px, 1.3vw, 22px); letter-spacing: var(--display-tracking);',
     'font-size: clamp(18px, 1.7vw, 28px); letter-spacing: var(--display-tracking);'),
    # Panel sub (week label) — includes font-weight context
    ('color: var(--text-dim); font-size: clamp(10px, 0.8vw, 13px);\n  font-weight: 500;',
     'color: var(--text-dim); font-size: clamp(12px, 1.0vw, 17px);\n  font-weight: 500;'),
    # Group label (MORNING / MIDDAY / AFTERNOON) — includes letter-spacing context
    ('font-size: clamp(12px, 1.05vw, 16px); letter-spacing: 0.14em;',
     'font-size: clamp(14px, 1.3vw, 20px); letter-spacing: 0.14em;'),
    # Duty time ("7:30-7:45a") — includes white-space context
    ('font-size: clamp(13px, 1.15vw, 19px); white-space: nowrap;',
     'font-size: clamp(16px, 1.5vw, 24px); white-space: nowrap;'),
    # Staff name — MOST IMPORTANT — includes min-width context
    ('font-weight: 700; font-size: clamp(16px, 1.55vw, 23px); min-width: 0; }',
     'font-weight: 700; font-size: clamp(20px, 2.0vw, 30px); min-width: 0; }'),
    # Duty location — single-line rule
    ('.duty__where { color: var(--text-dim); font-size: clamp(13px, 1.1vw, 18px); text-align: right; white-space: nowrap; }',
     '.duty__where { color: var(--text-dim); font-size: clamp(16px, 1.4vw, 22px); text-align: right; white-space: nowrap; }'),
    # Duty empty state — single-line rule
    ('.duty__empty { color: var(--text-dim); font-style: italic; font-size: clamp(13px, 1.1vw, 19px); }',
     '.duty__empty { color: var(--text-dim); font-style: italic; font-size: clamp(16px, 1.4vw, 23px); }'),

    # ── Scan / QR panel ───────────────────────────────────────────────────────
    # "House Points" / "Work Order" labels — includes font-weight context
    ('font-weight: 700; font-size: clamp(11px, 0.9vw, 15px);',
     'font-weight: 700; font-size: clamp(14px, 1.15vw, 19px);'),

    # ── TICKER (biggest bump — nearly unreadable at distance) ─────────────────
    # "Notices" tag — includes align-self context to distinguish from clock__date
    ('font-size: clamp(11px, 0.85vw, 15px); align-self: stretch;',
     'font-size: clamp(16px, 1.4vw, 22px); align-self: stretch;'),
    # Ticker item text — single-line rule
    ('.ticker__item { font-size: clamp(12px, 0.95vw, 17px); padding: 10px 0; color: var(--header-text); }',
     '.ticker__item { font-size: clamp(17px, 1.5vw, 26px); padding: 12px 0; color: var(--header-text); }'),
]

ok = 0
for old, new in replacements:
    if old in css:
        css = css.replace(old, new, 1)
        print(f'  OK  {old[:60].strip()!r}')
        ok += 1
    else:
        print(f'  MISS {old[:60].strip()!r}')

path.write_text(css)
print(f'\n{ok}/{len(replacements)} replacements applied.')
if ok == len(replacements):
    print('All good. Run: git diff display/style.css')
else:
    print('Fix MISSes above, then re-run.')
