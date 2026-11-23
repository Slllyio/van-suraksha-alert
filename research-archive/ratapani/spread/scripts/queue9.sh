#!/bin/bash
cd /tmp/claude-0/spread/scripts
for nm in snpp_h viirs all; do
  CB="{\"fuel\":\"rfuel\",\"ign_snap\":true,\"wind\":false,\"ros_mult\":3,\"hours\":48,\"strict\":1,\"barriers\":true,\"events_file\":\"/tmp/claude-0/spread/data/events_$nm.parquet\"}"
  for k in 0 1 2 3; do python3 restart.py "$CB" ../data/restart_$nm\_$k.parquet $k/4 > ../data/log_restart_$nm\_$k.txt 2>&1 & done; wait
  echo "done $nm"
done
echo ALLDONE
