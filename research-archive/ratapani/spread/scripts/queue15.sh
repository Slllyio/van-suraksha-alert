#!/bin/bash
# fuel thread's per-class suggestion: ROS x1.4 overall with grass/scrub/sparse load x2.6 (so grass runs ~1.8x faster than closed forest)
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE14_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 30; done
python3 prep_grass.py ../data/rfuel20_loose.npz ../data/rfuel20_loose_g26.npz 2.6 > ../data/log_prep_grass26.txt 2>&1
CFG='{"fuel":"rfuel","rfuel_file":"rfuel20_loose_g26.npz","leaffall":"interp","ros_mult":1.4,"ign_snap":true,"wind":false,"hours":48,"strict":1,"barriers":true}'
for k in 0 1 2 3; do python3 score.py "$CFG" ../data/res_loose_lfi_m14_g26_$k.parquet 100000 2017,2018,2019,2020,2021,2022,2023,2024 $k/4 > ../data/log_g26_$k.txt 2>&1 & done; wait
echo QUEUE15_DONE >> ../data/log_foot_train.txt
