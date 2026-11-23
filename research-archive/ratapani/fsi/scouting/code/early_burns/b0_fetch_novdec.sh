#!/bin/bash
# Fetch FIRMS country-archive S-NPP and NOAA-20 India yearly files (no key needed), keep Oct-Dec points in MP bbox.
O=/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd
for sat in viirs-snpp viirs-jpss1; do for y in $(seq 2013 2025); do
  [ $sat = viirs-jpss1 ] && [ $y -lt 2018 ] && continue
  f=$O/${sat}_${y}_ond.csv; [ -s $f ] && continue
  curl -sS --max-time 600 "https://firms.modaps.eosdis.nasa.gov/data/country/${sat#viirs-}/$y/${sat}_${y}_India.csv" -o $O/tmp.csv 2>/dev/null || curl -sS --max-time 600 "https://firms.modaps.eosdis.nasa.gov/data/country/$sat/$y/${sat}_${y}_India.csv" -o $O/tmp.csv
  head -1 $O/tmp.csv > $f
  awk -F, 'NR>1 && $1>=21 && $1<=26.9 && $2>=74 && $2<=82.9 && substr($6,6,2)>="10"' $O/tmp.csv >> $f
  echo $sat $y $(wc -l < $f)
done; done
rm -f $O/tmp.csv
