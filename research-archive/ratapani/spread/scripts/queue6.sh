#!/bin/bash
cd /tmp/claude-0/spread/scripts
until grep -q ALLDONE ../data/run5.log; do sleep 20; done
for k in 0 1 2 3; do python3 hybrid_data.py '{"fuel":"rfuel","wind":false,"ros_mult":3}' ../data/hyb_$k.parquet $k/4 > ../data/log_hyb_$k.txt 2>&1 & done; wait
echo HYBDONE
