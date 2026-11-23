"""Emerging-hot-spot style classes on scar burns (2017-2026) and persistent VIIRS ignition sources; held-out value vs plain burn frequency."""
import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy import stats
RS = '/mnt/project-files/research/'; OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/cause_an/'
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']; n = len(G)
xy = np.zeros((n, 2))
for f in G: p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)
tr = cKDTree(xy); nb = tr.query_ball_point(xy, 1010)  # self + 8 neighbours (+ 4 at 1 km)
bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
S = list(range(2017, 2027)); B = np.zeros((len(S), n))
for r in bw[bw.burned == 1].itertuples(): B[S.index(r.season), r.cell_id] = 1
# Getis-Ord Gi* per year on burned indicator
W = np.zeros((n, n), np.float32)
for i, js in enumerate(nb): W[i, js] = 1
def gistar(x):
    xb, s = x.mean(), x.std(); wi = W.sum(1); num = W @ x - xb * wi
    den = s * np.sqrt((n * (W ** 2).sum(1) - wi ** 2) / (n - 1)); return num / den
Z = np.stack([gistar(B[k]) for k in range(len(S))])
hot = Z > 1.96
nh = hot.sum(0)
tau = np.array([stats.kendalltau(np.arange(len(S)), Z[:, i])[0] if Z[:, i].std() > 0 else 0 for i in range(n)])
pk = np.array([stats.kendalltau(np.arange(len(S)), Z[:, i])[1] if Z[:, i].std() > 0 else 1 for i in range(n)])
cls = np.full(n, 'none', object)
cls[(nh >= 1)] = 'sporadic'
cls[(nh >= 0.9 * len(S)) & (pk >= 0.05)] = 'persistent'
cls[(nh >= 0.9 * len(S)) & (pk < 0.05) & (tau > 0)] = 'intensifying'
cls[(nh >= 0.9 * len(S)) & (pk < 0.05) & (tau < 0)] = 'diminishing'
cls[hot[-1] & (nh == 1)] = 'new'
cls[hot[-1] & ~hot[:-1].any(0) & False] = 'new'
cls[(hot[-1]) & (nh < 0.9 * len(S)) & (nh >= 0.5 * len(S)) & (pk < 0.05) & (tau > 0)] = 'consecutive/emerging'
cls[(~hot[-1]) & (nh >= 0.5 * len(S)) & (nh < 0.9 * len(S))] = 'oscillating/historical'
print('EHSA-style classes (Gi* z>1.96 on yearly burned indicator, 1 km window, 2017-2026):')
print(pd.Series(cls).value_counts().to_string())
print('burn frequency by class (mean seasons burned of 10):\n', pd.Series(B.sum(0)).groupby(cls).mean().round(2).to_string())
# held-out: for each season Y, rank cells within pseudo-beat by (a) own frequency in other seasons, (b) Gi*-smoothed frequency, (c) a+0.5b ; capture burned cells at top-5 and top-10 per beat
pb = pd.read_csv('/mnt/project-files/ratapani/scoring/pseudo_beats_pipeline.csv').set_index('cell_id').pseudo_beat.reindex(range(n)).values
res = {k: [0, 0, 0] for k in ('own', 'nbr', 'mix')}; tot = 0
for k, Y in enumerate(S):
    o = np.delete(B, k, 0); own = o.mean(0); nbm = (W @ own) / W.sum(1); mix = own + 0.5 * nbm + 1e-6 * np.random.default_rng(k).random(n)
    y = B[k]; tot += y.sum()
    for nm, sc in (('own', own + 1e-6 * np.random.default_rng(k).random(n)), ('nbr', nbm + 1e-6 * np.random.default_rng(k).random(n)), ('mix', mix)):
        for b in np.unique(pb):
            idx = np.where(pb == b)[0]; top = idx[np.argsort(-sc[idx])]
            res[nm][0] += y[top[:5]].sum(); res[nm][1] += y[top[:10]].sum(); res[nm][2] += y[top[:20]].sum()
print('\nseason-level capture of burned cells within pseudo-beats (top5 / top10 / top20 cells per beat per season):')
for nm, (a, b, c) in res.items(): print(f'  {nm}: {a / tot:.3f} / {b / tot:.3f} / {c / tot:.3f}')
# persistent VIIRS ignition sources
E = pd.read_parquet(OUT + 'events.parquet'); v = pd.read_parquet(OUT + 'viirs_cells.parquet')
first = v.sort_values('dt_ist').groupby('ev').first()
first['season'] = first.dt_ist.dt.year
ig = first.groupby('cell_id').season.nunique().reindex(range(n), fill_value=0)
yrs = first.season.nunique(); pyear = first.groupby('season').cell_id.nunique() / n
sim = (np.random.default_rng(2).random((500, len(pyear), n)) < pyear.values[None, :, None]).sum(1)
for k_ in (3, 4, 5, 6):
    print(f'cells with event-start (ignition proxy) in >= {k_} of {yrs} seasons: observed {(ig >= k_).sum()}  random expectation {np.mean((sim >= k_).sum(1)):.1f}')
top = ig[ig >= 5].index
print('top repeat-ignition cells (>=5 seasons):', len(top), ' their share of all event starts:', round(first.cell_id.isin(top).mean(), 3))
px = pd.read_csv('/mnt/project-files/ratapani/ee/proximity.csv').set_index('cell_id')
print('dist_village / dist_road / depth for repeat-ignition cells vs all cells with any event start:')
print(pd.DataFrame({'repeat>=5': px.loc[top].median(), 'any': px.loc[ig[ig >= 1].index].median()}).round(0).to_string())
pd.DataFrame({'cell_id': range(n), 'ehsa': cls, 'n_hot': nh, 'tau': tau, 'ign_seasons': ig.values}).to_csv(OUT + 'ehsa_cells.csv', index=False)
