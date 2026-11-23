#!/bin/bash
# after the forward test (queue31, itself after the fair table queue27). FSI thread's barrier layer (Oct 15): (25) learned footprint with barrier features, polygon labels; (26) physics with leaky barriers scored on the polygons
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE32_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
export SCAR_GROWN=1 BARRIERS=1
for k in 0 1 2 3; do nice -n 5 python3 footprint.py build $k/4 ../data/foot_rows_bar_$k.parquet > ../data/log_foot_build_bar_$k.txt 2>&1 & done; wait
nice -n 5 python3 footprint.py train ../data/foot_rows_bar_0.parquet,../data/foot_rows_bar_1.parquet,../data/foot_rows_bar_2.parquet,../data/foot_rows_bar_3.parquet ../data/foot_models_bar > ../data/log_foot_train_bar.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 footprint.py score ../data/foot_models_bar $k/4 ../data/foot_score_bar_$k.parquet > ../data/log_foot_score_bar_$k.txt 2>&1 & done; wait
echo QUEUE25_DONE >> ../data/log_foot_train.txt
unset BARRIERS
for k in 0 1 2 3; do nice -n 5 python3 barrier_phys.py $k/4 ../data/barrier_phys_$k.parquet > ../data/log_barrier_phys_$k.txt 2>&1 & done; wait
echo QUEUE26_DONE >> ../data/log_foot_train.txt
