@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
python e63_cascade.py model ts tree > ..\work\casc_ts_tree.log 2>&1
python e63_cascade.py model emb tree > ..\work\casc_emb_tree.log 2>&1
python e63_cascade.py model both tree > ..\work\casc_both_tree.log 2>&1
python e63_cascade.py model ts conv > ..\work\casc_ts_conv.log 2>&1
python e63_cascade.py model both conv > ..\work\casc_both_conv.log 2>&1
echo DONE > ..\work\casc_done.log
