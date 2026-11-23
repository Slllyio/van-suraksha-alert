#!/bin/bash
# grown scars (scar thread, Oct 15): (20) rescore the raster-trained footprint models against the grown outlines; (21) retrain on grown labels and score
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE19_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 30; done
for k in 0 1 2 3; do SCAR_GROWN=1 nice -n 5 python3 footprint.py score ../data/foot_models $k/4 ../data/foot_score_grown_$k.parquet > ../data/log_foot_score_grown_$k.txt 2>&1 & done; wait
echo QUEUE20_DONE >> ../data/log_foot_train.txt
for k in 0 1 2 3; do SCAR_GROWN=1 nice -n 5 python3 footprint.py build $k/4 ../data/foot_rows_grown_$k.parquet > ../data/log_foot_build_grown_$k.txt 2>&1 & done; wait
SCAR_GROWN=1 nice -n 5 python3 footprint.py train ../data/foot_rows_grown_0.parquet,../data/foot_rows_grown_1.parquet,../data/foot_rows_grown_2.parquet,../data/foot_rows_grown_3.parquet ../data/foot_models_grown > ../data/log_foot_train_grown.txt 2>&1
for k in 0 1 2 3; do SCAR_GROWN=1 nice -n 5 python3 footprint.py score ../data/foot_models_grown $k/4 ../data/foot_score_grown2_$k.parquet > ../data/log_foot_score_grown2_$k.txt 2>&1 & done; wait
echo QUEUE21_DONE >> ../data/log_foot_train.txt
