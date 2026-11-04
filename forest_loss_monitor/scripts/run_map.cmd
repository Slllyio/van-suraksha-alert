@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
set PYTHONUNBUFFERED=1
python e8_classify.py v3
python 06_stats_maps.py
echo FINISHED
