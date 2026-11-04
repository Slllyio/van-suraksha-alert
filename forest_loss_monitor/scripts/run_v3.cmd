@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
set PYTHONUNBUFFERED=1
python e7_score.py v3
python anomalies.py v3
echo FINISHED
