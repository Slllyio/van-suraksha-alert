@echo off
cd /d E:\FIRE\forest_loss_monitor\scripts
python e67_prithvi.py embed > ..\work\prithvi_embed.log 2>&1
python e63_cascade.py model prithvi tree > ..\work\casc_prithvi_tree.log 2>&1
python e63_cascade.py model ts_same_rows tree > ..\work\casc_tssame_tree.log 2>&1
python e63_cascade.py model ts+prithvi tree > ..\work\casc_tsp_tree.log 2>&1
python e63_cascade.py model prithvi conv > ..\work\casc_prithvi_conv.log 2>&1
python e63_cascade.py model ts_same_rows conv > ..\work\casc_tssame_conv.log 2>&1
echo DONE > ..\work\casc_prithvi_done.log
