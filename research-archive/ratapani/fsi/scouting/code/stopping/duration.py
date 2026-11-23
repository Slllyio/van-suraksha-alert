"""Fire duration / extinction stats for Ratapani from FIRMS VIIRS points (S-NPP, NOAA-20, NOAA-21).
Clusters detections into fires (FEDS/GFA-like: link if within LINK_M and within GAP_H hours of a detection
already in the fire), then: duration distribution, passes, P(fire re-detected | k consecutive missed passes,
FRP, day/night), last-detection hour, and daily RH (NASA POWER) on ending vs continuing fire-days."""
import glob, json, sys
import numpy as np, pandas as pd
from shapely.geometry import shape, Point
from shapely.prepared import prep
from scipy.spatial import cKDTree

LINK_M = float(sys.argv[1]) if len(sys.argv) > 1 else 1000
GAP_H = float(sys.argv[2]) if len(sys.argv) > 2 else 48
aoi = prep(shape(json.load(open('/mnt/project-files/ratapani/ratapani_aoi.geojson'))['features'][0]['geometry']))
fs = glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv')
d = pd.concat([pd.read_csv(f, dtype={'acq_time': str}).assign(sat=f.split('/')[-1].split('_')[0]) for f in fs])
d = d[d.type.fillna(0) != 3]
d['t'] = pd.to_datetime(d.acq_date + ' ' + d.acq_time.str.zfill(4), format='%Y-%m-%d %H%M')  # UTC
d['tl'] = d.t + pd.Timedelta(hours=5.5)
d['inaoi'] = [aoi.contains(Point(x, y)) for x, y in zip(d.longitude, d.latitude)]
d = d[d.inaoi & d.tl.dt.month.isin([1, 2, 3, 4, 5, 6])].copy()
# merge 2026 duplicates of Dec rows not relevant (season months only)
d = d.sort_values('t').reset_index(drop=True)
lat0 = 23.0
d['x'] = (d.longitude - 77.7) * 111320 * np.cos(np.radians(lat0)); d['y'] = (d.latitude - lat0) * 110540
th = (d.t - d.t.min()).dt.total_seconds().values / 3600
# overpass id: satellite + time rounded to 20 min
d['pass'] = d.sat + '_' + d.t.dt.floor('20min').astype(str)
# union-find
par = np.arange(len(d))
def f(i):
    while par[i] != i:
        par[i] = par[par[i]]; i = par[i]
    return i
tree = cKDTree(np.c_[d.x, d.y])
pairs = tree.query_pairs(LINK_M, output_type='ndarray')
dt = np.abs(th[pairs[:, 0]] - th[pairs[:, 1]])
for a, b in pairs[dt <= GAP_H]:
    ra, rb = f(a), f(b)
    if ra != rb: par[ra] = rb
d['fire'] = [f(i) for i in range(len(d))]
# NOTE: transitive linking can chain; acceptable for stats (same as GFA/FEDS behaviour)
g = d.groupby('fire')
fire = pd.DataFrame({'n': g.size(), 't0': g.t.min(), 't1': g.t.max(), 'npass': g['pass'].nunique(),
                     'maxfrp': g.frp.max(), 'sumfrp': g.frp.sum(), 'yr': g.tl.min().dt.year})
fire['dur_h'] = (fire.t1 - fire.t0).dt.total_seconds() / 3600
print(f'LINK {LINK_M} m GAP {GAP_H} h: {len(d)} detections in AOI Jan-Jun, {len(fire)} fires')
print('passes per fire:', fire.npass.value_counts().sort_index().head(8).to_dict(), ' share single-pass %.1f%%' % (100 * (fire.npass == 1).mean()))
for q in [0.5, 0.75, 0.9, 0.95, 0.99]:
    print(' dur quantile %.2f: %.1f h' % (q, fire.dur_h.quantile(q)))
m = fire.npass > 1
print(' multi-pass fires: %d, median dur %.1f h, p90 %.1f h' % (m.sum(), fire.dur_h[m].median(), fire.dur_h[m].quantile(.9)))
for lo, hi in [(0, 5), (5, 15), (15, 50), (50, 1e9)]:
    s = fire[(fire.maxfrp >= lo) & (fire.maxfrp < hi)]
    print(f'  maxFRP {lo}-{hi}: n={len(s)}, single-pass {100*(s.npass==1).mean():.0f}%, median dur {s.dur_h.median():.1f} h, >24h {100*(s.dur_h>24).mean():.0f}%, >48h {100*(s.dur_h>48).mean():.1f}%')
# Overpass schedule: all passes of each satellite that saw anything in the AOI (proxy for "the box was viewed")
P = d.groupby('pass').agg(t=('t', 'min'), sat=('sat', 'first'), dn=('daynight', 'first')).sort_values('t').reset_index()
# fill: satellites that existed. Add passes inferred: if a satellite has detections in the AOI on that day/half-day, it viewed the box.
pt = (P.t - d.t.min()).dt.total_seconds().values / 3600
# Survival after a detection: for each fire, each detection-pass p, count passes of the schedule after p until next detection of the same fire
rows = []
for fid, gg in g:
    ps = sorted(set(gg['pass']))
    tps = P.set_index('pass').loc[ps, 't'].values
    frp_by_pass = gg.groupby('pass').frp.max()
    dn_by_pass = gg.groupby('pass').daynight.first()
    for i, p in enumerate(ps):
        t0 = tps[i]
        tnext = tps[i + 1] if i + 1 < len(ps) else None
        # schedule passes in the following 48 h
        sel = (P.t.values > t0) & (P.t.values <= t0 + np.timedelta64(48, 'h'))
        later = P[sel]
        if tnext is not None:
            missed = int(((later.t.values > t0) & (later.t.values < tnext)).sum())
            gap = (tnext - t0) / np.timedelta64(1, 'h')
        else:
            missed = len(later); gap = np.nan
        rows.append(dict(fire=fid, frp=frp_by_pass[p], frp_cum=gg[gg.t <= t0].frp.max(), dn=dn_by_pass[p],
                         hour=(pd.Timestamp(t0) + pd.Timedelta(hours=5.5)).hour, redet=tnext is not None,
                         missed=missed, gap=gap, k_avail=len(later), npass_so_far=i + 1, t=pd.Timestamp(t0)))
R = pd.DataFrame(rows)
print('\nAfter a detection pass: share re-detected later %.1f%% (n=%d)' % (100 * R.redet.mean(), len(R)))
# P(redetected later | k passes already missed): among steps where at least k passes followed silently
print('P(fire seen again | k silent passes since last detection), by FRP of last pass:')
out = {}
for k in range(0, 7):
    elig = R[R.k_avail > k]  # at least k+? passes available
    alive = elig[(elig.redet) & (elig.missed >= k)]
    dead = elig[(~elig.redet)]
    # survived k silent passes: redet with missed>=k, or never redetected
    tot = len(alive) + len(dead)
    line = f' k={k}: all {100*len(alive)/max(tot,1):.1f}% (n={tot})'
    for lo, hi in [(0, 5), (5, 15), (15, 1e9)]:
        e = elig[(elig.frp_cum >= lo) & (elig.frp_cum < hi)]
        a = ((e.redet) & (e.missed >= k)).sum(); dd = (~e.redet).sum()
        line += f' | cumFRP {lo}-{hi}: {100*a/max(a+dd,1):.1f}% (n={a+dd})'
    print(line)
    out[k] = 100 * len(alive) / max(tot, 1)
for dn in ['D', 'N']:
    e = R[R.dn == dn]
    print(f' last pass {dn}: P(seen again) {100*e.redet.mean():.1f}% n={len(e)}; given 1 silent pass: '
          f'{100*((e.redet)&(e.missed>=1)).sum()/max(((e.redet)&(e.missed>=1)).sum()+(~e.redet).sum(),1):.1f}%')
print(' by number of passes seen so far:', R.groupby(R.npass_so_far.clip(upper=5)).redet.mean().round(3).to_dict())
# Hour of last detection vs all detections
last = d.loc[d.groupby('fire').t.idxmax()]
multi_ids = fire.index[fire.npass > 1]
lm = last[last.fire.isin(multi_ids)]
print('\nlast-detection day/night (multi-pass fires):', lm.daynight.value_counts(normalize=True).round(3).to_dict(),
      ' all detections:', d.daynight.value_counts(normalize=True).round(3).to_dict())
# Weather: daily RH on ending day vs continuing fire-days (by local date)
W = pd.read_parquet('/mnt/project-files/ratapani/weather_power_daily.parquet'); W['date'] = pd.to_datetime(W.date)
d['ld'] = d.tl.dt.normalize()
fd = d.groupby(['fire', 'ld']).size().reset_index()[['fire', 'ld']]
fd['last'] = fd.groupby('fire').ld.transform('max') == fd.ld
fd = fd[fd.fire.isin(multi_ids)]
fd = fd.merge(W, left_on='ld', right_on='date', how='left')
nxt = W.copy(); nxt['date'] = nxt.date - pd.Timedelta(days=1)
fd = fd.merge(nxt[['date', 'rh_pct', 'precip_mm', 'temp_c', 'wind_kmh']].rename(columns=lambda c: c + '_next' if c != 'date' else 'date'), left_on='ld', right_on='date', how='left')
print('\nFire-days of multi-pass fires: last day vs continuing day (NASA POWER daily, sanctuary-wide):')
print(fd.groupby('last')[['rh_pct', 'rh_pct_next', 'temp_c', 'wind_kmh', 'precip_mm_next']].mean().round(2))
from sklearn.metrics import roc_auc_score
ok = fd.dropna(subset=['rh_pct_next'])
print(' AUC of next-day RH for "this is the last day":', round(roc_auc_score(ok['last'], ok.rh_pct_next), 3),
      ' of same-day RH:', round(roc_auc_score(ok['last'], ok.rh_pct), 3), ' month AUC:', round(roc_auc_score(ok['last'], -ok.ld.dt.month), 3))
fire.to_csv(f'/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/stop_code/fires_{int(LINK_M)}_{int(GAP_H)}.csv')
R.to_csv(f'/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/stop_code/steps_{int(LINK_M)}_{int(GAP_H)}.csv', index=False)
