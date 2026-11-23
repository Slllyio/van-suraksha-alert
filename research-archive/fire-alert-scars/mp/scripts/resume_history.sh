#!/bin/bash
# Resume the all-MP 2017-25 scar history run if it is not already running (safe to call any time).
if ps -eo args | grep -q "^python3 -W ignore .*mp_run.py .*set_rest_of_mp"; then echo "already running"; exit 0; fi
mkdir -p /tmp/firms
cd /tmp && nohup python3 -W ignore /mnt/project-files/fire-alert-scars/mp/scripts/mp_run.py \
  /mnt/project-files/fire-alert-scars/mp/out/set_rest_of_mp.csv /mnt/project-files/fire-alert-scars/mp/out/scars_mp_hist.csv 16 \
  > /tmp/firms/rest_run.log 2>&1 &
echo "started"
