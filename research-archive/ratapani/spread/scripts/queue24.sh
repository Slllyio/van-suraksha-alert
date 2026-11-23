#!/bin/bash
# learned restart with far-side distances (pixel footprint edge farthest from the earlier passes), polygon end labels, after queue23
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE23_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
export SCAR_GROWN=1 GROWN_STORE=grown_scars_viirs.pkl EVENTS_FILE=events_viirs_st.parquet FAR_SIDE=1
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py build $k/4 ../data/lrf_rows_$k.parquet > ../data/log_lrf_build_$k.txt 2>&1 & done; wait
nice -n 5 python3 foot_restart.py train ../data/lrf_rows_0.parquet,../data/lrf_rows_1.parquet,../data/lrf_rows_2.parquet,../data/lrf_rows_3.parquet ../data/lrf_models > ../data/log_lrf_train.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py score ../data/lrf_models $k/4 ../data/lrf_score_$k.parquet > ../data/log_lrf_score_$k.txt 2>&1 & done; wait
echo QUEUE24_DONE >> ../data/log_foot_train.txt
