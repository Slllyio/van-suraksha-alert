#!/bin/bash
cd /mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2
SC=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r28
while [ ! -f $SC/m2_done.txt ]; do sleep 30; done
python3 m2_cuts.py tr3 oracle > $SC/m2_tr3_oracle.log 2>&1
python3 m2_cuts.py tr2 oracle > $SC/m2_tr2_oracle.log 2>&1
echo ALLDONE >> $SC/m2b_done.txt
