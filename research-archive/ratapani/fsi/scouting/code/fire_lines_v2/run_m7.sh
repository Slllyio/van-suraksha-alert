#!/bin/bash
cd /mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2
SC=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r28
python3 m7_natural.py tr3 lonat > $SC/m7_tr3_lonat.log 2>&1
echo LONATDONE >> $SC/m7_done.txt
python3 m7_natural.py all5 finalnat > $SC/m7_all5_finalnat.log 2>&1
echo FINALNATDONE >> $SC/m7_done.txt
