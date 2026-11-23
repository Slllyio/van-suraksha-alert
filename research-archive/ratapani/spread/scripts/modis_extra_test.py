"""Do MODIS Terra/Aqua looks between VIIRS passes improve the 24 h forecast? (Oct 17, Akkshay "Go" on step 2.)
Unseen 818 fires (2+ VIIRS looks). Truth is the VIIRS-only blend map inside outline v2, so MODIS is independent of it.
A forecast is issued at every MODIS look (dets within 1 h) that falls after the first VIIRS dot and has no VIIRS look within 1 h.
Truth = burned by +24 h from the MODIS time. Rules (375 m VIIRS blocks always counted as burned):
  viirs      : dots + 24 ha per active front (fronts with dots in the last 2 VIIRS looks), nearest to VIIRS dots   <- today
  seed       : same area, nearest to VIIRS or MODIS dots
  fresh      : same area, nearest to the MODIS dots first (freshest), then VIIRS
  fresh_n    : active fronts recounted with MODIS (a front is active if MODIS saw it, or it had VIIRS dots in the last 2 looks;
               MODIS clusters > 750 m from any front add a front); placed as 'seed'
  modis_fp   : 'seed' plus MODIS 1 km pixels (500 m radius) counted as burned
  python3 modis_extra_test.py
"""
import sys, pickle, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
X0, Y0 = 737300.0, 2560500.0; MED = 24.1; LINK = 750.0
I = pd.read_parquet('/tmp/claude-0/unseen/u_issues.parquet'); M = pickle.load(open('/tmp/claude-0/unseen/u_maps.pkl', 'rb'))
A0 = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t'])
V = A0[A0.sat != 'modis']; MO = A0[A0.sat == 'modis']
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = cKDTree(xy).query_pairs(LINK, output_type='ndarray')
    g = coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy)))
    return connected_components(g, directed=False)[1]


def sat_of(t):
    h = t.hour
    return 'terra_day' if 3 <= h <= 6 else 'aqua_day' if 7 <= h <= 10 else 'terra_night' if 14 <= h <= 18 else 'aqua_night'


rows = []
for fire in sorted(I.fire.unique()):
    m = MO[MO.fire == fire].sort_values('t')
    if not len(m): continue
    d = C.viirs_looks(V[V.fire == fire]).reset_index(drop=True); t0 = d.t.min()
    m = m[m.t > t0].copy()
    if not len(m): continue
    m['lk'] = (m.t.diff().dt.total_seconds().fillna(1e9) > 3600).cumsum()
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    for lk, g in m.groupby('lk'):
        tm = g.t.max()
        if ((d.t - tm).abs() <= pd.Timedelta(hours=1)).any(): continue
        kn = d[d.t <= tm]; th = (tm - t0).total_seconds() / 3600
        k = kn.lk.max(); xy = kn[['x', 'y']].values; mxy = g[['x', 'y']].values
        truth = dom & (Tg <= th + 24); new = dom & (Tg > th) & (Tg <= th + 24)
        lab = clusters(xy); act = set(lab[(kn.lk >= k - 1).values])
        dd = cKDTree(xy).query(P)[0]; dm = cKDTree(mxy).query(P)[0]; foot = dd <= 265
        # recount active fronts with MODIS
        dmf = cKDTree(xy).query(mxy)[0]; seen = set(lab[cKDTree(xy).query(mxy)[1][dmf <= LINK]])
        extra = len(np.unique(clusters(mxy[dmf > LINK]))) if (dmf > LINK).any() else 0
        n_act, n_act2 = len(act), len(act | seen) + extra
        hrs_since_v = th - kn.th.max() if 'th' in kn else (tm - kn.t.max()).total_seconds() / 3600
        out = dict(fire=fire, sat=sat_of(tm), hours_since_viirs=round((tm - kn.t.max()).total_seconds() / 3600, 1), n_modis=len(g),
                   modis_far=int((dmf > LINK).sum()), n_act=n_act, n_act_modis=n_act2, truth_ha=truth.sum() * .04, new_ha=new.sum() * .04)
        def place(score, n, base=foot):
            s = np.where(base, -1, score); mk = np.zeros(len(s), bool); mk[np.argsort(s, kind='stable')[:n]] = True; return mk
        n = int(foot.sum() + MED * n_act / .04)
        out['viirs'] = so(place(dd, n), truth)
        out['seed'] = so(place(np.minimum(dd, dm), n), truth)
        out['fresh'] = so(place(np.where(dm <= dd + 1e-9, dm, dd + 5000), n), truth)
        out['fresh_n'] = so(place(np.minimum(dd, dm), int(foot.sum() + MED * n_act2 / .04)), truth)
        f2 = foot | (dm <= 500); out['modis_fp'] = so(place(np.minimum(dd, dm), int(f2.sum() + MED * n_act / .04), f2), truth)
        out['viirs_area_fp'] = so(place(dd, int(f2.sum() + MED * n_act / .04)), truth)   # control: same total area as modis_fp, VIIRS only
        out['viirs_area_n'] = so(place(dd, int(foot.sum() + MED * n_act2 / .04)), truth)  # control: same area as fresh_n, VIIRS only
        out['area_fp_ha'] = (f2.sum() - foot.sum()) * .04
        out['blocks_only'] = so(foot, truth)
        # does MODIS point at new burning? share of next-24 h new burning within 500 m of MODIS vs of the latest VIIRS look
        last = kn[kn.lk == k][['x', 'y']].values; dl = cKDTree(last).query(P)[0]
        if new.sum():
            out['new_within500_modis'] = float((dm[new] <= 500).mean()); out['new_within500_lastviirs'] = float((dl[new] <= 500).mean())
        rows.append(out)
R = pd.DataFrame(rows); R.to_csv('/tmp/claude-0/modis/modis_extra.csv', index=False)
cols = ['blocks_only', 'viirs', 'seed', 'fresh', 'fresh_n', 'viirs_area_n', 'modis_fp', 'viirs_area_fp']
rng = np.random.default_rng(0); res = dict(forecasts=len(R), fires=int(R.fire.nunique()))
def summ(U):
    o = dict(n=len(U), fires=int(U.fire.nunique()))
    for c in cols: o[c] = round(float(U[c].median()), 4)
    f = U.groupby('fire')[cols].mean()
    for c, b in [('seed', 'viirs'), ('fresh', 'viirs'), ('fresh_n', 'viirs'), ('modis_fp', 'viirs'), ('fresh_n', 'viirs_area_n'), ('modis_fp', 'viirs_area_fp')]:
        dl = (f[c] - f[b]).values; c = f'{c}_vs_{b}'
        o[f'{c}_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
        o[f'{c}_better/worse_fires'] = [int((dl > .005).sum()), int((dl < -.005).sum())]
    o['area_fp_ha'] = round(float(U.area_fp_ha.median()), 1)
    o['new_within500_modis'] = round(float(U.new_within500_modis.median()), 3); o['new_within500_lastviirs'] = round(float(U.new_within500_lastviirs.median()), 3)
    return o
res['all'] = summ(R)
for s, U in R.groupby('sat'): res[s] = summ(U)
res['modis_far_new_front'] = summ(R[R.modis_far > 0]) if (R.modis_far > 0).sum() > 10 else None
res['median_hours_since_viirs'] = float(R.hours_since_viirs.median())
json.dump(res, open('/tmp/claude-0/modis/modis_extra.json', 'w'), indent=1); print(json.dumps(res, indent=1))
