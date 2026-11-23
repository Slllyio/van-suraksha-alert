"""Experiment A: which beats burn in the next 2 / 7 days. LOSO 2017-24 + train 2017-24 -> test 2025-26."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, common as C
from sklearn.isotonic import IsotonicRegression

df = pd.read_parquet(D.OUT + 'beat_day.parquet')
fp = pd.read_csv('/mnt/project-files/research/reframe/results/cell_fsi_prone.csv').merge(D.cells()[['cell_id', 'beat_uid']], on='cell_id')
fpb = fp.groupby('beat_uid').agg(fsi_beat=('fsi_prone', 'mean'), fsi_hi=('fsi_prone', lambda s: float((s >= 3.5).mean())))
df = df.merge(fpb, left_on='beat_uid', right_index=True, how='left')
CV = list(range(2017, 2025)); TEST = [2025, 2026]
bs = df.groupby(['season', 'beat']).n7.first()  # placeholder (not used)
# per beat-season first-burned share (for the leave-season-out beat prior)
burned = pd.concat([D.burns()]).query('first')
c = D.cells(); bmap = dict(zip(sorted(c.beat_uid.dropna().unique()), range(94)))
burned['beat'] = c.set_index('cell_id').beat_uid.map(bmap).reindex(burned.cell_id).values
share = burned.groupby(['season', 'beat']).size().unstack(fill_value=0).reindex(columns=range(94), fill_value=0)
ncell = df.groupby('beat').ncell.first()
share = share / ncell.values

def add_prior(d, seasons):
    pr = share.loc[seasons].mean(0); d = d.copy(); d['beat_prior'] = d.beat.map(pr).values; return d

STATIC = ['ncell', 'forest', 'beat_prior', 'doy']
RECENT = ['v_l1', 'v_l3', 'v_l7', 'v_season', 'v_dsl', 'seen_share', 'seen14', 'adj_l1', 'adj_l3', 'san_l1', 'san_l3', 'san_l7', 'san_seen']
WX = ['T2M_MAX', 'RH2M', 'days_since_rain', 'rh_min7', 'rh7', 'tmax7', 'rain30', 'vpd7', 'WS10M']
LEAN = ['lean_sum', 'lean_max', 'lean_top5', 'lean_rate', 'lean_n']
SETS = {'climatology': STATIC, 'fsi_fire_prone_map': ['doy', 'ncell', 'fsi_beat', 'fsi_hi'], 'persistence': STATIC + ['v_l1', 'v_l3', 'v_l7', 'v_dsl', 'seen_share', 'seen14'],
        'lean_beat_sum': ['doy'] + LEAN, 'full': STATIC + RECENT + WX + LEAN, 'full_no_lean': STATIC + RECENT + WX}

def run(y, feats):
    raw = pd.Series(np.nan, index=df.index)
    for hold, train in [([s], [x for x in CV if x != s]) for s in CV] + [(TEST, CV)]:
        tr = add_prior(df[df.season.isin(train)], train); te = add_prior(df[df.season.isin(hold)], train)
        raw.loc[te.index], _ = C.fit_predict(tr, te, feats, y)
    out = pd.Series(np.nan, index=df.index)
    for hold in [[s] for s in CV] + [TEST]:
        cal = df.season.isin([x for x in CV if x not in hold])   # calibration map from the other seasons' held-out predictions
        iso = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=1 - 1e-4).fit(raw[cal], df.loc[cal, y])
        m = df.season.isin(hold); out[m] = iso.predict(raw[m])
    return out

res = {}
for y, w in (('y2', 'n2'), ('y7', 'n7'), ('v2', None), ('v7', None)):
    res[y] = {}
    preds = {k: run(y, f) for k, f in SETS.items()}
    for split, m in (('loso_2017_24', df.season.isin(CV)), ('test_2025_26', df.season.isin(TEST))):
        d = df[m].copy(); d['day'] = d.season.astype(str) + d.date.astype(str)
        r = {}
        for k in SETS:
            d[k] = preds[k][m].values
            r[k] = C.skill(d[y], d[k], ref=d['climatology'] if k != 'climatology' else None)
            for K in (10, 20):
                r[k][f'beatday_recall_top{K}'] = C.topk_recall(d, k, y, 'day', K)
                if w: r[k][f'burned_cells_in_top{K}'] = C.topk_recall(d, k, y, 'day', K, weight=w)
            r[k]['auc_by_season'] = {int(s): round(float(C.roc_auc_score(g[y], g[k])), 3) for s, g in d.groupby('season')}
        for K in (10, 20):
            r[f'ceiling_top{K}'] = C.topk_ceiling(d, y, 'day', K)
            if w: r[f'ceiling_burned_cells_top{K}'] = C.topk_ceiling(d, y, 'day', K, weight=w)
            d['rnd'] = np.random.default_rng(1).random(len(d)); r[f'random_top{K}'] = C.topk_recall(d, 'rnd', y, 'day', K)
        r['reliability_full'] = C.reliability(d[y], d['full'])
        res[y][split] = r
        print(y, split, {k: (r[k]['auc'], r[k].get('bss_vs_ref'), r[k]['beatday_recall_top10']) for k in SETS}, flush=True)
    df[f'p_{y}'] = preds['full'].values
json.dump(res, open('/mnt/project-files/research/reframe/results/beats.json', 'w'), indent=1)
df[['season', 'date', 'beat', 'beat_uid'] + [f'p_{y}' for y in ('y2', 'y7', 'v2', 'v7')]].to_parquet(D.OUT + 'beat_preds.parquet')
print('DONE')
