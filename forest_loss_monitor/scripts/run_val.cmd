@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
set PYTHONUNBUFFERED=1
python e12_validation.py attrs
python e12_validation.py chips
python e12_validation.py ccdc
echo FINISHED
