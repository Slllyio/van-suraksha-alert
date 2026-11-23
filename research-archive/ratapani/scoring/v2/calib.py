"""Honest % per square on the v2 key (dated_once.py): chance that this square's first burn of the season STARTS
(VIIRS fire day) in the next 2 days, t+1 or t+2. Issue days Feb 15 - Jun 13; live pool (cells not confirmed burned
by t-1). Cells whose first burn is undated are dropped (we cannot say when they burned).
Model score: honest lean classifier (research/prediction-review/results/pred_allcells_honest.parquet).
Steps, all leave-one-season-out over 2017-24 (2025-26 uses 2017-24):
  iso      isotonic map from model score to the v2 outcome
  iso+k    iso times an in-season correction k_t = (O + 20) / (E + 20), where O = S-NPP VIIRS points in Ratapani
           from Feb 1 to t-1 this season and E = training-season mean of the same count (known live, no labels needed)
Baselines: day-of-year climatology (7-day smoothed rate) and burn history x day-of-year (isotonic on history score
times climatology). Reported: Brier skill vs climatology, reliability bins, season total predicted vs observed,
and the top 1% of squares' observed rate ("times normal").  Out: v2/results_calib.json"""
import json, numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression
P = '/mnt/project-files/'; OUT = P + 'ratapani/scoring/v2/'; n = 3614; SEAS = list(range(2017, 2027))
fb = pd.read_parquet(OUT + 'dated_burns_2017_2026.parquet')
pr = pd.read_parquet(P + 'research/prediction-review/results/pred_allcells_honest.parquet', columns=['season', 'date', 'cell_id', 'honest'])
pr['date'] = pd.to_datetime(pr['date']); pr = pr[(pr.date.dt.strftime('%m-%d') >= '02-15') & (pr.date.dt.strftime('%m-%d') <= '06-13')]
pr = pr.merge(fb, on=['season', 'cell_id'], how='left')
conf = pr.window_end + pd.Timedelta('25D')
live = ~(conf <= pr.date - pd.Timedelta('1D'))
undated = pr.window_end.notna() & pr.fire_day.isna()
lead = (pr.fire_day - pr.date).dt.days
already = pr.fire_day.notna() & (lead <= 0)                          # burn already started (fire day known live from VIIRS)
d = pr[live & ~undated & ~already].copy(); d['y'] = lead[d.index].isin([1, 2]).astype(float)
d['doy'] = d.date.dt.dayofyear
# burn history: share of other training seasons each cell burned
bw = pd.read_csv(P + 'research/ratapani-burn-labels/burn_windows.csv'); bw = bw[bw.burned == 1].drop_duplicates(['season', 'cell_id'])
B = np.zeros((len(SEAS), n))
for r in bw.itertuples(): B[SEAS.index(r.season), r.cell_id] = 1
# live in-season activity: S-NPP VIIRS points in the Ratapani grid box, Feb 1 to t-1
v = pd.read_parquet(P + 'ratapani/viirs_snpp_2013_2024.parquet')[['latitude', 'longitude', 'acq_date', 'confidence']]
v = pd.concat([v] + [pd.read_csv(P + f'fire-alert-scars/alerts/viirs-snpp_{Y}.csv')[['latitude', 'longitude', 'acq_date', 'confidence']] for Y in (2025, 2026)])
G = json.load(open(P + 'ratapani/grid_500m.geojson'))['features']
lon = np.array([c[0] for f in G for c in f['geometry']['coordinates'][0]]); lat = np.array([c[1] for f in G for c in f['geometry']['coordinates'][0]])
v = v[v.confidence.astype(str).str.lower().isin(['n', 'h', 'nominal', 'high']) & v.longitude.between(lon.min(), lon.max()) & v.latitude.between(lat.min(), lat.max())].copy()
v['date'] = pd.to_datetime(v.acq_date); v['season'] = v.date.dt.year; v = v[v.date.dt.month <= 6]
cum = {}
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-30'); c = v[v.season == Y].groupby('date').size().reindex(days, fill_value=0).cumsum().shift(1, fill_value=0)
    cum[Y] = pd.Series(c.values, index=days.dayofyear)
d['O'] = [cum[s].get(k, 0) for s, k in zip(d.season.values, d.doy.values)]
d['clim'] = np.nan; d['hist'] = np.nan; d['iso'] = np.nan; d['isok'] = np.nan; d['k'] = np.nan
for Y in SEAS:
    trS = [s for s in range(2017, 2025) if s != Y]; tr = d[d.season.isin(trS)]; te = d.season == Y
    c = tr.groupby('doy').y.mean().rolling(7, center=True, min_periods=1).mean()
    clim = d.loc[te, 'doy'].map(c).fillna(tr.y.mean()).values
    hs = B[[SEAS.index(s) for s in trS]].mean(0)
    ih = IsotonicRegression(out_of_bounds='clip').fit(hs[tr.cell_id.values] * tr.doy.map(c).values, tr.y.values)
    ir = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(tr.honest.values, tr.y.values)
    E = pd.concat([cum[s] for s in trS], axis=1).mean(1)
    k = ((d.loc[te, 'O'].values + 20) / (d.loc[te, 'doy'].map(E).values + 20))
    # fit how strongly k should apply (exponent a) on training seasons, by Brier
    trk = (tr.O.values + 20) / (tr.doy.map(E).values + 20); itr = ir.predict(tr.honest.values)
    a = min(np.linspace(0, 1.5, 16), key=lambda a: np.mean((np.clip(itr * trk ** a, 0, 1) - tr.y.values) ** 2))
    d.loc[te, 'clim'] = clim; d.loc[te, 'hist'] = ih.predict(hs[d.loc[te, 'cell_id'].values] * clim)
    d.loc[te, 'iso'] = ir.predict(d.loc[te, 'honest'].values); d.loc[te, 'k'] = k ** a
    d.loc[te, 'isok'] = np.clip(d.loc[te, 'iso'].values * k ** a, 0, 1)
    print(Y, 'a', round(float(a), 2), flush=True)
def brier(p, y): return float(np.mean((p - y) ** 2))
res = {'rows': len(d), 'positives': int(d.y.sum())}
for nm, sl in (('loso_2017_24', d.season < 2025), ('test_2025_26', d.season >= 2025)):
    x = d[sl]; y = x.y.values; bc = brier(x.clim.values, y)
    o = {'base_rate_pct': round(100 * y.mean(), 3)}
    for c in ('hist', 'iso', 'isok'): o[f'brier_skill_{c}_vs_doy'] = round(1 - brier(x[c].values, y) / bc, 4)
    bins = [0, .002, .005, .01, .02, .05, .1, 1]; xb = x.assign(bin=pd.cut(x.isok, bins, include_lowest=True))
    o['reliability_isok'] = {str(k): {'pred_pct': round(100 * g.isok.mean(), 2), 'obs_pct': round(100 * g.y.mean(), 2), 'share': round(len(g) / len(x), 3)} for k, g in xb.groupby('bin', observed=True)}
    o['season_total'] = {int(s): {'observed': int(g.y.sum()), 'iso': round(float(g.iso.sum())), 'iso_k': round(float(g.isok.sum()))} for s, g in x.groupby('season')}
    top = x.groupby('date', group_keys=False).apply(lambda g: g[g.isok >= g.isok.quantile(0.99)])
    o['top1pct_daily'] = {'obs_pct': round(100 * top.y.mean(), 2), 'times_normal': round(top.y.mean() / y.mean(), 1), 'pred_pct': round(100 * top.isok.mean(), 2)}
    o['max_pred_pct'] = round(100 * float(x.isok.max()), 1)
    res[nm] = o
json.dump(res, open(OUT + 'results_calib.json', 'w'), indent=1); print(json.dumps(res, indent=1)); print('CALIB_DONE')
