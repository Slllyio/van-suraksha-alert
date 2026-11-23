#!/bin/bash
# wait for the feature build, then train, score, the grass x3 physics test and the Rethink-style cell scoring
cd /tmp/claude-0/spread/scripts
until [ -f ../data/foot_rows_0.parquet ] && [ -f ../data/foot_rows_1.parquet ] && [ -f ../data/foot_rows_2.parquet ] && [ -f ../data/foot_rows_3.parquet ]; do sleep 15; done
python3 footprint.py train ../data/foot_rows_0.parquet,../data/foot_rows_1.parquet,../data/foot_rows_2.parquet,../data/foot_rows_3.parquet ../data/foot_models > ../data/log_foot_train.txt 2>&1
for k in 0 1 2 3; do python3 footprint.py score ../data/foot_models $k/4 ../data/foot_score_$k.parquet > ../data/log_foot_score_$k.txt 2>&1 & done; wait
python3 prep_grass.py ../data/rfuel20_loose.npz ../data/rfuel20_loose_g3.npz 3 > ../data/log_prep_grass.txt 2>&1
CFG='{"fuel":"rfuel","rfuel_file":"rfuel20_loose_g3.npz","leaffall":"interp","ros_mult":2,"ign_snap":true,"wind":false,"hours":48,"strict":1,"barriers":true}'
for k in 0 1 2 3; do python3 score.py "$CFG" ../data/res_loose_lfi_m2_g3_$k.parquet 100000 2017,2018,2019,2020,2021,2022,2023,2024 $k/4 > ../data/log_g3_$k.txt 2>&1 & done; wait
for k in 0 1 2 3; do python3 foot_cells.py score ../data/rf ../data/foot_models $k/4 ../data/rf_scores_$k.parquet > ../data/log_rf_score_$k.txt 2>&1 & done; wait
python3 foot_cells.py eval ../data/rf ../data/rf_scores_0.parquet,../data/rf_scores_1.parquet,../data/rf_scores_2.parquet,../data/rf_scores_3.parquet > ../data/log_rf_eval.txt 2>&1
echo QUEUE14_DONE >> ../data/log_foot_train.txt
