"""Summarise rundir.parquet: how one-sided real scars are relative to the first detection, and which direction
cue agrees with the run direction. Usage: rundir_stats.py rundir.parquet"""
import numpy as np, pandas as pd, sys
d = pd.read_parquet(sys.argv[1])
print(f'{len(d)} scarred fires (>= 5 ha). scar elongation (sd along / sd across): median {d.elong.median():.2f}, q25-q75 {d.elong.quantile(.25):.2f}-{d.elong.quantile(.75):.2f}')
print(f'position of first detections along the scar axis (0 = at an end, 0.5 = centre): median {d.u_first.median():.2f}; in the end fifth (<0.2) {(d.u_first < 0.2).mean():.0%}; near the centre (>0.4) {(d.u_first > 0.4).mean():.0%}')
print(f'run (first detections -> scar centroid): median {d.run_m.median():.0f} m; > 300 m in {(d.run_m > 300).mean():.0%}, > 500 m in {(d.run_m > 500).mean():.0%}; scar 95% extent from the first detections median {d.ext95_m.median():.0f} m')
print(f'share of scar pixels more than 1 km from every detection of the event: median {d.far_frac.median():.0%}, mean {d.far_frac.mean():.0%}; fires with > 50% far: {(d.far_frac > 0.5).mean():.0%}')
for lab, sub in [('all', d), ('scar >= 20 ha', d[d.scar_px >= 500]), ('2022-24', d[d.season >= 2022])]:
    print(f'  [{lab}] n={len(sub)}: u_first median {sub.u_first.median():.2f}, run median {sub.run_m.median():.0f} m, elong {sub.elong.median():.2f}, far {sub.far_frac.mean():.0%}')
m = d[d.run_m > 300].copy()
print(f'\nDirection cues vs the real run direction, fires with run > 300 m (n={len(m)}); random = cos 0.00, 25% within 45 deg, 50% within 90 deg')
for cue, lab in [('edge_az', 'away from nearest non-fuel within 500 m (land cover, water, built, earlier burn, road)'), ('lc_az', 'away from non-vegetation land cover within 500 m'),
                 ('burn_az', "away from this season's earlier burns within 500 m"), ('road_az', 'away from roads within 500 m'), ('vill_az', 'away from built-up within 1 km'),
                 ('fuel_az', 'toward the burnable fuel mass within 1 km'), ('down_az', 'downslope at the first detections'), ('wind_az', 'ERA5 wind direction (toward), first 24 h'),
                 ('mom_az', 'first pass -> second pass (momentum; needs 2 passes)')]:
    x = m.dropna(subset=[cue]); diff = np.abs((x[cue] - x.run_az + 180) % 360 - 180)
    extra = ''
    if cue == 'down_az':
        s = x[x.slope_deg >= 5]; ds = np.abs((s[cue] - s.run_az + 180) % 360 - 180); extra = f' | slope >= 5 deg (n={len(s)}): cos {np.cos(np.radians(ds)).mean():+.2f}, {(ds <= 45).mean():.0%} / {(ds <= 90).mean():.0%}'
    if cue == 'wind_az':
        s = x[x.wind_ms >= 2]; ds = np.abs((s[cue] - s.run_az + 180) % 360 - 180); extra = f' | wind >= 2 m/s (n={len(s)}): cos {np.cos(np.radians(ds)).mean():+.2f}, {(ds <= 45).mean():.0%} / {(ds <= 90).mean():.0%}'
    if cue in ('edge_az', 'burn_az', 'road_az'):
        dc = {'edge_az': 'edge_d', 'burn_az': 'burn_d', 'road_az': 'road_d'}[cue]; s = x[x[dc] <= 200]; ds = np.abs((s[cue] - s.run_az + 180) % 360 - 180)
        extra = f' | centroid within 200 m (n={len(s)}): cos {np.cos(np.radians(ds)).mean():+.2f}, {(ds <= 45).mean():.0%} / {(ds <= 90).mean():.0%}'
    print(f'  {lab:85s} n={len(x):4d}: mean cos {np.cos(np.radians(diff)).mean():+.2f}, within 45 deg {(diff <= 45).mean():.0%}, within 90 deg {(diff <= 90).mean():.0%}{extra}')
# the scar axis vs the first-pass front line (axis, 0-180)
x = m.dropna(subset=['front_az']); da = np.abs((x.front_az - x.scar_axis_az + 90) % 180 - 90)
print(f'\nscar long axis vs first-pass detection line (n={len(x)}): within 30 deg {(da <= 30).mean():.0%} (random 33%)')
print(f'night-first fires {d.night_first.mean():.0%}; run median night {d[d.night_first==1].run_m.median():.0f} m vs day {d[d.night_first==0].run_m.median():.0f} m')
