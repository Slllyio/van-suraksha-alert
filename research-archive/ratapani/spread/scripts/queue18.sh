#!/bin/bash
# per-class right-size variant from the class split of 4b: ROS x1.63 (closed forest sized right) + grass/scrub load x2.5 (grass sized right), after queue17
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE17_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 30; done
python3 prep_grass.py ../data/rfuel20_loose.npz ../data/rfuel20_loose_g25.npz 2.5 > ../data/log_prep_grass25.txt 2>&1
CFG='{"fuel":"rfuel","rfuel_file":"rfuel20_loose_g25.npz","leaffall":"interp","ros_mult":1.63,"ign_snap":true,"wind":false,"hours":48,"strict":1,"barriers":true}'
for k in 0 1 2 3; do python3 score.py "$CFG" ../data/res_loose_lfi_m163_g25_$k.parquet 100000 2017,2018,2019,2020,2021,2022,2023,2024 $k/4 > ../data/log_g25_$k.txt 2>&1 & done; wait
echo QUEUE18_DONE >> ../data/log_foot_train.txt
