"""t5: does the 20-30 m scar add independent evidence? Uses scratch r21_cb/scar_shapes.parquet from t4.
(1) class table: scar found, size, strip index (core30), aspect, compactness, beat/road alignment vs decoy, by set x window x flag;
(2) season-held-out AUC of shape-only features for Jan-14 Feb flagged (control-rich) vs 16 Mar-May flagged (wildfire-like) in Ratapani;
(3) MP 15 Feb-15 Jun: does adding a scar condition raise the density-matched precision of the flag in 15-28 Feb?
(4) lag: days from fire to the first usable post-fire image.
Outputs: out/scar_shape_by_class.csv, out/scar_auc.csv, out/scar_rule.csv, out/scar_lag.csv"""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
E = pd.read_parquet(S + 'r21_cb/scar_shapes.parquet')
E = E.merge(pd.read_parquet(S + 'r21_cb/density.parquet'), on='cid', how='left')
E = E[E.fn.notna()]
E['yes'] = E.scar_found == 'yes'; E['any_scar'] = E.scar_found.isin(['yes', 'faint'])
E['strip'] = (E.core30 < 0.25) & E.area_ha.notna()
E['aligned'] = (E.beat30 >= 0.25) | (E.road30 >= 0.25)
E['win'] = E.fn.map({'1 Jan': 'Jan-14 Feb', '2 1-14 Feb': 'Jan-14 Feb', '3 15-28 Feb': '15-28 Feb', '4 1-15 Mar': '1-15 Mar', '5 16 Mar-May': '16 Mar-May'})
E = E[E.win.notna()]
rows = []
for (st, wn, fl), q in E.groupby(['set', 'win', 'flag_cur']):
    s = q[q.area_ha.notna()]
    rows.append(dict(set={'R': 'Ratapani v2', 'M': 'all-MP 15 Feb-15 Jun'}[st], window=wn, flagged=fl, events=len(q),
                     scar_yes=q.yes.mean(), scar_yes_or_faint=q.any_scar.mean(), with_outline=len(s),
                     median_ha=s.area_ha.median(), median_core30=s.core30.median(), strip_share=s.strip.mean(),
                     median_aspect=s.aspect.median(), median_compact=s.compact.median(),
                     beat30=s.beat30.mean(), beat30_decoy=s.beat30_decoy.mean(), road30=s.road30.mean(), road30_decoy=s.road30_decoy.mean(),
                     low_severity=(s.severity == 'low').mean(), median_rdnbr=s.rdnbr.median()))
T = pd.DataFrame(rows); T.to_csv(O + 'scar_shape_by_class.csv', index=False)
pd.set_option('display.width', 250); print(T.round(3).to_string())
# (2) AUC, Ratapani, flagged events with outline, Jan-14 Feb vs 16 Mar-May, leave-one-season-out
F = ['area_ha', 'core30', 'aspect', 'compact', 'beat30', 'road30']
out = []
for st in ['R']:
    for subset, cond in [('flagged only', E.flag_cur == True), ('all events', E.flag_cur.notna())]:
        q = E[(E.set == st) & cond & E.win.isin(['Jan-14 Feb', '16 Mar-May']) & E.area_ha.notna()].copy()
        y = (q.win == 'Jan-14 Feb').astype(int).values
        for feats, nm in [(F, 'shape+size+alignment'), (['core30', 'aspect', 'compact', 'beat30', 'road30'], 'shape+alignment (no size)'),
                          (['beat30', 'road30'], 'alignment only')]:
            p = np.full(len(q), np.nan)
            for s in q.season.unique():
                tr = q.season.values != s
                if y[tr].sum() < 10: continue
                m = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, class_weight='balanced', random_state=0).fit(q[feats].values[tr], y[tr])
                p[~tr] = m.predict_proba(q[feats].values[~tr])[:, 1]
            ok = np.isfinite(p)
            bs = []
            rng = np.random.default_rng(1)
            for _ in range(300):
                i = rng.integers(0, ok.sum(), ok.sum())
                yy, pp = y[ok][i], p[ok][i]
                if 0 < yy.sum() < len(yy): bs.append(roc_auc_score(yy, pp))
            out.append(dict(set=st, subset=subset, features=nm, n_jan=int(y.sum()), n_marmay=int((1 - y).sum()),
                            auc=roc_auc_score(y[ok], p[ok]), lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5)))
A = pd.DataFrame(out); A.to_csv(O + 'scar_auc.csv', index=False); print(A.round(3).to_string())
# (3) MP: does a scar condition raise the excess share in late Feb? compare share of flagged events meeting the condition
# in 15-28 Feb vs 16 Mar-May, matched on density bin (event-weighted).
edges = [-1, 0, 2, 5, 10, 25, 60, 1e9]; E['db'] = np.digitize(E.dens10k.fillna(0), edges[1:-1], right=True)
res = []
for st in ['M', 'R']:
    q = E[(E.set == st) & (E.flag_cur == True)]
    for cname in ['strip', 'aligned', 'no clear scar', 'small (<5 ha)']:
        cond = {'strip': q.strip, 'aligned': q.aligned, 'no clear scar': ~q.yes, 'small (<5 ha)': q.area_ha.fillna(0) < 5}[cname]
        a = q[q.win == '15-28 Feb']; b = q[q.win == '16 Mar-May']
        ca = cond[a.index]; cb = cond[b.index]
        rb = cb.groupby(b.db).mean(); exp = a.db.map(rb).fillna(cb.mean())
        res.append(dict(set=st, condition=cname, late_feb_flagged_events=len(a), share_late_feb=ca.mean(), share_marmay_matched=exp.mean(),
                        ratio=ca.mean() / exp.mean() if exp.mean() else np.nan,
                        jan_share=cond[q[q.win == 'Jan-14 Feb'].index].mean() if (q.win == 'Jan-14 Feb').any() else np.nan))
R = pd.DataFrame(res); R.to_csv(O + 'scar_rule.csv', index=False); print(R.round(3).to_string())
# (4) lag
L = E[E.lag_days.notna()].groupby('set').lag_days.describe(percentiles=[.25, .5, .75, .9])
for k in [3, 5, 10]: L[f'share_le_{k}d'] = E[E.lag_days.notna()].groupby('set').lag_days.apply(lambda s: (s <= k).mean())
L.to_csv(O + 'scar_lag.csv'); print(L.round(2).to_string())
