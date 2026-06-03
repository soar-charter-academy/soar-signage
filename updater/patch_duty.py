#!/usr/bin/env python3.12
"""patch_duty.py — writes fresh duty data from the Sheet into signage.json,
leaving events and announcements untouched."""
import json, pathlib, sys
from dataclasses import asdict
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from yard_duty import fetch_current

SIGNAGE_JSON = pathlib.Path(__file__).parent.parent / "display" / "data" / "signage.json"

result = fetch_current()

if not result.assignments:
    print(f"No duty data returned: {result.warning}")
    sys.exit(1)

data = json.loads(SIGNAGE_JSON.read_text())
data["yard_duty"] = {
    "week_label": result.week_label or "",
    "assignments": [asdict(a) for a in result.assignments],
}
SIGNAGE_JSON.write_text(json.dumps(data, indent=2))
print(f"✓ {len(result.assignments)} assignments written for {result.week_label}")