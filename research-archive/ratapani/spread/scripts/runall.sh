#!/bin/bash
# usage: runall.sh name 'cfgjson' [seasons]
cd /tmp/claude-0/spread/scripts
S=${3:-2017,2018,2019,2020,2021,2022,2023,2024}
for k in 0 1 2 3; do python3 score.py "$2" ../data/res_$1_$k.parquet 100000 $S $k/4 > ../data/log_$1_$k.txt 2>&1 & done
wait
python3 -c "
import pandas as pd,glob; d=pd.concat([pd.read_parquet(f) for f in sorted(glob.glob('../data/res_$1_[0-9].parquet'))]); d.to_parquet('../data/res_$1.parquet'); print('$1', len(d))"
