#!/bin/bash
# learned restart (foot_restart.py): build -> train -> score, 3-satellite events, LOSO
cd /tmp/claude-0/spread/scripts
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py build $k/4 ../data/lr_rows_$k.parquet > ../data/log_lr_build_$k.txt 2>&1 & done; wait
nice -n 5 python3 foot_restart.py train ../data/lr_rows_0.parquet,../data/lr_rows_1.parquet,../data/lr_rows_2.parquet,../data/lr_rows_3.parquet ../data/lr_models > ../data/log_lr_train.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py score ../data/lr_models $k/4 ../data/lr_score_$k.parquet > ../data/log_lr_score_$k.txt 2>&1 & done; wait
echo QUEUE19_DONE >> ../data/log_foot_train.txt
