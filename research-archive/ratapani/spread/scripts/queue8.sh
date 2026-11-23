#!/bin/bash
cd /tmp/claude-0/spread/scripts
CB='{"fuel":"rfuel","ign_snap":true,"wind":false,"ros_mult":3,"hours":48,"strict":1,"barriers":true}'
./runall.sh m3_barrier "$CB"
for k in 0 1 2 3; do python3 restart.py "$CB" ../data/restart_$k.parquet $k/4 > ../data/log_restart_$k.txt 2>&1 & done; wait
echo ALLDONE
