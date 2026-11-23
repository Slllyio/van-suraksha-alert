"""Step 6c: every FIRMS field per detection (Akkshay 18:07Z), and whether any of them places the fire better on mid-fire photos.

Fields in fire-alert-scars/alerts/*.csv
  VIIRS: latitude, longitude, bright_ti4 (3.7 um K), bright_ti5 (11 um K), scan, track (pixel size km), acq_date, acq_time,
         satellite, confidence (l/n/h), version, frp (MW), daynight
  MODIS: brightness (4 um), bright_t31 (11 um), scan, track, confidence (0-100), frp, daynight, satellite (Terra/Aqua)
Derived per VIIRS detection:
  frp_area_m2  = FRP / (sigma (Tf^4 - Tb^4)), Tf = 800 K (flaming litter), Tb = bright_ti5 background estimate
  dozier p, Tf = two-channel split: the pixel is a fraction p at fire temperature Tf and (1-p) at background Tb,
                 solved from the I4 and I5 radiances (Dozier 1981). Tb = 10th percentile of bright_ti5 of all
                 Ratapani detections in the same look (proxy: FIRMS gives no background value). I4 saturates at 367 K.
Photo test (same set-up as b6b): VIIRS-point kernels weighted by each field; does any weight beat the unweighted kernel?
Out: results/alert_fields.csv, results/photo_fields_summary.json
"""
import glob, os, json
import numpy as np, pandas as pd, rasterio, pyproj
from scipy.optimize import brentq
from sklearn.metrics import roc_auc_score
ROOT = '/mnt/project-files'; R = f'{ROOT}/research/big-fires/results'; TD = f'{ROOT}/fuel-map/ratapani/timing/'
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
v = pd.concat([pd.read_csv(f).assign(sat=os.path.basename(f).rsplit('_', 1)[0]) for f in glob.glob(f'{ROOT}/fire-alert-scars/alerts/viirs-*.csv')], ignore_index=True)
v = v.dropna(subset=['acq_time'])
v['t'] = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time.astype(int) // 100, 'h') + pd.to_timedelta(v.acq_time.astype(int) % 100, 'min')
v['x'], v['y'] = tp(v.longitude.values, v.latitude.values)
v['scan'] = v.scan.fillna(0.375); v['track'] = v.track.fillna(0.375)
v['look'] = (v.sort_values('t').t.diff() > pd.Timedelta(hours=2)).cumsum().reindex(v.index)
v = v.sort_values('t'); v['look'] = (v.t.diff() > pd.Timedelta(hours=2)).cumsum()
h, c, k = 6.626e-34, 2.998e8, 1.381e-23
def planck(lam, T): return 2 * h * c ** 2 / lam ** 5 / (np.exp(h * c / (lam * k * T)) - 1)
L4, L5 = 3.74e-6, 11.45e-6
v['Tb'] = v.groupby('look').bright_ti5.transform(lambda s: s.quantile(0.1))
sig = 5.67e-8
v['frp_area_m2'] = v.frp * 1e6 / (sig * (800 ** 4 - v.Tb ** 4))
v['pix_m2'] = v.scan * v.track * 1e6
def dozier(T4, T5, Tb):
    if T4 >= 366.9 or T5 <= Tb + 0.05: return np.nan, np.nan
    r4, r5 = planck(L4, T4), planck(L5, T5); b4, b5 = planck(L4, Tb), planck(L5, Tb)
    def f(Tf):
        p = (r5 - b5) / (planck(L5, Tf) - b5); return p * planck(L4, Tf) + (1 - p) * b4 - r4
    try:
        Tf = brentq(f, 400, 2000)
    except ValueError:
        return np.nan, np.nan
    return (r5 - b5) / (planck(L5, Tf) - b5), Tf
pt = [dozier(a, b, c_) for a, b, c_ in zip(v.bright_ti4, v.bright_ti5, v.Tb)]
v['dz_p'] = [p for p, _ in pt]; v['dz_Tf'] = [t for _, t in pt]
v['dz_area_m2'] = v.dz_p * v.pix_m2
v[['latitude', 'longitude', 't', 'sat', 'confidence', 'daynight', 'frp', 'bright_ti4', 'bright_ti5', 'scan', 'track', 'Tb', 'frp_area_m2',
   'dz_p', 'dz_Tf', 'dz_area_m2']].to_csv(f'{R}/alert_fields.csv', index=False)
ok = v.dz_p.notna()
print('VIIRS detections', len(v), '| two-channel split solvable', round(ok.mean(), 2), '| I4 saturated', round((v.bright_ti4 >= 366.9).mean(), 3))
print('burning share of the block from FRP (Tf 800 K): median', round((v.frp_area_m2 / v.pix_m2).median() * 100, 3), '%')
print('two-channel: p median', round(v.dz_p.median() * 100, 3), '%, Tf median', round(v.dz_Tf.median()), 'K; Spearman with FRP area',
      round(v.loc[ok, ['dz_area_m2', 'frp_area_m2']].corr('spearman').iloc[0, 1], 2))
print(v.groupby('daynight')[['frp', 'frp_area_m2', 'dz_p', 'dz_Tf']].median().round(4))
print('Sorted by confidence:', v.groupby('confidence')[['frp', 'bright_ti4']].median().round(1).to_dict())

# photo test with weights
with rasterio.open(f'{ROOT}/research/ratapani-burn-labels/rasters/burn_2017.tif') as r: TRB = r.transform
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
v['w_conf'] = v.confidence.map({'l': 0.5, 'n': 1.0, 'h': 1.5})
v['w_night'] = np.where(v.daynight == 'N', 1.5, 1.0)
v['w_frp'] = v.frp; v['w_dz'] = v.dz_area_m2.fillna(v.dz_area_m2.median())
v['w_smallpix'] = 0.14 / (v.scan * v.track)   # sharper pixels near nadir count more
W = ['none', 'w_conf', 'w_night', 'w_frp', 'w_dz', 'w_smallpix']
rows = []
for f in sorted(glob.glob(TD + 'chips/*.npz')):
    b_ = os.path.basename(f); ev = int(b_.split('_')[0]); sc = b_[len(str(ev)) + 1:-4]
    m = ms[(ms.event == ev) & (ms.scene.str[:40] == sc)]
    if not len(m): continue
    m = m.iloc[0]; z = np.load(f); Sm, bym, okm = z['S'], z['bym'], z['ok']; i0, j0 = int(z['i0']), int(z['j0'])
    rr, cc = np.where(Sm & okm)
    if len(rr) < 20: continue
    xs, ys = rasterio.transform.xy(TRB, rr + i0, cc + j0); X, Y = np.array(xs), np.array(ys)
    yb = bym[rr, cc].astype(int)
    if yb.sum() == 0 or yb.all(): continue
    T = pd.Timestamp(m['T']); cx, cy = X.mean(), Y.mean()
    g = v[(v.t <= T - pd.Timedelta(hours=1)) & (v.t >= T - pd.Timedelta(days=4)) & (np.abs(v.x - cx) < 4000) & (np.abs(v.y - cy) < 4000)]
    if not len(g): continue
    d = np.hypot(X[:, None] - g.x.values[None], Y[:, None] - g.y.values[None]); K = np.exp(-d / 400)
    r = dict(event=ev, T=T, n=len(g))
    for w in W:
        wt = np.ones(len(g)) if w == 'none' else g[w].values
        r[w] = roc_auc_score(yb, (K * wt[None]).sum(1))
    r['points'] = roc_auc_score(yb, -d.min(1))
    rows.append(r)
D = pd.DataFrame(rows)
rng = np.random.default_rng(0); out = dict(photos=len(D), mean_auc={w: round(D[w].mean(), 3) for w in W + ['points']}, diff_vs_unweighted_95={})
for w in W[1:]:
    bs = [(D.sample(len(D), replace=True, random_state=i)[w] - D.none).mean() for i in range(1000)]
    bs = [(lambda s: (s[w] - s['none']).mean())(D.iloc[rng.integers(0, len(D), len(D))]) for _ in range(1000)]
    out['diff_vs_unweighted_95'][w] = [round(np.quantile(bs, .025), 3), round(np.quantile(bs, .975), 3)]
print(json.dumps(out, indent=1))
json.dump(out, open(f'{R}/photo_fields_summary.json', 'w'), indent=1)
