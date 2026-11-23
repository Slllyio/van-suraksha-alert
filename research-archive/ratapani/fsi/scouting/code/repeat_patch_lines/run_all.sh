#!/bin/bash
# Full rerun of round r26 (repeat-burn patches, entry sides, entry-side lines). Needs round-25 code (../fire_lines) and its
# scratch r25 (round-25 road candidates and plan lines, for the comparisons). ~1 h, mostly reading the statewide outlines.
set -e
cd "$(dirname "$0")"
SC=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r26
python3 r1_fires.py core > $SC/r1_core.log 2>&1
python3 r1_fires.py rest > $SC/r1_rest.log 2>&1
python3 r2_patches.py > $SC/r2.log 2>&1
python3 r3_entries.py tr3 > $SC/r3_tr3.log 2>&1
python3 r3_entries.py all5 > $SC/r3_all5.log 2>&1
python3 r4_test.py tr3 > $SC/r4_tr3.log 2>&1
python3 r4_test.py all5 > $SC/r4_all5.log 2>&1
python3 r5_report.py > $SC/r5.log 2>&1
python3 r6_figs.py > $SC/r6.log 2>&1
