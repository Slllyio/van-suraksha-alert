#!/bin/bash
cd /tmp/claude-0/spread/scripts
until ! pgrep -f "headtest[2]" > /dev/null; do sleep 15; done
B='"ign_snap":true,"wind":false,"hours":48,"strict":1,"barriers":true'
./runall.sh loose_lf "{\"fuel\":\"rfuel\",\"rfuel_file\":\"rfuel20_loose.npz\",\"leaffall\":true,$B}"
./runall.sh loose_lf_m15 "{\"fuel\":\"rfuel\",\"rfuel_file\":\"rfuel20_loose.npz\",\"leaffall\":true,\"ros_mult\":1.5,$B}"
./runall.sh m3_lf "{\"fuel\":\"rfuel\",\"leaffall\":true,\"ros_mult\":3,$B}"
echo ALLDONE
