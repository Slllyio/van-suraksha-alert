#!/bin/bash
cd /tmp/claude-0/spread/scripts
B='"ign_snap":true,"wind":false,"hours":48,"strict":1,"barriers":true,"rfuel_file":"rfuel20_loose.npz","leaffall":"interp"'
./runall.sh loose_lfi "{\"fuel\":\"rfuel\",$B}"
./runall.sh loose_lfi_m15 "{\"fuel\":\"rfuel\",\"ros_mult\":1.5,$B}"
./runall.sh loose_lfi_m2 "{\"fuel\":\"rfuel\",\"ros_mult\":2,$B}"
echo ALLDONE
