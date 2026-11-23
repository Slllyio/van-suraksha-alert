#!/bin/bash
# VIIRS footprint instead of point (fuel thread's timing finding): free run and restarts with the final model, S-NPP events
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE16_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 30; done
BASE='"fuel":"rfuel","rfuel_file":"rfuel20_loose.npz","leaffall":"interp","ros_mult":2,"wind":false,"hours":48,"strict":1,"barriers":true'
for v in point fp snap; do
  case $v in point) EXTRA='"ign_snap":false';; fp) EXTRA='"ign_snap":false,"ign_fp":true';; snap) EXTRA='"ign_snap":true';; esac
  CFG="{$BASE,$EXTRA}"
  for k in 0 1 2 3; do python3 restart.py "$CFG" ../data/restart_final_$v\_$k.parquet $k/4 > ../data/log_restart_final_$v\_$k.txt 2>&1 & done; wait
done
CFG="{$BASE,\"ign_snap\":false,\"ign_fp\":true}"
for k in 0 1 2 3; do python3 score.py "$CFG" ../data/res_loose_lfi_m2_fp_$k.parquet 100000 2017,2018,2019,2020,2021,2022,2023,2024 $k/4 > ../data/log_fp_$k.txt 2>&1 & done; wait
echo QUEUE17_DONE >> ../data/log_foot_train.txt
