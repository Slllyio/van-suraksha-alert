#!/usr/bin/env bash
# MP rollout, loop 2: for divisions whose EE pull is done -> OSM proximity (sequential, 3 tries) -> features (max 2).
# Exits when every division with a grid has 11 season tables, or has failed EE / proximity / features 3 times.
S="/c/Users/SC16D6~1.C/AppData/Local/Temp/claude/E--FIRE--claude-worktrees-stoic-lumiere-ab3144/98a7d60a-b194-402f-ab0c-ff840b1d203a/scratchpad"
cd /e/FIRE/mp || exit 1
declare -A ftries ptries
running=()
nseas() { ls "$1"/feats/season_*.parquet 2>/dev/null | wc -l; }
while :; do
  alive=(); for p in "${running[@]}"; do kill -0 "${p%%:*}" 2>/dev/null && alive+=("$p") || echo "$(date +%H:%M) features finished: ${p#*:} ($(nseas ${p#*:})/11)"; done; running=("${alive[@]}")
  pending=0
  for g in */grid_500m.geojson; do
    d=${g%%/*}
    [ "$(nseas "$d")" -ge 11 ] && continue
    if [ ! -f "$d/ee/modis_lst.csv" ]; then
      grep -q Traceback "$d/ee_err.txt" 2>/dev/null && [ -z "$(pgrep -f "mp_ee.py.*$d" 2>/dev/null)" ] && continue
      pending=1; continue
    fi
    if [ ! -f "$d/ee/proximity.csv" ]; then
      [ "${ptries[$d]:-0}" -ge 3 ] && continue
      ptries[$d]=$(( ${ptries[$d]:-0} + 1 ))
      python -I "$S/mp_proximity.py" "E:/FIRE/mp/$d" > "$d/prox_log.txt" 2>&1
      [ -f "$d/ee/proximity.csv" ] && echo "$(date +%H:%M) proximity done: $d" || echo "$(date +%H:%M) proximity try ${ptries[$d]} failed: $d"
      pending=1; continue
    fi
    case " ${running[*]} " in *":$d "*) pending=1; continue;; esac
    [ "${ftries[$d]:-0}" -ge 3 ] && { echo "GIVING UP features: $d"; continue; }
    pending=1
    if [ ${#running[@]} -lt 2 ]; then
      ftries[$d]=$(( ${ftries[$d]:-0} + 1 ))
      python -I "$S/mp_features.py" "E:/FIRE/mp/$d" >> "$d/feat_log.txt" 2>&1 &
      running+=("$!:$d"); echo "$(date +%H:%M) features started: $d"
    fi
  done
  [ $pending -eq 0 ] && [ ${#running[@]} -eq 0 ] && break
  sleep 60
done
echo "post loop finished: $(for g in */grid_500m.geojson; do d=${g%%/*}; [ "$(nseas "$d")" -ge 11 ] && echo x; done | wc -l) divisions complete"
