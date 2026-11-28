@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
set PYTHONUNBUFFERED=1
set FLM_VAL=validation2
set FLM_VERSION=v3
python e12_validation.py attrs
python e12_validation.py chips
python e12_validation.py ccdc
python e13_viewer.py assets
echo FINISHED
