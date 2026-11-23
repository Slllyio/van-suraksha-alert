#!/bin/bash
# audit item 5 (Oct 15): forward test. Models trained on every season 2017-24 ('all') are scored once on the 2025 and 2026 fires
# (multi-satellite events events_viirs_2526.parquet; S-NPP-matched grown outlines grown_scars_2526_snpp.pkl, the rule of grown_scars_viirs.pkl).
# After the fair table (queue27); the barrier runs (queue25/26) wait for this.
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE27_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
export SCAR_GROWN=1
# (a) all-season restart heads (queue29's LOSO train started before the 'all' option existed)
SEASONS=all GROWN_STORE=grown_scars_viirs.pkl nice -n 5 python3 foot_restart.py train ../data/lrg_rows_0.parquet,../data/lrg_rows_1.parquet,../data/lrg_rows_2.parquet,../data/lrg_rows_3.parquet ../data/lrg_models > ../data/log_lrg_train_all.txt 2>&1
export EVENTS_FILE=events_viirs_2526.parquet GROWN_STORE=grown_scars_2526_snpp.pkl
# (b) learned restart, next-pass and end scores on 2025-26 (README 4j style)
for k in 0 1 2 3; do nice -n 5 python3 foot_restart.py score ../data/lrg_models $k/4 ../data/lrg_score_2526_$k.parquet > ../data/log_lrg_score_2526_$k.txt 2>&1 & done; wait
# (c) fair table rows (for the stopping model) and scores on 2025-26 with the 2017-24 heads
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py build $k/4 ../data/fair_rows_2526_$k.parquet > ../data/log_fair_build_2526_$k.txt 2>&1 & done; wait
for k in 0 1 2 3; do nice -n 5 python3 fair_table.py score ../data/fair_models $k/4 ../data/fair_score_2526_$k.parquet > ../data/log_fair_score_2526_$k.txt 2>&1 & done; wait
echo QUEUE31_DONE >> ../data/log_foot_train.txt
