#!/bin/bash
# grass/scrub/sparse (canopy < 10%) load x3 with ROS x2 (fuel thread's inversion), after queue15
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE15_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 30; done
python3 prep_grass.py ../data/rfuel20_loose.npz ../data/rfuel20_loose_g3.npz 3 > ../data/log_prep_grass.txt 2>&1
CFG='{"fuel":"rfuel","rfuel_file":"rfuel20_loose_g3.npz","leaffall":"interp","ros_mult":2,"ign_snap":true,"wind":false,"hours":48,"strict":1,"barriers":true}'
for k in 0 1 2 3; do python3 score.py "$CFG" ../data/res_loose_lfi_m2_g3_$k.parquet 100000 2017,2018,2019,2020,2021,2022,2023,2024 $k/4 > ../data/log_g3_$k.txt 2>&1 & done; wait
echo QUEUE16_DONE >> ../data/log_foot_train.txt
