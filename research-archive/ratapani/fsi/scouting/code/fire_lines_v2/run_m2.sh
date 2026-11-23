#!/bin/bash
cd /mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2
SC=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r28
for v in "tr3 sum" "tr3 med" "tr3 lo" "tr2 med" "tr2 sum"; do
  set -- $v
  python3 m2_cuts.py $1 $2 > $SC/m2_$1_$2.log 2>&1
done
echo ALLDONE >> $SC/m2_done.txt
