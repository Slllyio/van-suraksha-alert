"""Experiment 4: negative evidence, "the satellite looked here and saw no fire".
FIRMS lists only fire pixels; the pixels that were looked at and found clear are not in the file. Approximation:
- a VIIRS pass "looked at Ratapani" when that satellite has detections in the MP-wide archive (alerts_mp) within 250 km of
  Ratapani at that pass, or on both sides of it (Ratapani then lies inside the 3,000 km swath). Clouds are unknown
  (assumed clear; Feb-May is mostly cloud-free) and night/day both count;
- a pass is "active on this fire" when that same pass flagged at least one pixel of the fire (so the fire area was in view
  and not cloud-hidden), and a 20 m pixel is "seen, no fire" at that pass when it lies outside every footprint of the pass.
Test on the mid-fire photos, with every season held out in turn:
  forecast (only passes >= 1 h before the photo) and reconstruction (passes before and after), logistic models on
  distance features alone vs distance + negative-evidence counts. Score: per-photo AUC and pixel accuracy.
"""
import glob, json, os
import numpy as np, pandas as pd, pyproj
from sklearn.linear_model import LogisticRegression
from s_lib import *
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
fn = f'{SC}/viewing_passes.parquet'
if not os.path.exists(fn):
    out = []
    for f in sorted(glob.glob(f'{ROOT}/fire-alert-scars/alerts_mp/viirs-*.csv')):
        a = pd.read_csv(f, usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'scan', 'track'])
        a['t'] = pd.to_datetime(a.acq_date) + pd.to_timedelta(a.acq_time.astype(int) // 100, 'h') + pd.to_timedelta(a.acq_time.astype(int) % 100, 'min')
        a = a.sort_values('t'); a['p'] = (a.t.diff().dt.total_seconds().fillna(1e9) > 900).cumsum()
        dist = np.hypot((a.longitude - 77.7) * 102, (a.latitude - 22.95) * 111)
        a['near'] = dist < 250; a['w'] = a.longitude < 77.7
        g = a.groupby('p').agg(t=('t', 'median'), near=('near', 'any'), west=('w', 'any'), east=('w', lambda s: (~s).any()),
                               scan=('scan', lambda s: s[a.loc[s.index, 'near']].mean()))
        g = g[g.near | (g.west & g.east)]; g['sensor'] = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}[os.path.basename(f).split('_')[0]]
        out.append(g[['t', 'sensor', 'scan']])
    pd.concat(out).to_parquet(fn)
VP = pd.read_parquet(fn)
D = load_det(); V = D[(D.kind == 'viirs') & (D.type.fillna(0) != 2)]
PH = photos()
def feats(ph, d, T, mode):
    """Per photo pixel features from the fire's VIIRS passes. mode 'forecast': passes <= T-1h; 'recon': all."""
    X, Y = ph['X'], ph['Y']
    th = (d.t - T).dt.total_seconds().values / 3600
    fd = foot_dist(X, Y, d)       # (px, det)
    pid = d.pass_id.values; up = np.unique(pid)
    inP = np.stack([(fd[:, pid == p] <= 0).any(1) for p in up], 1)          # pixel inside a footprint of pass p
    dP = np.stack([fd[:, pid == p].min(1) for p in up], 1)                  # distance to pass p's footprints
    tP = np.array([th[pid == p].min() for p in up])
    bef = tP <= -1; aft = tP > 0
    F = {}
    dm_b = np.where(bef[None], dP, np.inf).min(1); F['ld_before'] = np.log(np.minimum(dm_b, 5000) + 20)
    dp = np.hypot(X[:, None] - d.x.values[None], Y[:, None] - d.y.values[None])
    F['kern_before'] = np.exp(-dp[:, th <= -1] / 400).sum(1)
    near = dP <= 1500                                                         # the pass saw this fire within 1.5 km of the pixel
    neg = (~inP) & near
    F['neg_before'] = (neg & bef[None]).sum(1); F['pos_before'] = (inP & bef[None]).sum(1)
    # last pass before the photo that saw the fire near this pixel: was the pixel inside (1) or seen clear (0)?
    lastb = np.where(near & bef[None], tP[None], -np.inf).argmax(1); has = (near & bef[None]).any(1)
    F['neg_last_before'] = np.where(has, neg[np.arange(len(X)), lastb], 0).astype(float)
    F['neg_after_first_pos'] = ((neg & bef[None]) & (np.cumsum(inP & bef[None], 1) > 0)).sum(1)    # seen clear after it had burned there
    if mode == 'recon':
        dm_a = np.where(aft[None], dP, np.inf).min(1); F['ld_after'] = np.log(np.minimum(dm_a, 5000) + 20)
        F['neg_after'] = (neg & aft[None]).sum(1); F['pos_after'] = (inP & aft[None]).sum(1)
        firsta = np.where(near & aft[None], tP[None], np.inf).argmin(1); hasa = (near & aft[None]).any(1)
        F['neg_first_after'] = np.where(hasa, neg[np.arange(len(X)), firsta], 0).astype(float)
        # nearest-look rule (continuity): time of the nearest footprint; ties -> earliest
        dmin = fd.min(1, keepdims=True); tnn = np.where(fd <= dmin + 1e-6, th[None], np.inf).min(1)
        F['nn_burned'] = (tnn <= 0).astype(float); F['tnn'] = np.clip(tnn, -48, 48) / 12
    return pd.DataFrame(F)
res = {}
for mode in ['forecast', 'recon']:
    rows = []
    for k, ph in enumerate(PH):
        y, T = ph['y'], ph['T']
        if y.sum() == 0 or y.all(): continue
        d = V[(V.fire == ph['fire'])]
        if mode == 'forecast': d = d[d.t <= T - pd.Timedelta(hours=1)]
        if not len(d) or (d.t <= T - pd.Timedelta(hours=1)).sum() == 0: continue
        Fx = feats(ph, d, T, mode); Fx['y'] = y; Fx['photo'] = k; Fx['season'] = ph['season']; Fx['fire'] = ph['fire']
        rows.append(Fx)
    Z = pd.concat(rows, ignore_index=True)
    base = ['ld_before', 'kern_before'] + (['ld_after', 'nn_burned', 'tnn'] if mode == 'recon' else [])
    negc = ['neg_before', 'pos_before', 'neg_last_before', 'neg_after_first_pos'] + (['neg_after', 'pos_after', 'neg_first_after'] if mode == 'recon' else [])
    for c in negc: Z[c] = np.log1p(Z[c]) if c.startswith(('neg_b', 'pos', 'neg_after')) and c not in ('neg_last_before', 'neg_first_after') else Z[c]
    pr = {m: np.zeros(len(Z)) for m in ['base', 'neg']}
    for s in Z.season.unique():
        tr, te = Z.season != s, Z.season == s
        for m, cols in [('base', base), ('neg', base + negc)]:
            # weight photos equally
            w = 1 / Z.loc[tr].groupby('photo').y.transform('size')
            mdl = LogisticRegression(max_iter=2000, C=1.0).fit(Z.loc[tr, cols], Z.loc[tr, 'y'], sample_weight=w)
            pr[m][te.values] = mdl.predict_proba(Z.loc[te, cols])[:, 1]
    Z['p_base'], Z['p_neg'] = pr['base'], pr['neg']
    per = Z.groupby('photo').apply(lambda g: pd.Series(dict(fire=g.fire.iloc[0], auc_base=auc(g.y, g.p_base), auc_neg=auc(g.y, g.p_neg),
                                                         acc_base=((g.p_base > .5) == g.y).mean(), acc_neg=((g.p_neg > .5) == g.y).mean(),
                                                         acc_nn=((g.nn_burned > .5) == g.y).mean() if 'nn_burned' in g else np.nan,
                                                         share_neg=(g.neg_before > 0).mean()))).reset_index()
    per.to_csv(f'{OUT}/e4_{mode}_per_photo.csv', index=False)
    mdl = LogisticRegression(max_iter=2000).fit((Z[base + negc] - Z[base + negc].mean()) / Z[base + negc].std(), Z.y)
    r = dict(photos=len(per), pixels=len(Z), pixels_with_any_seen_clear_before=round(float((Z.neg_before > 0).mean()), 3),
             auc_base=round(per.auc_base.mean(), 4), auc_with_negative=round(per.auc_neg.mean(), 4), auc_diff_95=boot_diff(per, 'auc_neg', 'auc_base'),
             acc_base=round(per.acc_base.mean(), 4), acc_with_negative=round(per.acc_neg.mean(), 4), acc_diff_95=boot_diff(per, 'acc_neg', 'acc_base'),
             std_weights=dict(zip(base + negc, np.round(mdl.coef_[0], 3))))
    if mode == 'recon': r['acc_nearest_look_rule'] = round(per.acc_nn.mean(), 4)
    # simple univariate: among pixels at the same distance band, burned share when last pass saw it clear vs inside/no info
    Z['band'] = pd.cut(np.exp(Z.ld_before) - 20, [-1, 1, 200, 400, 700, 1500, 1e9], labels=['inside', '0-200', '200-400', '400-700', '700-1500', '>1500'])
    Z['nclear'] = pd.cut(np.expm1(Z.neg_before).round(), [-1, 1, 3, 1000], labels=['0-1', '2-3', '4+'])
    tab = Z.groupby(['band', 'nclear'], observed=True).y.agg(['mean', 'size']).round(3)
    r['burned_share_by_distance_and_clear_passes_before'] = {f'{b}|clear_passes={n}': dict(burned=float(v['mean']), n=int(v['size'])) for (b, n), v in tab.iterrows()}
    res[mode] = r; print(mode, json.dumps(r, indent=1, default=float))
json.dump(res, open(f'{OUT}/e4_summary.json', 'w'), indent=1, default=float)
