"""Does a single seasonal Prithvi score help the 2-day 'where' model in the 10 MP regions?
Step 1 (season score): per forest cell-season, P(cell burns wholesale) from static GIS + images only (no fire history, so no
future-season leak), trained with region AND season held out. Two versions: raw HLS pixels, raw HLS + Prithvi.
Step 2 (2-day): cell-day rows 15 Feb-15 Jun 2022-25; target = a VIIRS fire event in the cell on day t+1 or t+2 (mp_events).
Base inputs: fires within 1/3/5 km in last 1/3/7 days, days since last fire within 1 km, burned-before (2017..season-1 events),
day of year, static GIS. Variants add one season score. Region held out (train other 9 regions, all seasons; season also held out).
Metric: share of next-2-day fire cells inside the daily top 5% / 10% of forest cells of that region (strict recall), averaged per region.
Out: mp/mp_2day.json"""
import json, numpy as np, pandas as pd, lightgbm as lgb, warnings
warnings.filterwarnings('ignore')
from scipy.spatial import cKDTree
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
REGS = json.load(open(f'{SP}/mp/regions.json')); RN = list(REGS); SEAS = [2022, 2023, 2024, 2025]
st = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet')
GIS = ['elev', 'slope', 'rugged', 'rough_in', 'tpi5', 'south', 'd_edge_in', 'd_forest_out', 'road_km', 'major_km', 'road_km_5k', 'd_major', 'd_road',
       'd_village', 'villages_5k', 'farm_2k5', 'farm_5k', 'forest_5k', 'settle_5k', 'lc_forest', 'lc_scrub', 'lc_grass', 'lc_farm']
lab = pd.read_parquet(f'{SP}/mp/labels.parquet').merge(st, on='cell'); lab = lab[lab.lc_forest >= 0.5].reset_index(drop=True)
lab['most'] = ((lab.share >= 0.5) & ~lab.early).astype(int)
RAWN = [f'r{i}' for i in range(36)]; PRN = [f'p{i}' for i in range(64)]
R, T = [], []
for r in RN:
    for Y in SEAS:
        z = np.load(f'{SP}/mp/feat/{r}_{Y}.npz'); i = pd.Index(z['cell']); m = (lab.region == r) & (lab.season == Y); k = i.get_indexer(lab.cell[m])
        R.append(pd.DataFrame(z['raw'][k], index=lab.index[m], columns=RAWN)); T.append((lab.index[m], z['tok'][k].astype(np.float32)))
lab = lab.join(pd.concat(R)); TKI = pd.Index(np.concatenate([t[0] for t in T])); TK = np.concatenate([t[1] for t in T])
prm = dict(n_estimators=300, learning_rate=0.04, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.6, n_jobs=4, verbose=-1)
rng = np.random.default_rng(0)
def pcs(tr, idx):
    pos = TKI.get_indexer(tr); s = rng.choice(pos, min(30000, len(pos)), replace=False); X = TK[s]; X = X[~np.isnan(X).any(1)]
    P = [PCA(n, random_state=0).fit(X[:, a:b]) for (a, b), n in zip([(0, 1024), (1024, 2048), (2048, 3072)], (32, 16, 16))]
    A = TK[TKI.get_indexer(idx)]; nan = np.isnan(A).any(1); A = np.nan_to_num(A)
    F = np.concatenate([p.transform(A[:, a:b]) for p, (a, b) in zip(P, [(0, 1024), (1024, 2048), (2048, 3072)])], 1); F[nan] = np.nan
    return pd.DataFrame(F, index=idx, columns=PRN)
lab['s_raw'] = np.nan; lab['s_prithvi'] = np.nan
for r in RN:
    for Y in SEAS:
        tr = (lab.region != r) & (lab.season != Y); te = (lab.region == r) & (lab.season == Y)
        idx = lab.index[tr | te]; X = lab.loc[idx].join(pcs(lab.index[tr], idx))
        for col, f in (('s_raw', GIS + RAWN), ('s_prithvi', GIS + RAWN + PRN)):
            lab.loc[te, col] = lgb.LGBMClassifier(**prm).fit(X.loc[lab.index[tr], f], lab.most[tr]).predict_proba(X.loc[lab.index[te], f])[:, 1]
        print('score', r, Y, flush=True)
sc_auc = {c: round(float(np.mean([roc_auc_score(lab.most[m], lab[c][m]) for r in RN for Y in SEAS for m in [(lab.region == r) & (lab.season == Y)] if lab.most[m].sum() >= 10])), 4) for c in ('s_raw', 's_prithvi')}
print('season score AUC (no history)', sc_auc, flush=True)
# ---- 2-day rows
ev = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/mp_events.csv', usecols=['acq_date', 'x', 'y']); ev['d'] = pd.to_datetime(ev.acq_date)
ev['cell'] = ((2996000 - ev.y) // 500).astype(int) * 1829 + ((ev.x - 399000) // 500).astype(int)
out = {'season_score_auc': sc_auc}; rows = []
for r in RN:
    g = REGS[r]; cl = lab[lab.region == r].drop_duplicates('cell'); cells = cl.cell.values
    cx = 399000 + 500 * (cells % 1829) + 250.0; cy = 2996000 - 500 * (cells // 1829) - 250.0; tree = cKDTree(np.c_[cx, cy])
    e = ev[(ev.x > g['X0'] - 6000) & (ev.x < g['X0'] + 46320) & (ev.y > g['Y1'] - 46320) & (ev.y < g['Y1'] + 6000)]
    for Y in SEAS:
        days = pd.date_range(f'{Y}-02-15', f'{Y}-06-13'); hist = e[e.d < f'{Y}-01-01']
        bb = np.zeros(len(cells)); bb[tree.query_ball_point(np.c_[hist.x, hist.y], 500, return_sorted=False) if False else []] = 0
        hc = pd.Series(1, index=hist.cell).groupby(level=0).sum(); bb = hc.reindex(cells).fillna(0).values / max(1, Y - 2017)
        ey = e[(e.d >= f'{Y}-01-01') & (e.d <= f'{Y}-06-30')]; dd = {d: v for d, v in ey.groupby('d')}
        last = np.full(len(cells), -999.0); cnt = {}
        S = lab[(lab.region == r) & (lab.season == Y)].set_index('cell')[['s_raw', 's_prithvi']].reindex(cells)
        for day in pd.date_range(f'{Y}-01-01', f'{Y}-06-13'):
            v = dd.get(day)
            c1, c3, c5 = [np.zeros(len(cells)) for _ in range(3)]
            if v is not None:
                for rad, arr in ((1000, c1), (3000, c3), (5000, c5)):
                    for lst in tree.query_ball_point(np.c_[v.x, v.y], rad): arr[lst] += 1
                last[c1 > 0] = (day - pd.Timestamp(f'{Y}-01-01')).days
            cnt[day] = (c1, c3, c5)
            if day < pd.Timestamp(f'{Y}-02-15'): continue
            f = {}
            for lag in (1, 3, 7):
                ks = [day - pd.Timedelta(days=i) for i in range(lag)]
                for j, rad in enumerate((1, 3, 5)): f[f'n{rad}k_{lag}d'] = sum(cnt[k][j] for k in ks if k in cnt)
            tgt = set()
            for k in (1, 2):
                w = dd.get(day + pd.Timedelta(days=k))
                if w is not None: tgt |= set(w.cell)
            dfd = pd.DataFrame(f); dfd['since1k'] = np.minimum((day - pd.Timestamp(f'{Y}-01-01')).days - last, 200); dfd['burned_before'] = bb
            dfd['doy'] = day.dayofyear; dfd['cell'] = cells; dfd['region'] = r; dfd['season'] = Y; dfd['day'] = day
            dfd['y'] = np.isin(cells, list(tgt)).astype(np.int8); dfd['s_raw'] = S.s_raw.values; dfd['s_prithvi'] = S.s_prithvi.values
            rows.append(dfd)
    print('rows', r, flush=True)
D = pd.concat(rows, ignore_index=True).merge(st[['cell'] + GIS], on='cell'); del rows
print('cell-days', len(D), 'positive rate', round(float(D.y.mean()), 5), flush=True)
BASE = [c for c in D.columns if c.startswith('n') and 'k_' in c] + ['since1k', 'burned_before', 'doy'] + GIS
VARS = {'base (fires nearby + burned before + date + GIS)': BASE, '+ season score from raw HLS': BASE + ['s_raw'], '+ season score from raw HLS + Prithvi': BASE + ['s_prithvi']}
P = {n: np.full(len(D), np.nan) for n in VARS}
for r in RN:
    for Y in SEAS:
        tr = ((D.region != r) & (D.season != Y)).values; te = ((D.region == r) & (D.season == Y)).values
        ti = np.where(tr)[0]; pos = ti[D.y.values[ti] == 1]; neg = rng.choice(ti[D.y.values[ti] == 0], min(len(pos) * 20, (D.y.values[ti] == 0).sum()), replace=False); s = np.r_[pos, neg]
        for n, f in VARS.items():
            P[n][te] = lgb.LGBMClassifier(**prm).fit(D.iloc[s][f], D.y.values[s]).predict_proba(D.loc[te, f])[:, 1]
    print('2day', r, flush=True)
res = {}
for n in VARS:
    D['p'] = P[n]; per = {}
    for q in (0.05, 0.10):
        rk = D.groupby(['region', 'day']).p.rank(ascending=False, pct=True) <= q
        per[f'recall_top{int(q*100)}'] = {r: round(float(rk[(D.region == r) & (D.y == 1)].mean()), 4) for r in RN}
    res[n] = {k: dict(mean=round(float(np.mean(list(v.values()))), 4), by_region=v) for k, v in per.items()}
    print(n, {k: v['mean'] for k, v in res[n].items()}, flush=True)
for k in ('recall_top5', 'recall_top10'):
    for a in list(VARS)[1:]:
        g = np.array([res[a][k]['by_region'][r] - res[list(VARS)[0]][k]['by_region'][r] for r in RN])
        res[f'{a} vs base {k}'] = dict(mean=round(float(g.mean()), 4), regions_better=int((g > 0).sum()))
    g = np.array([res[list(VARS)[2]][k]['by_region'][r] - res[list(VARS)[1]][k]['by_region'][r] for r in RN])
    res[f'prithvi vs raw score {k}'] = dict(mean=round(float(g.mean()), 4), regions_better=int((g > 0).sum()))
out['two_day'] = res; out['cell_days'] = int(len(D)); out['pos_rate'] = float(D.y.mean())
json.dump(out, open(f'{SP}/mp/mp_2day.json', 'w'), indent=1); print(json.dumps({k: v for k, v in res.items() if 'vs' in k}, indent=0))
