#!/bin/bash
cd /mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2
SC=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r28
timeout 3600 python3 m7_natural.py all5 finalnat > $SC/m7_all5_finalnat.log 2>&1
# any division the pool left behind runs alone
for f in $SC/cuts_all5_final_*.pkl; do k=$(basename $f .pkl); k=${k#cuts_all5_final_}; [ -f $SC/cuts_all5_finalnat_$k.pkl ] || timeout 1200 python3 -c "import sys; sys.path.insert(0,'.'); import m7_natural as N; N.main(('$k','all5','finalnat'))" >> $SC/m7_all5_finalnat.log 2>&1; done
echo FINALNATDONE >> $SC/m7_done.txt
