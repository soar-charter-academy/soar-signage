#!/bin/bash
# run_update.command — double-click this in Finder to run the weekly update.
# It just cd's into this folder and runs the updater with python3.12.
cd "$(dirname "$0")" || exit 1
echo "Starting the SOAR signage updater…"
python3.12 update_signage.py
echo ""
echo "Done. You can close this window."
