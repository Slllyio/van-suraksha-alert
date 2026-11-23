#!/bin/bash
# audit item 1 (Oct 15): honest ROS / load refit against the outlines; after queue28
cd /tmp/claude-0/spread/scripts
until grep -q QUEUE28_DONE ../data/log_foot_train.txt 2>/dev/null; do sleep 60; done
for k in 0 1 2 3; do nice -n 5 python3 ros_sweep.py $k/4 ../data/ros_sweep_$k.parquet > ../data/log_ros_sweep_$k.txt 2>&1 & done; wait
echo QUEUE30_DONE >> ../data/log_foot_train.txt
