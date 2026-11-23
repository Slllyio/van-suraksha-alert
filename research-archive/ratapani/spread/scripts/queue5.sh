#!/bin/bash
cd /tmp/claude-0/spread/scripts
./runall.sh rfuel '{"fuel":"rfuel","waf":0.3,"ign_snap":true,"hours":48}'
./runall.sh rfuel_nowind '{"fuel":"rfuel","ign_snap":true,"wind":false,"hours":48}'
./runall.sh cdac_sikkim '{"fuel":"rfuel","cdac_params":true,"waf":0.4,"ign_snap":true,"hours":48}'
./runall.sh rfuel_m3 '{"fuel":"rfuel","ign_snap":true,"wind":false,"ros_mult":3,"hours":48}'
./runall.sh rfuel_viirs '{"fuel":"rfuel","wind":false,"hours":48}'
echo ALLDONE
