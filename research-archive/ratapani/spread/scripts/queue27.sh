#!/bin/bash
# audit item 1 (Oct 15): fair comparison at fixed leads; rows with physics -> LOSO heads -> scoring; after queue29 (honest earlier-burn rule)
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE29_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py build $k/4 ../data/fair_rows_$k.parquet > ../data/log_fair_build_$k.txt 2>&1 & done; wait
nice -n 5 python3 fair_table.py train ../data/fair_rows_0.parquet,../data/fair_rows_1.parquet,../data/fair_rows_2.parquet,../data/fair_rows_3.parquet ../data/fair_models > ../data/log_fair_train.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py score ../data/fair_models $k/4 ../data/fair_score_$k.parquet > ../data/log_fair_score_$k.txt 2>&1 & done; wait
echo QUEUE27_DONE >> ../data/log_foot_train.txt
