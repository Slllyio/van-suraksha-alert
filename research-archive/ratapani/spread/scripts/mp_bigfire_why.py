"""Why do some big MP fires get a much better 24 h map than others? (Akkshay Oct 19 12:28Z: 'are these interior or forest staff
won't reach this because of some other reasons').  600 big fires from mp_bigfire_apply.py. Per fire: map score (learned area, mean over
forecasts) vs access (roads, villages, depth inside forest, ruggedness: mp_grid static_gis_v1, cells under the scar) and the fire's own
shape in the satellite record (dots per look, how much of the scar the dots cover, how long it burned, how compact the scar is).
Outputs why/fire_table.csv, why/why.json."""
import glob, pickle, json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.metrics import r2_score
IN = '/tmp/claude-0/mpbig'; OUT = '/mnt/project-files/ratapani/spread/mp_bigfires/why'
G = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet').set_index('cell')
X0, Y1, NC = 399000.0, 2996000.0, 1829
R = pd.read_csv(f'{IN}/mp_bigfire_rows.csv'); R = R[R.skip.isna()] if 'skip' in R else R
S = pd.read_csv('/mnt/project-files/ratapani/spread/mp_bigfires/fires_summary.csv').set_index('seed')
ACC = ['d_road', 'd_major', 'd_village', 'villages_5k', 'road_km_5k', 'settle_5k', 'farm_5k', 'forest_5k', 'd_edge_in', 'rugged', 'slope', 'elev', 'lc_teak', 'lc_sal', 'lc_bamboo', 'lc_grass', 'lc_degraded']
rows = []
for f in glob.glob(f'{IN}/fire_*.pkl'):
    z = pickle.load(open(f, 'rb')); s = z['seed']
    if s not in S.index: continue
    x0, y1, W, H = z['box']; dom = z['dom']; d = z['d']
    rr, cc = np.nonzero(dom); X = x0 + (cc + .5) * 20; Y = y1 - (rr + .5) * 20
    cell = ((Y1 - Y) // 500).astype(int) * NC + ((X - X0) // 500).astype(int)
    g = G.reindex(np.unique(cell)); a = g[ACC].mean()            # access/ground averaged over the cells under the scar
    dd = cKDTree(d[['x', 'y']].values).query(np.c_[X, Y])[0]
    per = d.groupby('lk').size(); dur = (d.t.max() - d.t.min()).total_seconds() / 3600
    area = dom.sum() * .04; perim = (np.abs(np.diff(dom.astype(int), axis=0)).sum() + np.abs(np.diff(dom.astype(int), axis=1)).sum()) * 20
    r = R[R.seed == s]
    rows.append(dict(seed=s, score=r.learned.mean(), rule=r.rule.mean(), oracle=r.oracle.mean(), division=S.at[s, 'division'], year=int(str(r.t.iloc[0])[:4]),
                     month=pd.Timestamp(r.t.iloc[0]).month, scar_ha=area, looks=len(per), dots=len(d), dots_per_look=len(d) / len(per),
                     dots_per_100ha=len(d) / area * 100, scar_within_265m=float((dd <= 265).mean()), scar_within_600m=float((dd <= 600).mean()),
                     burn_hours=dur, compact=4 * np.pi * area * 1e4 / max(perim, 1) ** 2, frp_median=float(d.frp.median()),
                     night_share=float((d.daynight == 'N').mean()), size_error=float((r.learned_ha / r.true_extra_ha.clip(lower=1)).median()), **a.to_dict()))
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/fire_table.csv', index=False)
FIRE = ['scar_ha', 'looks', 'dots_per_look', 'dots_per_100ha', 'scar_within_265m', 'scar_within_600m', 'burn_hours', 'compact', 'frp_median', 'night_share', 'month']
res = dict(fires=len(T))
res['spearman_with_score'] = {c: round(float(spearmanr(T[c], T.score, nan_policy='omit').correlation), 3) for c in FIRE + ACC}
q = T.score.quantile([.25, .75]); top, bot = T[T.score >= q[.75]], T[T.score <= q[.25]]
res['top_vs_bottom_quarter_median'] = {c: [round(float(top[c].median()), 3), round(float(bot[c].median()), 3)] for c in ['score'] + FIRE + ACC}
# how much each group explains, held out by year
def r2(cols):
    p = np.zeros(len(T))
    for y in T.year.unique():
        tr, te = T.year != y, T.year == y
        p[te] = lgb.LGBMRegressor(n_estimators=200, learning_rate=.03, num_leaves=7, min_child_samples=20, n_jobs=1, verbose=-1).fit(T.loc[tr, cols], T.score[tr]).predict(T.loc[te, cols])
    return round(float(r2_score(T.score, p)), 3)
res['heldout_R2'] = {'fire shape in satellite record': r2(FIRE), 'access + ground': r2(ACC), 'both': r2(FIRE + ACC),
                     'only dot coverage (scar_within_265m)': r2(['scar_within_265m'])}
# access effect after removing dot coverage: residual of score on coverage
from numpy.polynomial import polynomial as Pn
c = Pn.polyfit(T.scar_within_265m, T.score, 2); T['resid'] = T.score - Pn.polyval(T.scar_within_265m, c)
res['access_vs_score_after_coverage'] = {k: round(float(spearmanr(T[k], T.resid, nan_policy='omit').correlation), 3) for k in ACC}
res['coverage_vs_access'] = {k: round(float(spearmanr(T[k], T.scar_within_265m, nan_policy='omit').correlation), 3) for k in ['d_road', 'd_village', 'villages_5k', 'd_edge_in', 'rugged']}
# remoteness bands
T['remote'] = pd.qcut(T.d_village.rank(method='first'), 3, labels=['near villages', 'middle', 'remote'])
res['by_remoteness'] = T.groupby('remote', observed=True)[['score', 'scar_ha', 'looks', 'scar_within_265m', 'd_village', 'd_road']].median().round(3).to_dict('index')
res['by_division_top'] = T.groupby('division').score.agg(['median', 'size']).query('size >= 8').sort_values('median').round(3).to_dict('index')
json.dump(res, open(f'{OUT}/why.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
