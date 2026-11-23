#!/bin/bash
# audit item 2 (Oct 15): honest earlier-burn rule (burns final 25 days after their window end) -> retrain the polygon-truth learned restart (lrg) and learned footprint (foot_models_grown)
cd /tmp/claude-0/spread/scripts
export SCAR_GROWN=1
export GROWN_STORE=grown_scars_viirs.pkl
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py build $k/4 ../data/lrg_rows_$k.parquet > ../data/log_lrg_build_$k.txt 2>&1 & done; wait
nice -n 5 python3 foot_restart.py train ../data/lrg_rows_0.parquet,../data/lrg_rows_1.parquet,../data/lrg_rows_2.parquet,../data/lrg_rows_3.parquet ../data/lrg_models > ../data/log_lrg_train.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py score ../data/lrg_models $k/4 ../data/lrg_score_$k.parquet > ../data/log_lrg_score_$k.txt 2>&1 & done; wait
unset GROWN_STORE
for k in 0 1 2 3; do nice -n 5 python3 footprint.py build $k/4 ../data/foot_rows_grown_$k.parquet > ../data/log_foot_build_grown_$k.txt 2>&1 & done; wait
nice -n 5 python3 footprint.py train ../data/foot_rows_grown_0.parquet,../data/foot_rows_grown_1.parquet,../data/foot_rows_grown_2.parquet,../data/foot_rows_grown_3.parquet ../data/foot_models_grown > ../data/log_foot_train_grown.txt 2>&1
for k in 0 1 2 3; do nice -n 5 python3 footprint.py score ../data/foot_models_grown $k/4 ../data/foot_score_grown2_$k.parquet > ../data/log_foot_score_grown2_$k.txt 2>&1 & done; wait
echo QUEUE29_DONE >> ../data/log_foot_train.txt
