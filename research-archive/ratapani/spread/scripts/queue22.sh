#!/bin/bash
# learned restart with the grown outlines as the end label and truth (Akkshay 09:01Z "go ahead"), after queue21
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE21_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
export SCAR_GROWN=1 GROWN_STORE=grown_scars_viirs.pkl
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py build $k/4 ../data/lrg_rows_$k.parquet > ../data/log_lrg_build_$k.txt 2>&1 & done; wait
nice -n 5 python3 foot_restart.py train ../data/lrg_rows_0.parquet,../data/lrg_rows_1.parquet,../data/lrg_rows_2.parquet,../data/lrg_rows_3.parquet ../data/lrg_models > ../data/log_lrg_train.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py score ../data/lrg_models $k/4 ../data/lrg_score_$k.parquet > ../data/log_lrg_score_$k.txt 2>&1 & done; wait
echo QUEUE22_DONE >> ../data/log_foot_train.txt
