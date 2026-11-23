"""Exact VIIRS pixel shapes vs fixed 375 m blocks (Oct 18; Akkshay "what further since we have new data").
Question: does drawing each detection at its real size (FIRMS scan x track, which grows to ~0.8 x 0.7 km at the edge of the swath)
and real centre (fire-mask geolocation, mask_pixels_near_fires.parquet) put the 'already burning' blocks more on burnt ground?
Truth that does NOT depend on the footprint shape: the final scar outline v2 (dom). The blend arrival map is built from scan x track boxes,
so it is not used here (it would favour boxes by construction).
Per forecast issue on the 818 unseen fires (dots seen so far):
  disc    : 265 m disc per dot (today)
  box     : scan x track box per dot (axis-aligned, as c0_lib.footprint)
  mask    : 265 m disc around every fire pixel (cls 7-9) of the same passes in the raw masks (true 03IMG centres; includes pixels FIRMS dropped)
  null    : the disc layer shifted by a random 0-250 m (does any re-placement look like a gain?)
Score: precision = share of footprint on the final scar; recall = share of the scar burned by +24 h (VIIRS-free part: final scar) covered.
"""
import sys, pickle, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from pyproj import Transformer
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
X0, Y0 = 737300.0, 2560500.0
I = pd.read_parquet('/tmp/claude-0/unseen/u_issues.parquet'); M = pickle.load(open('/tmp/claude-0/unseen/u_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
MP = pd.read_parquet('/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/tracking/results/mask_pixels_near_fires.parquet',
                     columns=['fire', 't_pass', 'lat', 'lon', 'cls', 'vza'])
MP = MP[MP.cls >= 7].copy(); MP['t_pass'] = pd.to_datetime(MP.t_pass)
x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(MP.lon.values, MP.lat.values); MP['x'] = x; MP['y'] = y
rng = np.random.default_rng(0); rows = []
for fire, g in I.groupby('fire'):
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); m = MP[MP.fire == fire]
    for it in g.itertuples():
        kn = d[d.lk <= it.k]; xy = kn[['x', 'y']].values; tk = kn.t.max()
        disc = cKDTree(xy).query(P)[0] <= 265
        box = np.zeros(len(P), bool)
        for r in kn.itertuples():
            box |= (np.abs(P[:, 0] - r.x) <= r.scan * 500) & (np.abs(P[:, 1] - r.y) <= r.track * 500)
        mm = m[(m.t_pass <= tk + pd.Timedelta(minutes=10)) & (m.t_pass >= d.t.min() - pd.Timedelta(minutes=10))]
        mk = (cKDTree(mm[['x', 'y']].values).query(P)[0] <= 265) if len(mm) else disc
        sh = rng.uniform(0, 250); a = rng.uniform(0, 2 * np.pi)
        null = cKDTree(xy + [sh * np.cos(a), sh * np.sin(a)]).query(P)[0] <= 265
        o = dict(fire=fire, k=it.k, n_dots=len(xy), n_mask_px=len(mm), scar_ha=dom.sum() * .04, mean_scan=float(kn.scan.mean()))
        for nm, f in [('disc', disc), ('box', box), ('mask', mk), ('null', null)]:
            o[f'{nm}_ha'] = f.sum() * .04; o[f'{nm}_prec'] = float((f & dom).sum() / max(f.sum(), 1)); o[f'{nm}_rec'] = float((f & dom).sum() / max(dom.sum(), 1))
            o[f'{nm}_sor'] = 2 * (f & dom).sum() / max(f.sum() + dom.sum(), 1)
        rows.append(o)
R = pd.DataFrame(rows); R.to_csv('/tmp/claude-0/unseen/pixel_shape.csv', index=False)
res = dict(issues=len(R), fires=int(R.fire.nunique()), mask_pixels_vs_firms_dots=[float(R.n_mask_px.sum()), float(R.n_dots.sum())])
for nm in ['disc', 'box', 'mask', 'null']:
    res[nm] = {k: round(float(R[f'{nm}_{k}'].median()), 4) for k in ['ha', 'prec', 'rec', 'sor']}
f = R.groupby('fire').mean(numeric_only=True)
for nm in ['box', 'mask', 'null']:
    dl = (f[f'{nm}_prec'] - f.disc_prec).values
    res[f'{nm}_minus_disc_prec_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
wide = R[R.mean_scan > .5]
res['wide_pixels_scan>0.5km'] = dict(n=len(wide), **{nm: {k: round(float(wide[f'{nm}_{k}'].median()), 4) for k in ['ha', 'prec', 'sor']} for nm in ['disc', 'box', 'mask']})
json.dump(res, open('/tmp/claude-0/unseen/pixel_shape.json', 'w'), indent=1); print(json.dumps(res, indent=1))
