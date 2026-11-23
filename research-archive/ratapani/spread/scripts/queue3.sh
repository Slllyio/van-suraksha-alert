#!/bin/bash
cd /tmp/claude-0/spread/scripts
while pgrep -f "res_cdac_" >/dev/null; do sleep 15; done
./runall.sh rfuel '{"fuel":"rfuel","waf":0.3,"ign_snap":true}'
./runall.sh rfuel_nowind '{"fuel":"rfuel","ign_snap":true,"wind":false}'
./runall.sh rfuel_m3 '{"fuel":"rfuel","ign_snap":true,"wind":false,"ros_mult":3}'
./runall.sh rfuel_viirs '{"fuel":"rfuel","wind":false}'
./runall.sh cdac_sikkim '{"fuel":"rfuel","cdac_params":true,"waf":0.4,"ign_snap":true}'
echo ALLDONE
