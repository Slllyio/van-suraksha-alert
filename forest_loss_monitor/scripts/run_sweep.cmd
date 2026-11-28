@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
set PYTHONUNBUFFERED=1
python e18_timeseries.py ccdc ../outputs/timeseries/sweep_points.csv ccdc_sweep.jsonl
python e20_sweep.py review
echo FINISHED
