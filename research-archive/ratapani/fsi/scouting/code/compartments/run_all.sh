#!/bin/bash
# Full rerun of round r27 (compartments inside repeat-burn patches + conference PDF). Needs round-26 scratch (fires, patches,
# rings, entries) and round-25 scratch (candidate chains, corridor plan lines). About 1.5 h on 4 cores.
set -e
cd "$(dirname "$0")"
SC=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r27
python3 k1_cuts.py tr3 > $SC/k1_tr3.log 2>&1
python3 k1_cuts.py all5 > $SC/k1_all5.log 2>&1
python3 k2_score.py lines > $SC/k2_lines.log 2>&1
python3 k2_score.py alloc > $SC/k2_alloc.log 2>&1
python3 k2_score.py score > $SC/k2_score.log 2>&1
python3 k4_report.py > $SC/k4.log 2>&1
python3 k3_final.py > $SC/k3.log 2>&1
python3 k5_mosaic.py > $SC/k5.log 2>&1
python3 k6_figs.py > $SC/k6.log 2>&1
python3 k7_paper.py > $SC/k7.log 2>&1
