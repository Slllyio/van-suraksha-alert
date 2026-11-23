"""Lean the 24 h forecast along the 30 m Sentinel-2/Landsat arrow (burnt-so-far patch -> live hot line; big-fires README 15e, 51% within
45 deg vs 25% chance). Oct 17, coordinator relay after Akkshay "whatever we have now use those data and improve the system".
Scenes: fuel-map/ratapani/timing/chips/*.npz (20 m: S final scar, bym burned by scene minute, hot 30 m hot pixels; midscar.parquet time T).
Matched to the unseen fires: VIIRS dots of the fire within 1.5 km of the chip's scar and the scene inside the fire's dot span +-12 h.
Forecast issued at the scene time T with VIIRS dots seen up to T; truth = burned by T + 24 h (VIIRS-only blend map inside outline v2, so
independent of the scene). Same added area for all rules = 24.1 ha per active front (dots in the last 2 VIIRS looks before T).
  rule      : nearest to VIIRS dots (blocks burned)                                               <- today (0.477 overall)
  lean      : distance scaled by (1 - 0.5 cos(angle to the arrow)) around every dot (cheaper ahead, dearer behind)
  hot       : 30 m hot pixels added as seeds
  hot_lean  : both
  hot_burnt : hot seeds, and the scene's burnt patch counted as burned (plus the same added area)
  python3 s2_arrow_test.py
"""
import sys, glob, os, pickle, json, numpy as np, pandas as pd, rasterio
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
T0 = '/mnt/project-files/fuel-map/ratapani/timing'; X0, Y0 = 737300.0, 2560500.0; MED = 24.1; LINK = 750.0; DTH = float(os.environ.get('DTH', .10))
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as s: TR = s.transform
MS = pd.read_parquet(f'{T0}/midscar.parquet'); MS = MS[MS.status == 'ok']
PRE = os.environ.get('PRE', '/tmp/claude-0/unseen/u'); I = pd.read_parquet(f'{PRE}_issues.parquet'); M = pickle.load(open(f'{PRE}_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[(A.sat != 'modis') & A.fire.isin(I.fire.unique())]
tree = cKDTree(A[['x', 'y']].values)
_ar = pd.read_csv('/tmp/claude-0/unseen/area_model.csv'); ARa = {(int(a), int(b)): float(c) for a, b, c in zip(_ar.fire, _ar.k, _ar['mean'])}
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]


rows = []; seen = set()
for f in sorted(glob.glob(f'{T0}/chips/*.npz')):
    ev = int(os.path.basename(f).split('_')[0]); scene = os.path.basename(f)[len(str(ev)) + 1:-4]
    m = MS[(MS.event == ev) & (MS.scene.str[:40] == scene)]
    if m.empty: continue
    T = pd.Timestamp(m.iloc[0]['T']); z = np.load(f); S, B, H = z['S'], z['bym'] & z['S'], z['hot']
    if B.sum() < 10 or H.sum() < 3: continue
    rr, cc = np.mgrid[0:S.shape[0], 0:S.shape[1]]
    X = TR.c + (z['j0'] + cc + .5) * 20; Y = TR.f - (z['i0'] + rr + .5) * 20
    sxy = np.c_[X[S], Y[S]]
    idx = np.unique(np.concatenate(tree.query_ball_point(sxy[::max(len(sxy) // 200, 1)], 1500)))
    if not len(idx): continue
    cand = A.iloc[idx]; best = None
    for fire, g in cand.groupby('fire'):
        if g.t.min() - pd.Timedelta(hours=12) <= T <= A[A.fire == fire].t.max() + pd.Timedelta(hours=12):
            if best is None or len(g) > best[1]: best = (fire, len(g))
    if best is None or (best[0], str(T)) in seen: continue
    fire = best[0]; seen.add((fire, str(T)))
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min(); kn = d[d.t <= T].reset_index(drop=True)
    if not len(kn): continue
    th = (T - t0).total_seconds() / 3600; k = kn.lk.max(); xy = kn[['x', 'y']].values
    lab = clusters(xy); nact = len(set(lab[(kn.lk >= k - 1).values]))
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    gr, gc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (gc + .5) * 20).ravel(), (Y0 - (gr + .5) * 20).ravel()]
    truth = dom & (Tg <= th + 24); new = dom & (Tg > th) & (Tg <= th + 24)
    hxy = np.c_[X[H], Y[H]]; bxy = np.c_[X[B], Y[B]]; arrow = hxy.mean(0) - bxy.mean(0); au = arrow / max(np.hypot(*arrow), 1)
    dd, ni = cKDTree(xy).query(P); foot = dd <= 265; dh = cKDTree(hxy).query(P)[0]
    v = P - xy[ni]; cosv = (v @ au) / np.maximum(np.hypot(v[:, 0], v[:, 1]), 1)
    burnt = cKDTree(bxy).query(P)[0] <= 15
    n = int(foot.sum() + MED * nact / .04)
    def place(score, base, n):
        s = np.where(base, -1, score); mk = np.zeros(len(s), bool); mk[np.argsort(s, kind='stable')[:n]] = True; return mk
    lean = dd * (1 - .5 * cosv); hs = np.minimum(dd, dh)
    out = dict(fire=fire, event=ev, scene=scene, T=str(T), hours_since_first_dot=round(th, 1), viirs_looks=int(k + 1), n_active=nact,
               new24_ha=new.sum() * .04, burnt_scene_ha=B.sum() * .04, hot_px=int(H.sum()))
    out['rule'] = so(place(dd, foot, n), truth); out['lean'] = so(place(lean, foot, n), truth)
    out['hot'] = so(place(hs, foot, n), truth); out['hot_lean'] = so(place(np.minimum(lean, dh), foot, n), truth)
    fb = foot | burnt; out['hot_burnt'] = so(place(hs, fb, int(fb.sum() + MED * nact / .04)), truth)
    dm = z['dmid'].astype(float); BL = (np.isfinite(dm) & (dm >= DTH)) | H        # live: mid-scene NBR drop only, no final scar, no post scene
    lab_, nl = __import__('scipy.ndimage', fromlist=['label']).label(BL)
    if nl:   # keep patches touching the hot pixels or within 300 m of a VIIRS dot (drop field-edge noise)
        keep = [i for i in range(1, nl + 1) if (H & (lab_ == i)).any() or cKDTree(xy).query(np.c_[X[lab_ == i], Y[lab_ == i]])[0].min() <= 300]
        BL = np.isin(lab_, keep)
    braw = np.c_[X[BL], Y[BL]]
    br = (cKDTree(braw).query(P)[0] <= 15) if len(braw) else np.zeros(len(P), bool); fr = foot | br
    out['hot_burnt_raw'] = so(place(hs, fr, int(fr.sum() + MED * nact / .04)), truth)
    out['rule_same_area_as_raw'] = so(place(dd, foot, int(fr.sum() + MED * nact / .04)), truth)
    la = ARa.get((fire, int(k)))                                       # learned 24 h area (section 17) for this look
    if la is not None:
        out['learned_area'] = so(place(dd, foot, int(foot.sum() + la / .04)), truth)
        out['learned_area_scene'] = so(place(hs, fr, int(fr.sum() + la / .04)), truth)
        out['learned_area_same_area_as_scene'] = so(place(dd, foot, int(fr.sum() + la / .04)), truth)
    fA = place(hs, fr, int(fr.sum() + MED * nact / .04)); fB = place(dd, foot, int(fr.sum() + MED * nact / .04)); fC = place(dd, foot, n)
    nn = max(new.sum(), 1); out['newcap_scene'] = float((fA & new).sum() / nn); out['newcap_rule_same_area'] = float((fB & new).sum() / nn); out['newcap_rule'] = float((fC & new).sum() / nn)
    nx = new & ~br; nnx = max(nx.sum(), 1); out['newx_ha'] = nx.sum() * .04
    out['newxcap_scene'] = float((fA & nx).sum() / nnx); out['newxcap_rule_same_area'] = float((fB & nx).sum() / nnx)
    out['burnt_raw_ha'] = br.sum() * .04; out['burnt_raw_in_truth'] = float((br & truth).sum() / max(br.sum(), 1))
    al = (braw.mean(0) if len(braw) else bxy.mean(0)); a2 = hxy.mean(0) - al; a2 = a2 / max(np.hypot(*a2), 1)
    c2 = (v @ a2) / np.maximum(np.hypot(v[:, 0], v[:, 1]), 1); out['lean_live'] = so(place(dd * (1 - .5 * c2), foot, n), truth)
    out['rule_same_area_as_hot_burnt'] = so(place(dd, foot, int(fb.sum() + MED * nact / .04)), truth)
    rows.append(out)
R = pd.DataFrame(rows); R.to_csv(f'{PRE}_combined_scene.csv', index=False)
cols = ['rule', 'lean', 'hot', 'hot_lean', 'hot_burnt', 'rule_same_area_as_hot_burnt', 'hot_burnt_raw', 'rule_same_area_as_raw', 'burnt_raw_in_truth', 'burnt_raw_ha', 'lean_live', 'newcap_scene', 'newcap_rule_same_area', 'newcap_rule', 'newxcap_scene', 'newxcap_rule_same_area', 'newx_ha']
res = dict(scenes=len(R), fires=int(R.fire.nunique()), median_new24_ha=float(R.new24_ha.median()))
U = R[R.new24_ha >= 1]; res['scenes_with_>=1ha_new_burning'] = len(U)
rng = np.random.default_rng(0)
for name, Z in [('all', R), ('new>=1ha', U), ('early_<=2_looks', R[R.viirs_looks <= 2])]:
    o = dict(n=len(Z))
    for c in cols: o[c] = round(float(Z[c].median()), 4)
    f = Z.groupby('fire')[cols].mean()
    for c, b in [('lean', 'rule'), ('lean_live', 'rule'), ('hot', 'rule'), ('hot_lean', 'rule'), ('hot_burnt', 'rule_same_area_as_hot_burnt'), ('hot_burnt_raw', 'rule_same_area_as_raw'), ('newcap_scene', 'newcap_rule_same_area'), ('newxcap_scene', 'newxcap_rule_same_area')]:
        dl = (f[c] - f[b]).values
        if len(dl) > 3:
            o[f'{c}_vs_{b}_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
            o[f'{c}_vs_{b}_better/worse'] = [int((dl > .005).sum()), int((dl < -.005).sum())]
    res[name] = o
json.dump(res, open(f'{PRE}_combined_scene.json', 'w'), indent=1); print(json.dumps(res, indent=1))
