"""Step 10. Does the pre-fire size score sharpen the app's big-fire chance at alert time?
2025 scar fires (start 15 Feb-31 May). For each fire: (a) the app's big-fire points (field-system/app/big_fire.py items,
rebuilt from the VIIRS archive: first-look dots = same satellite within 10 min, chained by 1.2 km from the first dot;
span, hottest dot, night, date band, division group, VIIRS dots within 10 km in the 72 h before; farmland = VTM farm
share of the start square > 0.5 in place of WorldCover 1 km); (b) SIZE, BIG, PC scores of the start square from the
day before (scratch cubes, all models trained 2018-24). Combination = logistic on points + logit(SIZE), 5-fold CV.
Out: results/at_alert_2025.csv, results/at_alert_fires_2025.csv."""
import csv, pickle, numpy as np, pandas as pd, lf_sr
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from scipy.spatial import cKDTree
import lf_common as L
C, Fe = lf_sr.C, lf_sr.Fe
FD = L.P + 'field-system/data/big_fire/'
PTS = {r['item']: int(r['points']) for r in csv.DictReader(open(FD + 'points_table_S200.csv'))}
DG = {r['Division']: (3 if r['group'].startswith('many') else -3 if r['group'].startswith('few') else 0) for r in csv.DictReader(open(FD + 'division_history_groups.csv'))}
B = Fe.base(); U = B['U']
V = C.load_det(); V = V[(V.season == 2025) & (V.type == 0)].reset_index(drop=True)
tree = cKDTree(np.c_[V.x.values, V.y.values]); ut = V.utc.values
farm = pd.read_parquet(L.P + 'ratapani/mp_grid/static_gis_v1.parquet', columns=['cell', 'lc_farm']).set_index('cell').lc_farm
fires = [f for f in pickle.load(open(L.SC + 'fires.pkl', 'rb')) if f['year'] == 2025 and pd.Timestamp('2025-02-15') <= f['start_day'] <= pd.Timestamp('2025-05-31')]
days = pd.date_range('2025-02-13', '2025-05-30')
cubes = {k: np.nan_to_num(np.load(L.SC + f'cube_{k}_2025.npy').astype(np.float32), nan=-1) for k in ('SIZE', 'BIG', 'PC', 'START')}
rows = []
for f in fires:
    t0 = np.datetime64(f['t0']); sc = f['start_cells']
    cx = C.X0 + (sc % C.W + .5) * C.S; cy = C.Y1 - (sc // C.W + .5) * C.S
    near = np.unique(np.concatenate([tree.query_ball_point([x, y], 1500) for x, y in zip(cx, cy)])).astype(int)
    near = near[np.abs((ut[near] - t0) / np.timedelta64(1, 'm')) <= 10]
    if len(near) == 0: continue
    sat = V.sat.values[near[np.argmin(np.abs(ut[near] - t0))]]
    cand = tree.query_ball_point([cx.mean(), cy.mean()], 6000); cand = [i for i in cand if V.sat.values[i] == sat and abs((ut[i] - t0) / np.timedelta64(1, 'm')) <= 10]
    P = V.iloc[cand]; xy = P[['x', 'y']].values.astype(float)
    first = {int(np.argmin(np.hypot(xy[:, 0] - cx.mean(), xy[:, 1] - cy.mean())))}; grew = True
    while grew:
        grew = False
        for j in range(len(xy)):
            if j not in first and min(np.hypot(*(xy[j] - xy[k])) for k in first) <= 1200: first.add(j); grew = True
    Fd = P.iloc[sorted(first)]; n = len(Fd)
    pts = 0
    pts += PTS['2 dots'] if n == 2 else PTS['3-4 dots'] if 3 <= n <= 4 else PTS['5-8 dots'] if 5 <= n <= 8 else PTS['9+ dots'] if n >= 9 else 0
    blk = np.mean(np.sqrt(Fd.scan.fillna(.375).values * Fd.track.fillna(.375).values)) * 1000
    q = Fd[['x', 'y']].values.astype(float); span = (np.max(np.hypot(q[:, None, 0] - q[None, :, 0], q[:, None, 1] - q[None, :, 1])) if n > 1 else 0) + blk
    pts += PTS['dots spread over 1 km or more'] * (span >= 1000) + PTS['hottest dot 20 MW or more'] * (Fd.frp.max() >= 20) + PTS['first seen at night'] * (Fd.daynight == 'N').any()
    ds = (pd.Timestamp(f['t0']) - pd.Timestamp('2025-02-15')).total_seconds() / 86400
    pts += PTS['first seen 15 Mar - 15 Apr'] if 28 <= ds < 60 else PTS['first seen 16 Apr - 15 May'] if 60 <= ds < 90 else PTS['first seen after 15 May'] if ds >= 90 else 0
    pts += DG.get(f['div'].replace(' ', '_'), DG.get(f['div'], 0))
    nb = tree.query_ball_point([q[:, 0].mean(), q[:, 1].mean()], 10000)
    n10 = sum(1 for i in nb if 0 < (t0 - ut[i]) / np.timedelta64(1, 'h') <= 72 and (t0 - ut[i]) / np.timedelta64(1, 'm') > 3)
    pts += PTS['10+ VIIRS dots within 10 km in last 3 days'] * (n10 >= 10)
    pts += PTS['mostly farmland around (>50% within 1 km)'] * (farm.reindex(sc).fillna(0).mean() > 0.5)
    t = (f['start_day'] - pd.Timedelta(days=1) - days[0]).days
    ii = np.searchsorted(U, sc); ok = (ii < len(U)) & (U[np.minimum(ii, len(U) - 1)] == sc)
    if t < 0 or not ok.any(): continue
    rows.append(dict(fire=f['fire'], div=f['div'], ha=f['forest_ha'], dots=n, points=int(pts), n10=n10, **{k: float(c[t, ii[ok]].max()) for k, c in cubes.items()}))
D = pd.DataFrame(rows); D = D[D.PC > -1]; D.to_csv(L.OUT + 'at_alert_fires_2025.csv', index=False)
lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
out = []
for th in (200, 500):
    y = (D.ha >= th).values
    X = np.c_[D.points.values, lg(D.SIZE.values)]; cv = np.zeros(len(D))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(X, y):
        cv[te] = LogisticRegression().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    sc = dict(points=D.points.values + 1e-3 * D.dots.values, size_score=D.SIZE.values, watch_score=D.BIG.values, pc_daily=D.PC.values, points_plus_size=cv)
    for k, s in sc.items():
        bs = [roc_auc_score(y[i], s[i]) for i in [np.random.default_rng(b).integers(0, len(y), len(y)) for b in range(300)]]
        out.append(dict(size=f'{th}+', n_fires=len(y), n_big=int(y.sum()), score=k, auc=roc_auc_score(y, s), lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5), prauc=average_precision_score(y, s)))
    # top-N per day the officials read: share of big fires in the day's top 20% by score
R = pd.DataFrame(out).round(3); R.to_csv(L.OUT + 'at_alert_2025.csv', index=False); print(R.to_string())
