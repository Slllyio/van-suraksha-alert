"""Step 6b: independent truth. On mid-fire Sentinel-2/Landsat photos (burned-so-far at an exact minute; fuel thread's chips,
fuel-map/ratapani/timing/chips, indexed on the UNPADDED burn raster grid), which methods rank burned ground above not-yet-burned?

Everything seen at least 1 h before the photo, within the 4 days before it and 4 km of the chip, is used:
  points       : distance to the nearest VIIRS point (the spread review's honest winner, 'closest to any dot')
  viirs_blocks : distance to the nearest VIIRS block (true scan x track footprint; 0 inside)
  all_blocks   : distance to the nearest block of any sensor (VIIRS + MODIS + earlier S2/Landsat hot pixels)
  kernel       : sum over VIIRS points of exp(-d / 400 m)            (control for the FRP version)
  kernel_frp   : sum over VIIRS points of FRP * exp(-d / 400 m)      (FRP = how much is burning in the block)
  recent_blocks: distance to nearest block, + 15 m per hour since that block was seen (older burning counts less)
Truth: pixels of the final raster scar visible in the photo; burned by the photo (1) or not yet (0).
Sets: all scar pixels; and 'new ground' = pixels outside every VIIRS block seen before the photo.
Score: AUC per photo (0.5 = guessing), averaged; 95% bootstrap over fires for the differences.
Out: results/photo_scores.csv, results/photo_summary.json
"""
import glob, os, json, pickle
import numpy as np, pandas as pd, rasterio, pyproj
from shapely.geometry import Point
from sklearn.metrics import roc_auc_score
ROOT = '/mnt/project-files'; R = f'{ROOT}/research/big-fires/results'
TD = f'{ROOT}/fuel-map/ratapani/timing/'
with rasterio.open(f'{ROOT}/research/ratapani-burn-labels/rasters/burn_2017.tif') as r: TRB = r.transform
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t'])
A['kind'] = np.where(A.sat == 'modis', 'modis', 'viirs')
dflt = np.where(A.kind == 'modis', 1.0, 0.375)
A['hw'] = A.scan.fillna(pd.Series(dflt)) * 500; A['hh'] = A.track.fillna(pd.Series(dflt)) * 500
h = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_*.csv')], ignore_index=True)
h['t'] = pd.to_datetime(h.date + ' ' + h.time_utc); h['x'], h['y'] = tp(h.lon.values, h.lat.values)
h = h.assign(kind='hotpix', hw=15.0, hh=15.0, frp=np.nan)
B = pd.concat([A[['t', 'x', 'y', 'kind', 'hw', 'hh', 'frp']], h[['t', 'x', 'y', 'kind', 'hw', 'hh', 'frp']]], ignore_index=True)
F = pd.read_csv(f'{R}/fires.csv'); S = pickle.load(open(f'{R}/fire_scars.pkl', 'rb'))
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
bigscars = [S[i] for i in F[F.big].fire]
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']

def bdist(X, Y, b):
    dx = np.maximum(np.abs(X[:, None] - b.x.values[None]) - b.hw.values[None], 0)
    dy = np.maximum(np.abs(Y[:, None] - b.y.values[None]) - b.hh.values[None], 0)
    return np.hypot(dx, dy)
def auc(y, s):
    return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan

rows = []
for f in sorted(glob.glob(TD + 'chips/*.npz')):
    b_ = os.path.basename(f); ev = int(b_.split('_')[0]); sc = b_[len(str(ev)) + 1:-4]
    m = ms[(ms.event == ev) & (ms.scene.str[:40] == sc)]
    if not len(m): continue
    m = m.iloc[0]; z = np.load(f); Sm, bym, ok = z['S'], z['bym'], z['ok']; i0, j0 = int(z['i0']), int(z['j0'])
    rr, cc = np.where(Sm & ok)
    if len(rr) < 20: continue
    xs, ys = rasterio.transform.xy(TRB, rr + i0, cc + j0); X, Y = np.array(xs), np.array(ys)
    yb = bym[rr, cc].astype(int)
    if yb.sum() == 0 or yb.all(): continue
    T = pd.Timestamp(m['T']); cx, cy = X.mean(), Y.mean()
    b = B[(B.t <= T - pd.Timedelta(hours=1)) & (B.t >= T - pd.Timedelta(days=4)) &
          (np.abs(B.x - cx) < 4000) & (np.abs(B.y - cy) < 4000)]
    v = b[b.kind == 'viirs']
    if not len(v): continue
    dv_pts = np.hypot(X[:, None] - v.x.values[None], Y[:, None] - v.y.values[None])
    dvb = bdist(X, Y, v); dab = bdist(X, Y, b)
    age = (T - b.t).dt.total_seconds().values / 3600
    sc_ = dict(points=-dv_pts.min(1), viirs_blocks=-dvb.min(1), all_blocks=-dab.min(1),
               kernel=np.exp(-dv_pts / 400).sum(1), kernel_frp=(v.frp.fillna(1).values[None] * np.exp(-dv_pts / 400)).sum(1),
               recent_blocks=-(dab + 15 * age[None]).min(1))
    newg = dvb.min(1) > 0
    big = any(p.contains(Point(cx, cy)) for p in bigscars)
    for setname, msk in [('all', np.ones(len(X), bool)), ('new_ground', newg)]:
        if msk.sum() < 20: continue
        r = dict(event=ev, scene=sc, T=T, season=T.year, big=big, set=setname, n_px=int(msk.sum()), share_burned=yb[msk].mean(),
                 n_viirs=len(v), n_modis=int((b.kind == 'modis').sum()), n_hot=int((b.kind == 'hotpix').sum()),
                 lead_h=(T - v.t.max()).total_seconds() / 3600)
        for k, s in sc_.items(): r[k] = auc(yb[msk], s[msk])
        rows.append(r)
D = pd.DataFrame(rows); D.to_csv(f'{R}/photo_scores.csv', index=False)
meth = ['points', 'viirs_blocks', 'all_blocks', 'recent_blocks', 'kernel', 'kernel_frp']
rng = np.random.default_rng(0); out = {}
for (setname, big), g in list(D.groupby(['set', 'big'])) + [((s, 'any'), D[D.set == s]) for s in D.set.unique()]:
    g = g.dropna(subset=meth)
    key = f'{setname}|{"big" if big is True else ("other" if big is False else "all fires")}'
    res = dict(photos=len(g), fires=g.event.nunique(), mean_auc={k: round(g[k].mean(), 3) for k in meth})
    ev = g.event.unique(); diffs = {k: [] for k in ['viirs_blocks', 'all_blocks', 'recent_blocks', 'kernel_frp']}
    for _ in range(1000):
        sel = rng.choice(ev, len(ev)); gg = pd.concat([g[g.event == e] for e in sel])
        for k in diffs: diffs[k].append((gg[k] - (gg.kernel if k == 'kernel_frp' else gg.points)).mean())
    res['diff_95'] = {(k + (' - kernel' if k == 'kernel_frp' else ' - points')): [round(np.quantile(d, .025), 3), round(np.quantile(d, .975), 3)] for k, d in diffs.items()}
    res['photos_with_modis_or_hotpix_before'] = int(((g.n_modis + g.n_hot) > 0).sum())
    out[key] = res
    print(key, json.dumps(res))
json.dump(out, open(f'{R}/photo_summary.json', 'w'), indent=1, default=str)
