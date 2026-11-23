#!/bin/bash
# Daily all-MP burn-scar update: new alerts -> scars (live.py), and on Mondays the weekly officials' report
# for the 7 days ending Sunday. Output: mp/live/ (ledger) and mp/live/reports/<sunday>/ (report.html, map.png, CSVs).
# Usage: bash daily.sh [force_report]
set -u
D=/mnt/project-files/fire-alert-scars
python3 -c "import matplotlib, markdown" 2>/dev/null || python3 -m pip install -q matplotlib markdown 2>&1 | grep -v WARNING
cd /tmp
python3 -W ignore $D/scripts/live.py $D/mp/mp_beats_aoi.geojson $D/mp/live/ 2>&1 | tail -5
if [ "$(date -u +%u)" = "1" ] || [ "${1:-}" = "force_report" ]; then
  python3 -W ignore $D/mp/scripts/weekly_report.py "$(date -u -d yesterday +%F)" 2>&1 | tail -3
fi
