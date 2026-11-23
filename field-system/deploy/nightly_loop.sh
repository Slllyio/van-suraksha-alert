#!/usr/bin/env bash
# Sleeps until 17:15 IST (11:45 UTC), runs scripts/cloud_daily.sh, repeats. Off season the runner only refreshes inputs.
cd "$(dirname "$0")/../scripts"
while true; do
  now=$(date -u +%s); t=$(date -u -d "today 11:45" +%s)
  [ "$now" -ge "$t" ] && t=$(date -u -d "tomorrow 11:45" +%s)
  sleep $((t - now))
  ./cloud_daily.sh || echo "$(date -u +%FT%TZ) cloud_daily.sh exit $?"
done
