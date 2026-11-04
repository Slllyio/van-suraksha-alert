@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
set PYTHONUNBUFFERED=1
python e6_fetch_embeddings.py r05c04,r05c02,r05c05,r01c04,r04c07,r02c06,r01c03,r02c03,r03c09,r05c07 32
python e6_fetch_embeddings.py all 32
