#!/bin/bash
# Full rerun (unchanged code picks up whatever the statewide scar history holds at the time): ~1-2 h.
set -e
cd "$(dirname "$0")"
SC=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r25
python3 f1_fires.py core > $SC/f1_core.log 2>&1
python3 f1_fires.py rest > $SC/f1_rest.log 2>&1
python3 f2_candidates.py > $SC/f2.log 2>&1
python3 f3_select.py > $SC/f3.log 2>&1
python3 f4_report.py > $SC/f4.log 2>&1
python3 f5_final.py > $SC/f5.log 2>&1
