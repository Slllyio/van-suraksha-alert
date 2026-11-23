#!/bin/bash
cd /tmp/claude-0/spread/scripts
for k in 0 1 2 3; do python3 headtest2.py ../data/rundir.parquet ../data/headtest_$k.parquet $k/4 > ../data/log_headtest_$k.txt 2>&1 & done; wait
python3 - <<'PY'
import pandas as pd, glob
d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob('/tmp/claude-0/spread/data/headtest_[0-9].parquet'))]); d.to_parquet('/tmp/claude-0/spread/data/headtest.parquet')
print('fires', len(d), 'first-pass points median', d.n_pts.median())
for c in [c for c in d.columns if c.startswith('sor_')]:
    print(f'{c:18s} {d[c].mean():.3f}  (n={d[c].notna().sum()})')
big = d[d.scar_px >= 500]; print('scars >= 20 ha:', ', '.join(f'{c[4:]} {big[c].mean():.3f}' for c in ['sor_none_k1', 'sor_run_az_k2', 'sor_run_az_k3', 'sor_mom_az_k2', 'sor_vill_az_k2', 'sor_burn_az_k2', 'sor_fuel_az_k2']))
PY
echo ALLDONE
