"""Why the C-DAC-style forecast does not reproduce the real burn scars (Oct 17, Akkshay: "critically analyse").
Same 146 big fires, outlines v2, "real" timing = fire-continuity blend map (as in cdac_fronts.py). For the ground burned by +24 h
after the first VIIRS look, and for the whole outline, each row adds one piece of knowledge the forecast lacks:
  phys1     physics from the first look only (what cdac_fronts.py shows)
  phys1_sz  same ranking, but cut at the TRUE burned area (perfect speed)          -> how much is speed/size
  disc1_sz  disc at the first look's dots with the TRUE area                         -> does physics beat a plain disc
  dots      375 m footprints of every look up to +24 h (no model, uses later looks)  -> how much is just "where dots were"
  physR     physics restarted from every look up to +24 h, each at its time (C-DAC's planned restart; uses later looks)
  physR_sz  same, cut at the TRUE area
  discC_sz  disc at the TRUE burned ground's own centre with the TRUE area           -> best possible single blob
Reach: share of the real burned ground more than 600 m / 1 km from every first-look dot (24 h at 25 m/h = 600 m).
  FC_SCRATCH=/tmp/claude-0/fronts python3 gap_analysis.py out.csv
"""
import os, sys, pickle, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
import c0_lib as C
import sim, footprint as fp
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

OUT = sys.argv[1]
BF = '/mnt/project-files/research/big-fires/results'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv').set_index('fire'); L = pd.read_csv(f'{BF}/big_fires_list.csv')
SC = pickle.load(open(f"{os.environ['FC_SCRATCH']}/fire_scars.pkl", 'rb'))
CFG = dict(fp.CFG, ign_snap=False, hours=72); WX = {}


def soren(a, b):
    return 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


def topn(score, n):
    m = np.zeros(score.shape, bool)
    if n <= 0:
        return m
    f = np.where(np.isfinite(score), score, -np.inf).ravel(); idx = np.argpartition(-f, min(n, f.size) - 1)[:n]
    m.ravel()[idx] = True; return m & np.isfinite(score)


def run_phys(dets, s, box, t0, ign_all):
    ev = pd.DataFrame(dict(x=dets.x.values, y=dets.y.values, t=pd.to_datetime(dets.t.values), season=s, overpass=dets.t.min()))
    o = sim.run_event(ev, WX[s], dict(CFG, ign_all=ign_all, win=(box.r0, box.r1, box.c0, box.c1)), hours=96)
    return o['T'] / 60.0 - (t0 - ev.t.min().floor('h')).total_seconds() / 3600


def dist_to(pts, box):
    d = np.full(box.shape, np.inf)
    for x, y in pts:
        d = np.minimum(d, np.hypot(box.X - x, box.Y - y))
    return d


rows = []
for page, fire in enumerate(L.fire.tolist(), 1):
    d = C.viirs_looks(A[A.fire == fire]); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600; s = int(F.season[fire])
    if s not in WX:
        WX.clear(); WX[s] = sim.load_weather(s)
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = C.rc_of(xs.min() - 1500, ys.max() + 1500); r1, c1 = C.rc_of(xs.max() + 1500, ys.min() - 1500)
    box = C.Box(max(int(r0), 0), min(int(r1), C.NR - 1) + 1, max(int(c0), 0), min(int(c1), C.NC - 1) + 1)
    tr = Affine(20, 0, C.X0 + box.c0 * 20, 0, -20, C.Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    T, lo, hi, idx, dmin = C.blend_map(box, dom, d, clock=C.Clock(t0), p=4)
    Tg = np.full(box.shape, np.nan); rr, cc = np.where(dom); Tg[rr, cc] = np.where(np.isfinite(T), T, np.nan)
    first = d[d.lk == 0]; early = d[d.th <= 24]
    Th1 = run_phys(first, s, box, t0, False); ThR = run_phys(early, s, box, t0, True)
    d1 = dist_to(first[['x', 'y']].values, box); dE = dist_to(early[['x', 'y']].values, box)
    r = dict(page=page, fire=fire, outline_ha=dom.sum() * .04, n_looks=int(d.lk.max() + 1), looks_24h=int(early.lk.nunique()), first_dots=len(first))
    for tag, H, real in [('24h', 24, dom & np.isfinite(Tg) & (Tg <= 24)), ('all', 96, dom)]:
        n = int(real.sum()); r[f'{tag}_real_ha'] = n * .04
        if n == 0:
            continue
        yc, xc = box.Y[real].mean(), box.X[real].mean()
        cand = {
            'phys1': np.isfinite(Th1) & (Th1 <= H),
            'phys1_sz': topn(-Th1, n),
            'disc1_sz': topn(-d1, n),
            'dots': dE <= 265 if tag == '24h' else dist_to(d[['x', 'y']].values, box) <= 265,
            'physR': np.isfinite(ThR) & (ThR <= H),
            'physR_sz': topn(-ThR, n),
            'discC_sz': topn(-np.hypot(box.X - xc, box.Y - yc), n)}
        for k, m in cand.items():
            r[f'{tag}_{k}'] = round(soren(m, real), 3)
        r[f'{tag}_phys1_ha'] = cand['phys1'].sum() * .04
        r[f'{tag}_far600'] = round(float((d1[real] > 600).mean()), 3); r[f'{tag}_far1k'] = round(float((d1[real] > 1000).mean()), 3)
    r['outline_far1k_any_dot'] = round(float((dist_to(d[['x', 'y']].values, box)[dom] > 1000).mean()), 3)
    rows.append(r)
    if page % 20 == 0:
        print(page, flush=True); pd.DataFrame(rows).to_csv(OUT, index=False)
pd.DataFrame(rows).to_csv(OUT, index=False); print('done', len(rows))
