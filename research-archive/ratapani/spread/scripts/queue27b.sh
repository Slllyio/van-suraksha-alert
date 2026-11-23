#!/bin/bash
# relaunch after the container restart of Oct 15 ~13:30Z: the fair-table rows (build) finished 13:14Z; train and score remained
cd /tmp/claude-0/spread/scripts
nice -n 5 python3 fair_table.py train ../data/fair_rows_0.parquet,../data/fair_rows_1.parquet,../data/fair_rows_2.parquet,../data/fair_rows_3.parquet ../data/fair_models > ../data/log_fair_train.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py score ../data/fair_models $k/4 ../data/fair_score_$k.parquet > ../data/log_fair_score_$k.txt 2>&1 & done; wait
echo QUEUE27_DONE >> ../data/log_foot_train.txt
