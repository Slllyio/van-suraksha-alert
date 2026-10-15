#!/usr/bin/env bash
# MP rollout, loop 1: Earth Engine pulls for every division folder that has a grid but no MODIS LST yet, 9 at a time.
S="/c/Users/SC16D6~1.C/AppData/Local/Temp/claude/E--FIRE--claude-worktrees-stoic-lumiere-ab3144/98a7d60a-b194-402f-ab0c-ff840b1d203a/scratchpad"
cd /e/FIRE/mp || exit 1
todo=()
for g in */grid_500m.geojson; do d=${g%%/*}; [ -f "$d/ee/modis_lst.csv" ] || todo+=("$d"); done
echo "EE todo: ${#todo[@]} divisions"
for ((k = 0; k < ${#todo[@]}; k += 9)); do
  pids=()
  for d in "${todo[@]:k:9}"; do
    python -I "$S/mp_ee.py" "E:/FIRE/mp/$d" static alphaearth era5 modis lst > "$d/ee_log.txt" 2> "$d/ee_err.txt" &
    pids+=($!)
  done
  wait "${pids[@]}"
  for d in "${todo[@]:k:9}"; do
    if [ -f "$d/ee/modis_lst.csv" ]; then echo "$(date +%H:%M) EE done: $d"; else echo "$(date +%H:%M) EE FAILED: $d"; fi
  done
done
echo "EE loop finished"
