#!/bin/bash
# audit item 4 (Oct 15): grid-size sensitivity of the physics at 20 / 40 / 60 m; after queue26
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE26_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
for res in 20 40 60; do
  if [ $res = 20 ]; then unset SPREAD_DATA; else export SPREAD_DATA=/tmp/claude-0/spread/data$res; fi
  for k in 0 1 2 3; do nice -n 5 python3 grid_sens.py run $k/4 ../data/grid_sens_${res}_$k.parquet > ../data/log_grid_sens_${res}_$k.txt 2>&1 & done; wait
done
unset SPREAD_DATA
echo QUEUE28_DONE >> ../data/log_foot_train.txt
