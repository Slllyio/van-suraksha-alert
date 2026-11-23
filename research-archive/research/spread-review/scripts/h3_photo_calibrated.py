"""Honest chance map calibrated on mid-fire photos only (truth not built from the VIIRS dots).
Pixels from photo_test_box/pixels.parquet (h2 in 'chip' mode with DUMP=1): every pixel of each photo box outside the footprints
seen by issue time; obs = burned by photo time. Season held out (2017-24): each season is scored by a fit on the others.
Methods: (a) closest-dot: isotonic chance from distance to nearest dot; (b) small model on photo pixels (distance first, plus timing,
fire size, land cover, slope; forced to fall with distance); (c) old chance model's score, isotonic-calibrated on photos.
Out: photo_calibrated/summary.json, reliability.csv, preds.parquet"""
import pandas as pd, numpy as np, json, os, lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score
B = '/mnt/project-files/research/spread-review/'; O = B + 'photo_calibrated/'; os.makedirs(O, exist_ok=True)
D = pd.read_parquet(B + 'photo_test_box/pixels.parquet')
D['w'] = 1.0 / D.groupby(['event', 'scene']).obs.transform('size')          # every photo counts the same
F = ['d_all', 'd_last', 'h_since_last', 'silent', 'lead_h', 'n_seen', 'looks_seen', 'frp_max', 'wc', 'slope', 'elev_rel']
mono = [-1 if f in ('d_all', 'd_last') else 0 for f in F]
out = []
for s in sorted(D.season.unique()):
    tr, te = D[D.season != s], D[D.season == s].copy()
    iso = IsotonicRegression(increasing=False, out_of_bounds='clip').fit(tr.d_all, tr.obs, sample_weight=tr.w); te['p_closest'] = iso.predict(te.d_all)
    m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=500, monotone_constraints=mono,
                           verbose=-1).fit(tr[F], tr.obs, sample_weight=tr.w)
    raw_tr = m.predict_proba(tr[F])[:, 1]
    cal = IsotonicRegression(out_of_bounds='clip').fit(raw_tr, tr.obs, sample_weight=tr.w); te['p_photo_model'] = cal.predict(m.predict_proba(te[F])[:, 1])
    iso2 = IsotonicRegression(out_of_bounds='clip').fit(tr.arr, tr.obs, sample_weight=tr.w); te['p_old_model'] = iso2.predict(te.arr)
    out.append(te)
P = pd.concat(out); P.drop(columns=[c for c in P.columns if c not in F + ['obs', 'w', 'season', 'event', 'scene', 'p_closest', 'p_photo_model', 'p_old_model']]).to_parquet(O + 'preds.parquet')
M = ['p_closest', 'p_photo_model', 'p_old_model']; clim = np.average(P.obs, weights=P.w)
R = dict(n_photos=int(P.groupby(['event', 'scene']).ngroups), n_pixels=len(P), share_burned=round(float(clim), 4))
def per_scene(c):
    a, f = [], []
    for _, q in P.groupby(['event', 'scene']):
        if 0 < q.obs.sum() < len(q):
            a.append(roc_auc_score(q.obs, q[c])); k = int(q.obs.sum()); f.append(q.obs.values[np.argsort(-q[c].values, kind='stable')[:k]].mean())
    return np.mean(a), np.mean(f)
bs_ref = np.average((P.obs - clim) ** 2, weights=P.w)
for c in M:
    a, f = per_scene(c)
    R[c] = dict(mean_auc_per_photo=round(a, 3), found_equal_area=round(f, 3), pooled_auc=round(roc_auc_score(P.obs, P[c], sample_weight=P.w), 3),
                brier_skill=round(1 - np.average((P.obs - P[c]) ** 2, weights=P.w) / bs_ref, 3))
# bootstrap by photo: photo-model minus closest-dot
g = {k: q for k, q in P.groupby(['event', 'scene']) if 0 < q.obs.sum() < len(q)}
d = np.array([[roc_auc_score(q.obs, q.p_photo_model) - roc_auc_score(q.obs, q.p_closest),
               roc_auc_score(q.obs, q.p_old_model) - roc_auc_score(q.obs, q.p_closest)] for q in g.values()])
rng = np.random.default_rng(0); bb = np.array([d[rng.integers(0, len(d), len(d))].mean(0) for _ in range(2000)])
R['auc_gain_vs_closest_95ci'] = dict(photo_model=np.percentile(bb[:, 0], [2.5, 97.5]).round(3).tolist(), old_model=np.percentile(bb[:, 1], [2.5, 97.5]).round(3).tolist())
bins = [0, .01, .03, .1, .2, .3, .5, .7, 1.01]; rel = []
for c in M:
    b = pd.cut(P[c], bins, right=False)
    t = P.groupby(b, observed=True).apply(lambda q: pd.Series(dict(said=np.average(q[c], weights=q.w), came_true=np.average(q.obs, weights=q.w), pixels=len(q))))
    rel.append(t.assign(method=c))
pd.concat(rel).to_csv(O + 'reliability.csv')
# what the closest-dot chance looks like: chance by distance band
db = pd.cut(P.d_all, [0, 200, 300, 400, 500, 700, 1000, 1500, 3000])
R['burned_by_distance'] = {str(k): round(float(v), 3) for k, v in P.groupby(db, observed=True).apply(lambda q: np.average(q.obs, weights=q.w)).items()}
json.dump(R, open(O + 'summary.json', 'w'), indent=1); print(json.dumps(R, indent=1)); print(pd.concat(rel).round(3))
