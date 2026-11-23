#!/bin/bash
# extra Sentinel-3 date ranges (Dec 10 - Jan 31, Jun 1 - Jun 20) for one season
y=$1; p=$((y-1))
cd "$(dirname "$0")"
python3 -I s3pull.py $p-12-10 $y-01-31 ../r9data/s3syn_$y >> ../r9data/s3pull_${y}_x.log 2>&1
python3 -I s3pull.py $y-06-01 $y-06-20 ../r9data/s3syn_$y >> ../r9data/s3pull_${y}_x.log 2>&1
