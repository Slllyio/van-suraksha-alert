#!/bin/bash
# Oct 16: rescore the fair table against scar outlines v2 (2026-10-16; chip-edge fix). Models unchanged (trained on v1 labels).
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE31_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
SENSORS=viirs-snpp python3 grown_multi.py events_viirs_2526.parquet grown_scars_2526_snpp_v2.pkl > ../data/log_grown_2526_v2.txt 2>&1
export SCAR_GROWN=1 GROWN_STORE=grown_scars_viirs_v2.pkl
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py score ../data/fair_models $k/4 ../data/fair_score_v2_$k.parquet > ../data/log_fair_score_v2_$k.txt 2>&1 & done; wait
export EVENTS_FILE=events_viirs_2526.parquet GROWN_STORE=grown_scars_2526_snpp_v2.pkl
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py score ../data/fair_models $k/4 ../data/fair_score_2526_v2_$k.parquet > ../data/log_fair_score_2526_v2_$k.txt 2>&1 & done; wait
echo QUEUE32_DONE >> ../data/log_foot_train.txt
