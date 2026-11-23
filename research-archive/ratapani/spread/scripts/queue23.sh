#!/bin/bash
# direction of the learned footprint (grown-trained models, grown truth) after queue22
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE22_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
for k in 0 1 2 3; do SCAR_GROWN=1 nice -n 5 python3 footprint.py score ../data/foot_models_grown $k/4 ../data/foot_score_dir_$k.parquet > ../data/log_foot_score_dir_$k.txt 2>&1 & done; wait
echo QUEUE23_DONE >> ../data/log_foot_train.txt
