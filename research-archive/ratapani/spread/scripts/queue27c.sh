#!/bin/bash
# Oct 15 16:40Z: rescore 2017-24 with the spread review's 600 m ring baseline added (heads unchanged, trained 14:15Z)
cd /tmp/claude-0/spread/scripts
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py score ../data/fair_models $k/4 ../data/fair_score_$k.parquet > ../data/log_fair_score_$k.txt 2>&1 & done; wait
echo QUEUE27_DONE >> ../data/log_foot_train.txt
