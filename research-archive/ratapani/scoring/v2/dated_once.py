"""SCORING v2 (Oct 15, after research/prediction-review/REVIEW.md): each VIIRS-dated first burn counted ONCE.

Question scored: "was this 500 m square on its beat's list 1 or 2 days before the fire started?"
- Burns: first burn per cell-season from research/ratapani-burn-labels/burn_windows.csv (where), dated by the first
  S-NPP VIIRS point (nominal/high) within 750 m of the cell centre on [ws, we+1], clipped to [ws, we] (same rule as
  ratapani/fsi true_lead_labels_v2, extended to 2025-26 with fire-alert-scars/alerts/viirs-snpp_2025/26.csv).
  Only fire days Feb 17 - Jun 15 count (Akkshay's season, Feb 15 - Jun 15; issue days d-2, d-1 inside it).
- Lists: 5 cells per real beat (94 beats) per issue day, Feb 1 - Jun 20.
- LIVE candidate pool: every cell of the beat except cells whose scar is confirmable by t-1 (window_end + 25 d).
  A live system cannot know the rest. (The old scorer let models pick only from cells known still unburned.)
- Reported: % of dated burns warned 1-2 days before; % listed on any day 1-7 days before; lift over random and over
  burn history; split by near (VIIRS point within 1.5 km in the 3 days before the fire day) vs far (new start).
- Rules: random; burn history (share of other seasons each cell burned); lean model (honest, leak-fixed, from
  research/prediction-review/results/pred_allcells_honest.parquet: LOSO 2017-24, trained 2017-24 for 2025-26);
  each with and without "skip cells listed in the last g days" (g = 1..5).
Out: v2/dated_burns_2017_2026.parquet, v2/results_dated_once.json"""
import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
P = '/mnt/project-files/'; OUT = P + 'ratapani/scoring/v2/'
SEAS = list(range(2017, 2027)); n = 3614
G = json.load(open(P + 'ratapani/grid_500m.geojson'))['features']
xy = np.zeros((n, 2)); ll, ut = [], []
for f in G:
    p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)
    ll.append(np.array(f['geometry']['coordinates'][0][:4]).mean(0)); ut.append((p['x0'] + 250, p['y0'] + 250))
ll, ut = np.array(ll), np.array(ut)
D = lambda L: np.c_[L, L[:, :1] ** 2, L[:, 1:] ** 2, L[:, :1] * L[:, 1:], np.ones(len(L))]
Aff, *_ = np.linalg.lstsq(D(ll), ut, rcond=None)
tree = cKDTree(xy)

# ── VIIRS S-NPP points (same source as the FSI labels for 2017-24, alerts files for 2025-26) ──
v = pd.read_parquet(P + 'ratapani/viirs_snpp_2013_2024.parquet')[['latitude', 'longitude', 'acq_date', 'confidence']]
v = pd.concat([v] + [pd.read_csv(P + f'fire-alert-scars/alerts/viirs-snpp_{Y}.csv')[['latitude', 'longitude', 'acq_date', 'confidence']] for Y in (2025, 2026)])
v = v[v.confidence.astype(str).str.lower().isin(['n', 'h', 'nominal', 'high'])].copy(); v['date'] = pd.to_datetime(v.acq_date)
v = v[v.date >= '2016-12-01']
vxy = D(np.c_[v.longitude.values, v.latitude.values]) @ Aff
pairs = [(c, d) for d, nb in zip(v.date.values, tree.query_ball_point(vxy, r=750)) for c in nb]
vp = pd.DataFrame(pairs, columns=['cell_id', 'vd']).drop_duplicates()
near = [(c, d) for d, nb in zip(v.date.values, tree.query_ball_point(vxy, r=1500)) for c in nb]
vn = pd.DataFrame(near, columns=['cell_id', 'vd']).drop_duplicates()

bw = pd.read_csv(P + 'research/ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
bw = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
x = bw.merge(vp, on='cell_id')
x = x[(x.vd >= x.window_start) & (x.vd <= x.window_end + pd.Timedelta('1D'))].sort_values('vd').drop_duplicates(['season', 'cell_id'])
x['fire_day'] = x.vd.clip(lower=x.window_start, upper=x.window_end)
fb = bw.merge(x[['season', 'cell_id', 'fire_day']], on=['season', 'cell_id'], how='left')
# near = a VIIRS point within 1.5 km on any of the 3 days before the fire day (spread or nearby activity), else a new start
y = fb[fb.fire_day.notna()][['season', 'cell_id', 'fire_day']].merge(vn, on='cell_id')
y = y[(y.vd >= y.fire_day - pd.Timedelta('3D')) & (y.vd <= y.fire_day - pd.Timedelta('1D'))]
fb['near'] = fb.set_index(['season', 'cell_id']).index.isin(y.set_index(['season', 'cell_id']).index)
fb[['season', 'cell_id', 'window_start', 'window_end', 'fire_day', 'near']].to_parquet(OUT + 'dated_burns_2017_2026.parquet', index=False)
chk = pd.read_parquet(P + 'ratapani/fsi/true_lead_labels_v2.parquet'); chk = chk[chk.dated].groupby(['season', 'cell_id']).fire_day.first()
mine = fb[fb.fire_day.notna() & (fb.season < 2025)].set_index(['season', 'cell_id']).fire_day
j = pd.concat([chk.rename('a'), mine.rename('b')], axis=1)
res = {'check_vs_fsi_v2': {'fsi_dated': int(j.a.notna().sum()), 'mine_dated': int(j.b.notna().sum()), 'same_day': int((j.a == j.b).sum())}}
print(res, flush=True)

burns = fb[fb.fire_day.notna()].copy()
burns = burns[(burns.fire_day.dt.strftime('%m-%d') >= '02-17') & (burns.fire_day.dt.strftime('%m-%d') <= '06-15')]
res['dated_burns_in_season'] = {int(k): int(c) for k, c in burns.groupby('season').size().items()}
res['near_share'] = round(float(burns.near.mean()), 3)

# ── scores ──
beat = pd.read_csv(P + 'ratapani/beats/cell_beat.csv').set_index('cell_id').beat_uid.reindex(range(n))
inb = beat.notna().values; bid = pd.factorize(beat.fillna(-1))[0]
pr = pd.read_parquet(P + 'research/prediction-review/results/pred_allcells_honest.parquet', columns=['season', 'date', 'cell_id', 'honest'])
pr['date'] = pd.to_datetime(pr['date'])
B = np.zeros((len(SEAS), n))
for r in bw.itertuples(): B[SEAS.index(r.season), r.cell_id] = 1
def hist(Y):
    k = [i for i, s in enumerate(SEAS) if s != Y and s < 2025]; return B[k].mean(0)
def pick(score, ok):
    """top 5 per beat among ok cells; returns bool mask"""
    s = np.where(ok & inb, score, -np.inf); o = np.lexsort((-s, bid)); sel = np.zeros(n, bool)
    b_sorted = bid[o]; first = np.r_[0, np.flatnonzero(np.diff(b_sorted)) + 1]
    rank = np.arange(n) - np.repeat(first, np.diff(np.r_[first, n]))
    take = o[(rank < 5) & np.isfinite(s[o])]; sel[take] = True; return sel
rules = ['random', 'history', 'model'] + [f'{b}_skip{g}' for b in ('random', 'history', 'model') for g in (1, 2, 3, 4, 5)]
rows = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days)
    P_Y = pr[pr.season == Y].pivot(index='date', columns='cell_id', values='honest').reindex(index=days, columns=range(n)).to_numpy()
    h = hist(Y) + 1e-6 * np.random.default_rng(Y).random(n)
    conf = np.full(n, np.datetime64('2100-01-01'), 'datetime64[ns]')
    for r in bw[bw.season == Y].itertuples(): conf[r.cell_id] = np.datetime64(r.window_end + pd.Timedelta('25D'))
    rng = np.random.default_rng(100 + Y)
    L = {k: np.zeros((T, n), bool) for k in rules}
    for ti, t in enumerate(days):
        ok = conf <= np.datetime64(t - pd.Timedelta('1D'))
        ok = ~ok
        base = {'random': rng.random(n), 'history': h, 'model': np.nan_to_num(P_Y[ti], nan=-1)}
        for k in rules:
            b = k.split('_')[0]; g = int(k[-1]) if '_skip' in k else 0
            okk = ok.copy()
            if g: okk &= ~L[k][max(0, ti - g):ti].any(0)
            L[k][ti] = pick(base[b], okk)
    bb = burns[burns.season == Y]
    for r in bb.itertuples():
        di = (r.fire_day - days[0]).days
        row = {'season': Y, 'cell_id': r.cell_id, 'near': r.near}
        for k in rules:
            row[k + '_w12'] = bool(L[k][max(0, di - 2):di, r.cell_id].any())
            row[k + '_w7'] = bool(L[k][max(0, di - 7):di, r.cell_id].any())
        rows.append(row)
    print('season', Y, len(bb), flush=True)
R = pd.DataFrame(rows); R.to_parquet(OUT + 'dated_once_rows.parquet', index=False)
def summ(d):
    o = {'burns': len(d)}
    for k in rules: o[k] = {'warned_1_2d': round(100 * d[k + '_w12'].mean(), 1), 'listed_1_7d': round(100 * d[k + '_w7'].mean(), 1)}
    return o
for nm, sl in (('loso_2017_24', R.season < 2025), ('test_2025_26', R.season >= 2025)):
    d = R[sl]; res[nm] = {'all': summ(d), 'far_new_starts': summ(d[~d.near]), 'near_recent_fire': summ(d[d.near])}
    res[nm]['per_season_warned_1_2d'] = {int(y): {k: round(100 * g[k + '_w12'].mean(), 1) for k in ('random', 'history', 'model', 'model_skip2')} for y, g in d.groupby('season')}
json.dump(res, open(OUT + 'results_dated_once.json', 'w'), indent=1); print(json.dumps({k: res[k] for k in res if k.startswith(('loso', 'test'))}, indent=0)[:3000]); print('DATED_ONCE_DONE')
