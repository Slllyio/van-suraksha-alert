#!/bin/bash
cd /tmp/claude-0/spread/scripts
until grep -q ALLDONE ../data/run12.log; do sleep 15; done
./runall.sh teakmix '{"fuel":"rfuel","rfuel_file":"rfuel20_teakmix.npz","ign_snap":true,"wind":false,"hours":48}'
./runall.sh teakmix_lfi_m15 '{"fuel":"rfuel","rfuel_file":"rfuel20_teakmix.npz","leaffall":"interp","ros_mult":1.5,"ign_snap":true,"wind":false,"hours":48,"strict":1,"barriers":true}'
echo ALLDONE
