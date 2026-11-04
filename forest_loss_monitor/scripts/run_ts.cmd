@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
set PYTHONUNBUFFERED=1
python e18_timeseries.py ccdc ../outputs/timeseries/points_1020.csv ccdc_1020.jsonl
echo FINISHED
