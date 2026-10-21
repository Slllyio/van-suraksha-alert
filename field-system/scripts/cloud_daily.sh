#!/usr/bin/env bash
# Evening run of the officials' 2-day list and big-fire watch list (scripts/cloud_daily.py).
# Started at 17:15 IST by deploy/cloud-daily.timer. Retries every 20 min while the exit code says
# "try again" (2 = list not sent, 4 = big-fire list failed) and it is before 19:15 IST; the app's
# /api/v1/health reports a missing list from 19:45 IST.
# Exit codes of cloud_daily.py: 0 sent or nothing to issue, 2 daily not sent, 3 stale inputs/errors (sent,
# officials warned in the status file), 4 big-fire list failed.
set -u
cd "$(dirname "$0")"
LOG_DIR="${CD_LOG_DIR:-../logs/cloud_daily}"
mkdir -p "$LOG_DIR"
day=$(TZ=Asia/Kolkata date +%F)
: "${FS_URL:?FS_URL (the app, e.g. https://host) must be set}"
for try in 1 2 3 4 5 6 7; do
  timeout 5400 python3 cloud_daily.py --date "$day" --post "$FS_URL" >> "$LOG_DIR/$day.log" 2>&1
  rc=$?
  echo "$(date -u +%FT%TZ) try $try exit $rc" >> "$LOG_DIR/$day.log"
  case $rc in
    0|3) exit $rc ;;
  esac
  [ "$(TZ=Asia/Kolkata date +%H%M)" \> "1915" ] && exit $rc
  sleep 1200
done
exit $rc
