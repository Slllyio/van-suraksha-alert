"""Big-fire early warning from the FIRST alert (Akkshay 17 Oct 08:48Z: "continue with your next steps").

Question: at the moment of a fire's first satellite pass, what is the chance it ends as a big fire (final scar >= 200 ha)?
Does the first pass's heat add anything over things known without heat (date, place, ground under the first dots, weather)?
Only information available at the first pass is used: the first pass's own detections, the ground under THOSE dots
(not the final scar), last season's burns at those dots, and that day's weather (ERA5, stands in for a forecast).
Honest test: leave-one-season-out (train on the other seasons, predict the held-out one), Feb-Jun fires 2017-2026.
Out: results/bigfire_warning.csv (per-fire held-out %), results/bigfire_warning.json, figures/bigfire_warning.png
"""
import json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss, average_precision_score
from sklearn.isotonic import IsotonicRegression
from h0_lib import RES, BF, HERE

BIG = 200
v = pd.read_csv(f'{RES}/place_det.csv', parse_dates=['t']).dropna(subset=['fire']); v['fire'] = v.fire.astype(int)
F = pd.read_csv(f'{BF}/fires.csv'); F = F[F.month.between(2, 6)]
first = v.sort_values('t').groupby('fire').head(1)[['fire', 'pass']]
fp = v.merge(first, on=['fire', 'pass'])
G = fp.groupby('fire').agg(t=('t', 'min'), n_pix=('frp', 'size'), frp_sum=('frp', 'sum'), frp_max=('frp', 'max'), rel_max=('rel', 'max'),
                           rel_sum=('rel', lambda s: np.log(np.exp(s).sum())), night=('daynight', lambda s: (s == 'N').mean()),
                           pix_km2=('lpix', 'mean'), canopy=('canopy', 'mean'), grass=('grass', 'mean'), litter=('litter', 'mean'),
                           teak=('teak', 'mean'), slope=('slope', 'mean'), burnt_last=('since1', 'mean'), hist_years=('hist_years', 'mean'),
                           sensor=('sensor', 'first')).reset_index()
# other fires burning nearby in the 3 days before (known at first pass)
allv = v[['t', 'x', 'y', 'fire']]
xy = fp.groupby('fire')[['x', 'y']].mean()
def nearby(r):
    w = allv[(allv.t < r.t) & (allv.t >= r.t - pd.Timedelta('3D')) & (allv.fire != r.fire)]
    d = np.hypot(w.x - xy.at[r.fire, 'x'], w.y - xy.at[r.fire, 'y'])
    return (d < 10000).sum()
G['nearby_3d'] = G.apply(nearby, axis=1)
W = pd.read_csv(f'{RES}/fire_cov.csv')[['fire', 'tmax', 'rh', 'wind', 'rain30']]
G = G.merge(F[['fire', 'season', 'area_ha']], on='fire').merge(W, on='fire', how='left')
G['doy'] = G.t.dt.dayofyear; G['big'] = (G.area_ha >= BIG).astype(int)
G['l_n'] = np.log(G.n_pix); G['l_frp'] = np.log(G.frp_sum); G['l_max'] = np.log(G.frp_max); G['l_near'] = np.log1p(G.nearby_3d)
for c in ['tmax', 'rh', 'wind', 'rain30', 'canopy', 'grass', 'litter', 'teak', 'slope', 'burnt_last', 'hist_years']:
    G[c] = G[c].fillna(G[c].median())
print('fires', len(G), 'big share', round(G.big.mean(), 3))

SETS = {'date only': ['doy'],
        'date + place + weather (no heat)': ['doy', 'canopy', 'grass', 'litter', 'teak', 'slope', 'burnt_last', 'hist_years', 'tmax', 'rh', 'wind', 'rain30', 'l_near'],
        'pixel count only': ['l_n'],
        'heat only (count, summed FRP, max FRP, relative heat)': ['l_n', 'l_frp', 'l_max', 'rel_max', 'rel_sum', 'pix_km2', 'night'],
        'everything': ['doy', 'canopy', 'grass', 'litter', 'teak', 'slope', 'burnt_last', 'hist_years', 'tmax', 'rh', 'wind', 'rain30', 'l_near',
                       'l_n', 'l_frp', 'l_max', 'rel_max', 'rel_sum', 'pix_km2', 'night']}
out = {'fires': len(G), 'big_threshold_ha': BIG, 'base_rate': round(G.big.mean(), 3), 'models': {}}
for name, feats in SETS.items():
    p = np.zeros(len(G))
    for s in G.season.unique():
        tr, te = G.season != s, G.season == s
        m = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000)).fit(G.loc[tr, feats], G.loc[tr, 'big'])
        p[te.values] = m.predict_proba(G.loc[te, feats])[:, 1]
    G[f'p_{name}'] = p
    top = G[f'p_{name}'] >= np.quantile(p, 0.9)
    o = {'auc': round(roc_auc_score(G.big, p), 3), 'avg_precision': round(average_precision_score(G.big, p), 3),
         'brier': round(brier_score_loss(G.big, p), 4), 'top10pct_flagged_big_rate': round(G.big[top].mean(), 3),
         'top10pct_catches_share_of_big': round(G.big[top].sum() / G.big.sum(), 3),
         'auc_by_season': {int(s): round(roc_auc_score(g.big, g[f'p_{name}']), 3) for s, g in G.groupby('season') if g.big.nunique() == 2}}
    out['models'][name] = o; print(f'{name:55s}', {k: o[k] for k in list(o)[:5]})
# bootstrap: does heat add over no-heat?
a, b = G['p_everything'], G['p_date + place + weather (no heat)']
d = []
rng = np.random.default_rng(0)
for i in range(500):
    k = rng.integers(0, len(G), len(G))
    if G.big.values[k].sum() == 0: continue
    d.append(roc_auc_score(G.big.values[k], a.values[k]) - roc_auc_score(G.big.values[k], b.values[k]))
out['auc_gain_heat_over_noheat'] = [round(float(np.mean(d)), 3), [round(float(x), 3) for x in np.percentile(d, [2.5, 97.5])]]
print('heat adds AUC', out['auc_gain_heat_over_noheat'])
# calibration of the 'everything' held-out %: bins
pb = pd.cut(G.p_everything, [0, .05, .1, .2, .3, .5, 1])
cal = G.groupby(pb, observed=True).agg(fires=('big', 'size'), said=('p_everything', 'mean'), happened=('big', 'mean')).round(3)
print(cal); out['calibration'] = cal.reset_index().astype(str).to_dict('records')
# plain table: by pixel count and heat-for-its-pass
G['n_cls'] = pd.cut(G.n_pix, [0, 1, 2, 4, 1000], labels=['1 dot', '2 dots', '3-4 dots', '5+ dots'])
G['hot'] = np.where(G.rel_max >= G.rel_max.quantile(.8), 'hot for its pass (top fifth)', 'not hot')
tab = G.pivot_table(index='n_cls', columns='hot', values='big', aggfunc=['mean', 'size'], observed=True)
print(tab.round(3)); out['big_rate_by_dots_and_heat'] = {f'{a}|{b}|{c}': round(float(v), 3) for (a, b, c), v in tab.stack().stack().items()} if False else tab.round(3).to_string()
# coefficients of the full model (all seasons) for direction
m = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000)).fit(G[SETS['everything']], G.big)
out['coef_everything'] = dict(sorted({f: round(float(c), 3) for f, c in zip(SETS['everything'], m[-1].coef_[0])}.items(), key=lambda kv: -abs(kv[1])))
print(out['coef_everything'])
G[['fire', 'season', 't', 'area_ha', 'big', 'n_pix', 'frp_sum', 'rel_max'] + [c for c in G if c.startswith('p_')]].to_csv(f'{RES}/bigfire_warning.csv', index=False)
json.dump(out, open(f'{RES}/bigfire_warning.json', 'w'), indent=1, default=str)

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
names = list(SETS); vals = [out['models'][n]['top10pct_catches_share_of_big'] * 100 for n in names]
ax[0].barh(range(len(names)), vals, color=['gray', 'tab:green', 'tab:blue', 'tab:red', 'k']); ax[0].set_yticks(range(len(names)), [n.split(' (')[0] for n in names], fontsize=8)
ax[0].axvline(10, ls='--', c='gray'); ax[0].set_xlabel('% of big fires caught by flagging 10% of new fires'); ax[0].invert_yaxis()
ax[0].set_title(f"Held-out seasons, {len(G)} fires, {G.big.sum()} big (>= {BIG} ha)", fontsize=10)
c = pd.DataFrame(out['calibration']); ax[1].plot([0, .6], [0, .6], 'k:'); ax[1].plot(c.said.astype(float), c.happened.astype(float), 'o-')
ax[1].set_xlabel('chance the model said'); ax[1].set_ylabel('share that became big'); ax[1].set_title('Is the % honest? (held-out seasons)', fontsize=10)
fig.tight_layout(); fig.savefig(f'{HERE}/figures/bigfire_warning.png', dpi=110)
