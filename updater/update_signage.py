#!/usr/bin/env python3.12
"""
update_signage.py — Run this once a week to refresh the staff-room display.
===========================================================================

What it does, in order:
  1. Pops a native file picker so you can choose this week's bulletin .docx.
  2. Extracts + sanitizes the text, shows you what will be sent, and (with your
     OK) asks the API to structure the events.
  3. Reads the current week's yard duty out of the Google Sheet.
  4. Pops a box where you can type any extra announcements to put on the board.
  5. Writes display/data/signage.json — the file the display reads.

Run it:   python3.12 update_signage.py
   or:    double-click run_update.command  (macOS)

Nothing here is destructive beyond overwriting signage.json (and we keep a
timestamped backup of the previous one, just in case).
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import config


# ---------------------------------------------------------------------------
# Small UI helpers (tkinter). Imported lazily so a missing display server only
# breaks the GUI bits, not `import config` elsewhere.
# ---------------------------------------------------------------------------
def pick_bulletin_file() -> str | None:
    """Native file picker. Returns a path string, or None if cancelled."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()  # we only want the dialog, not a blank window
    root.update()

    start_dir = str(config.BULLETIN_START_DIR) if config.BULLETIN_START_DIR else str(Path.home())
    path = filedialog.askopenfilename(
        title="Choose this week's bulletin",
        initialdir=start_dir,
        filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
    )
    root.destroy()
    return path or None


def collect_announcements() -> list[dict]:
    """
    A simple multiline box for extra announcements — the curated, fuzzy stuff
    the API isn't asked to guess at (curriculum news, reminders, shout-outs).
    One announcement per line. Prefix a line with ! to mark it high-priority
    (the display can style those differently).

    Returns a list of {"text": str, "priority": "high"|"normal"}.
    """
    import tkinter as tk

    captured: dict[str, str] = {"value": ""}

    root = tk.Tk()
    root.title("Extra announcements for the board")
    root.geometry("560x360")

    tk.Label(
        root,
        text=(
            "One announcement per line. These show in the ticker.\n"
            "Start a line with !  to mark it high-priority.\n"
            "Leave blank if there's nothing extra this week."
        ),
        justify="left",
        anchor="w",
        padx=12,
        pady=10,
    ).pack(fill="x")

    text_box = tk.Text(root, wrap="word", height=12)
    text_box.pack(fill="both", expand=True, padx=12)
    text_box.focus_set()

    def done() -> None:
        captured["value"] = text_box.get("1.0", "end").strip()
        root.destroy()

    tk.Button(root, text="Save & continue", command=done).pack(pady=12)
    root.mainloop()

    announcements: list[dict] = []
    for line in captured["value"].splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("!"):
            announcements.append({"text": line[1:].strip(), "priority": "high"})
        else:
            announcements.append({"text": line, "priority": "normal"})
    return announcements


# ---------------------------------------------------------------------------
# Assembly + write
# ---------------------------------------------------------------------------
def build_payload(bulletin_result, duty_result, announcements: list[dict]) -> dict:
    """
    Assemble the JSON the display consumes. We store events flat WITH their
    dates and let the display do the today-relative bucketing ("this week" vs
    "coming up"), so the board stays correct every day of the week without a
    re-run. Theme selection is also the display's job (by date) — we only pass
    an optional manual override.
    """
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "week_of": bulletin_result.week_of,
        "theme_override": config.THEME_OVERRIDE,
        "events": bulletin_result.events,
        "yard_duty": {
            "week_label": duty_result.week_label,
            "assignments": [
                {
                    "post": a.post,
                    "name": a.name,
                    "time": a.time,
                    "where": a.where,
                    "part": a.part,
                }
                for a in duty_result.assignments
            ],
        },
        "announcements": announcements,
        # A small diagnostics block so the display (and you) can see what
        # happened on the last run without digging through a terminal.
        "diagnostics": {
            "sanitize": bulletin_result.sanitize_summary,
            "bulletin_warning": bulletin_result.warning,
            "yard_duty_warning": duty_result.warning,
        },
    }


def write_json(payload: dict) -> None:
    """Write atomically, keeping one timestamped backup of the prior file."""
    target = config.SIGNAGE_JSON
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = target.with_name(f"signage.{stamp}.bak.json")
        shutil.copy2(target, backup)

    # Write to a temp file then move into place so a half-written file can never
    # be served to the display.
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print("\nSOAR signage updater")
    print("--------------------")

    # Imports of the pipeline modules are here (not top-of-file) so the script
    # gives a friendly message if a dependency is missing, rather than a
    # traceback before it even starts.
    import bulletin
    import yard_duty

    path = pick_bulletin_file()
    if not path:
        print("No file chosen. Nothing changed.")
        return 1
    print(f"Bulletin: {path}")

    print("\nParsing bulletin (you'll be asked to approve what's sent)…")
    bulletin_result = bulletin.parse(path)
    print(f"  sanitize: {bulletin_result.sanitize_summary}")
    if bulletin_result.warning:
        print(f"  note:     {bulletin_result.warning}")
    print(f"  events:   {len(bulletin_result.events)} found")

    print("\nReading yard duty from the Sheet…")
    duty_result = yard_duty.fetch_current()
    if duty_result.warning:
        print(f"  note:     {duty_result.warning}")
    print(f"  on duty:  {len(duty_result.assignments)} assignment(s)"
          f"{f' — {duty_result.week_label}' if duty_result.week_label else ''}")

    print("\nOpening the announcements box…")
    announcements = collect_announcements()
    print(f"  added:    {len(announcements)} announcement(s)")

    payload = build_payload(bulletin_result, duty_result, announcements)
    write_json(payload)

    print(f"\n✅  Wrote {config.SIGNAGE_JSON}")
    print("    The display will pick it up on its next refresh (no reload needed).")
    print("\nReminder: git commit your changes before you wrap up for the day.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
