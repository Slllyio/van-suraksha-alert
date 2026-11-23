"""Step 6. Season question: before the season (inputs from earlier seasons + static GIS only), which squares will burn in
LARGE fires? Target per square and season = forest ha burned by fires of 200 (or 500) forest ha+. Models (LightGBM,
trained 2018-21, tested 2022-24; trained 2018-24, tested 2025): ALLMAP = trained on all scar burning (today's kind of map),
BIGMAP = trained on 200 ha+ burning only. Baselines: VIIRS fire history, all-scar history, big-fire history.
Score = share of the season's big-fire forest ha that falls in the top 5/10/20% of squares (statewide ranking)."""
import numpy as np, pandas as pd, pickle, lightgbm as lgb
from scipy.ndimage import uniform_filter
import lf_common as L, lf_sr, l2_samples as S2
C, Fe = lf_sr.C, lf_sr.Fe
B = Fe.base(); U, ur, uc = B['U'], B['ur'], B['uc']; nU = len(U)
fires = pickle.load(open(L.SC + 'fires.pkl', 'rb'))
cy = pd.read_parquet(L.P + 'fire-alert-scars/mp/burn_history/cell_year.parquet', columns=['cell', 'forest']).drop_duplicates('cell').set_index('cell').forest
FOR = cy.reindex(U).fillna(0).values.astype(np.float32)
st = S2.static(); V = C.load_det(); V = V[(V.type == 0) & ~V.ctrl]


def target(y, th):
    A = np.zeros(C.H * C.W, np.float32)
    for f in fires:
        if f['year'] == y and f['forest_ha'] >= th: np.add.at(A, f['cells'], f['frac'])
    return np.minimum(A[U], 1) * FOR * 25


def viirs_hist(y):
    o = {}
    yrs = [p for p in range(y - 5, y)]
    G = np.zeros((C.H, C.W), np.float32); Y = np.zeros_like(G)
    for p in yrs:
        v = V[V.season == p].drop_duplicates(['row', 'col', 'ld']); v = v[(v.row >= 0) & (v.row < C.H) & (v.col >= 0) & (v.col < C.W)]
        g = np.zeros_like(G); np.add.at(g, (v.row.values, v.col.values), 1); G += g; Y += g > 0
    for r in (0, 1, 3, 7): o[f'vh_r{r}'] = (uniform_filter(G, 2 * r + 1, mode='constant') * (2 * r + 1) ** 2)[ur, uc]
    o['vy_r0'] = Y[ur, uc]; o['vy_r1'] = uniform_filter(Y, 3, mode='constant')[ur, uc]
    return o


def table(y):
    d = dict(st); d.update(S2.scar_hist(y)); d.update(viirs_hist(y)); d['div'] = B['home'].astype(np.float32)
    D = pd.DataFrame(d); D['t_all'] = target(y, 0); D['t200'] = target(y, 200); D['t500'] = target(y, 500); D['season'] = y
    return D


T = {y: table(y) for y in range(2018, 2026)}; print('tables', flush=True)
feats = [c for c in T[2018].columns if c not in ('t_all', 't200', 't500', 'season')]
P = dict(objective='tweedie', learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbose=-1, num_threads=4)
rows = []
for per, tr, te in (('held 2022-24', range(2018, 2022), (2022, 2023, 2024)), ('fwd 2025', range(2018, 2025), (2025,))):
    D = pd.concat([T[y] for y in tr])
    M = {}
    for nm, tg in (('ALLMAP', 't_all'), ('BIGMAP', 't200'), ('B500MAP', 't500')):
        M[nm] = lgb.train(P, lgb.Dataset(D[feats].values, D[tg].values, feature_name=feats, categorical_feature=['div']), 400)
    for y in te:
        Dt = T[y]; sc = {k: m.predict(Dt[feats].values) for k, m in M.items()}
        sc['VIIRS_HIST'] = Dt.vh_r1.values; sc['SCAR_HIST'] = np.nan_to_num(Dt.bf_all_r3.values); sc['BIG_HIST'] = np.nan_to_num(Dt.bf_big_r3.values)
        rng = np.random.default_rng(y); sc['RAND'] = rng.random(nU)
        for k, s in sc.items():
            o = np.argsort(-(s + rng.random(nU) * 1e-9))
            for tg in ('t_all', 't200', 't500'):
                cum = np.cumsum(Dt[tg].values[o]) / max(Dt[tg].sum(), 1)
                for top in (0.05, 0.10, 0.20):
                    rows.append(dict(period=per, season=y, ranking=k, target=tg, top=top, share=100 * cum[int(top * nU) - 1]))
        print(y, flush=True)
R = pd.DataFrame(rows); R.to_csv(L.OUT + 'season_map_rows.csv', index=False)
S = R.groupby(['period', 'target', 'top', 'ranking']).share.mean().unstack('ranking').round(1)
S.to_csv(L.OUT + 'season_map_summary.csv'); print(S)
