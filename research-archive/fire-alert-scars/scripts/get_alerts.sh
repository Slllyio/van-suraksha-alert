#!/bin/bash
# Download FIRMS yearly India archives (MODIS, VIIRS S-NPP, NOAA-20, NOAA-21) and keep points in the Ratapani bbox (+2 km).
# Usage: get_alerts.sh <outdir>
out=${1:-/mnt/project-files/fire-alert-scars/alerts}; mkdir -p "$out"
for y in $(seq 2017 2026); do for s in modis viirs-snpp viirs-jpss1 viirs-jpss2; do
  f="$out/${s}_${y}.csv"; [ -s "$f" ] && continue
  curl -sS -m 900 --retry 3 "https://firms.modaps.eosdis.nasa.gov/data/country/$s/$y/${s}_${y}_India.csv" \
   | awk -F, 'NR==1 || ($1>22.80 && $1<23.125 && $2>77.32 && $2<78.09)' > "$f.tmp" && mv "$f.tmp" "$f"
  echo "$s $y $(($(wc -l < "$f")-1))"
done; done
