"""Cause signatures in Ratapani VIIRS (S-NPP 375 m, 2013-2024): time of day, weekday, FRP, persistence, crop proximity."""
import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
R = '/mnt/project-files/ratapani/'
v = pd.read_parquet(R + 'viirs_snpp_2013_2024.parquet')
G = json.load(open(R + 'grid_500m.geojson'))['features']
n = len(G); cen = np.zeros((n, 2)); ff = np.zeros(n)
for f in G:
    c = np.array(f['geometry']['coordinates'][0]); i = f['properties']['cell_id']; cen[i] = c[:, 0].mean(), c[:, 1].mean(); ff[i] = f['properties']['forest_frac']
k = np.cos(np.radians(23)); tr = cKDTree(np.c_[cen[:, 0] * k, cen[:, 1]])
d, idx = tr.query(np.c_[v.longitude * k, v.latitude], distance_upper_bound=0.004)
v['cell_id'] = np.where(np.isfinite(d), idx, -1)
print('points', len(v), 'in grid', (v.cell_id >= 0).sum())
v = v[v.cell_id >= 0].reset_index(drop=True)
wc = pd.read_csv(R + 'ee/worldcover.csv').set_index('cell_id'); px = pd.read_csv(R + 'ee/proximity.csv').set_index('cell_id')
v = v.join(wc[['wc_10', 'wc_20', 'wc_30', 'wc_40', 'wc_50']], on='cell_id').join(px, on='cell_id')
v['forest_frac'] = ff[v.cell_id]
# local time: acq_time is UTC hhmm; IST = UTC + 5:30
hh = v.acq_time // 100 + (v.acq_time % 100) / 60; v['ist'] = (hh + 5.5) % 24
v['dt_ist'] = pd.to_datetime(v.acq_date) + pd.to_timedelta(np.where(hh + 5.5 >= 24, 1, 0), 'D')
v['dow'] = v.dt_ist.dt.dayofweek  # 0 Monday
v['crop_cell'] = v.wc_40 >= 0.2
print('\n== type attribute ==\n', v['type'].value_counts().to_string())
print(v[v['type'] != 0][['acq_date', 'latitude', 'longitude', 'frp', 'wc_40', 'wc_80' if 'wc_80' in v else 'wc_50']].to_string())
print('\n== day overpass IST time quantiles ==', v[v.daynight == 'D'].ist.quantile([.05, .5, .95]).round(2).tolist(), ' night:', v[v.daynight == 'N'].ist.quantile([.05, .5, .95]).round(2).tolist())
# crop vs forest cells
v['grp'] = np.select([v.wc_40 >= 0.2, v.dist_crop_cell <= 1000], ['crop>=20%', 'forest<=1km of crop'], 'forest interior')
g = v.groupby('grp')
print('\n== by group ==')
print(pd.DataFrame({'n': g.size(), 'medFRP': g.frp.median(), 'p90FRP': g.frp.quantile(.9), 'night_share': g.daynight.apply(lambda s: (s == 'N').mean()),
                    'Apr15_May_share': g.dt_ist.apply(lambda s: ((s.dt.month == 5) | ((s.dt.month == 4) & (s.dt.day >= 15))).mean()),
                    'Feb_share': g.dt_ist.apply(lambda s: (s.dt.month <= 2).mean())}).round(3).to_string())
print('\n== month x group counts ==\n', pd.crosstab(v.dt_ist.dt.month, v.grp).to_string())
# weekly cycle: Monte Carlo test of max-min range (Earl et al. method), within-season permutation of day labels by week
def weekly(df, label, B=1000, rng=np.random.default_rng(0)):
    days = df.dt_ist.dt.normalize().value_counts()
    cal = pd.date_range(days.index.min(), days.index.max()); s = days.reindex(cal, fill_value=0)
    s = s[s.index.month.isin([1, 2, 3, 4, 5, 6])]
    cnt = s.groupby(s.index.dayofweek).sum().reindex(range(7), fill_value=0).values
    obs = cnt.max() - cnt.min()
    # null: shuffle daily counts within each calendar week (keeps seasonality)
    wk = (s.index - s.index[0]).days // 7; vals = s.values; sims = np.zeros(B)
    groups = [np.where(wk == w)[0] for w in np.unique(wk)]
    dows = s.index.dayofweek.values
    for b in range(B):
        perm = np.empty_like(vals)
        for gi in groups: perm[gi] = vals[rng.permutation(gi)]
        c = np.bincount(dows, perm, 7); sims[b] = c.max() - c.min()
    p = (sims >= obs).mean()
    print(f'{label:24s} counts Mon..Sun {cnt.tolist()} range {obs} p={p:.3f}  Sun/mean={cnt[6] / cnt.mean():.2f}')
print('\n== weekly cycle (Jan-Jun, within-week shuffle null) ==')
weekly(v, 'all')
for gname, d_ in v.groupby('grp'): weekly(d_, gname, B=1000)
weekly(v[v.dt_ist.dt.month <= 2], 'Jan-Feb all', B=1000)
# event clustering: same cell neighbourhood (<=750 m) within 1 day -> events
v = v.sort_values('dt_ist').reset_index(drop=True)
xy = np.c_[v.longitude * k * 111.32, v.latitude * 110.57]  # km
t = (v.dt_ist.dt.normalize() - pd.Timestamp('2013-01-01')).dt.days.values
parent = np.arange(len(v))
def find(a):
    while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
    return a
trk = cKDTree(np.c_[xy, t * 1000.0])  # time scaled so 1 day = 1000 km -> only same-day pairs within 0.75 km
for a, b in trk.query_pairs(0.75): parent[find(a)] = find(b)
tr2 = cKDTree(xy)
for a, b in tr2.query_pairs(0.75):
    if abs(t[a] - t[b]) <= 1: parent[find(a)] = find(b)
v['ev'] = [find(i) for i in range(len(v))]
E = v.groupby('ev').agg(n=('frp', 'size'), days=('dt_ist', lambda s: s.dt.normalize().nunique()), frp_max=('frp', 'max'), frp_sum=('frp', 'sum'),
                        night=('daynight', lambda s: (s == 'N').any()), start=('dt_ist', 'min'), crop=('wc_40', 'mean'), dcrop=('dist_crop_cell', 'mean'),
                        dvil=('dist_village', 'mean'), depth=('depth_in_forest', 'mean'), lon=('longitude', 'mean'), lat=('latitude', 'mean'))
def elong(gr):
    if len(gr) < 3: return np.nan
    p = np.c_[gr.longitude * k * 111.32, gr.latitude * 110.57]; p = p - p.mean(0); ev_ = np.linalg.eigvalsh(np.cov(p.T)); return np.sqrt(ev_[1] / max(ev_[0], 1e-4))
E['elong'] = v.groupby('ev').apply(elong)
E['month'] = E.start.dt.month
print('\n== events ==', len(E), 'points/event median', E.n.median(), ' share multi-day', (E.days > 1).mean().round(3), ' share with night det', E.night.mean().round(3))
E['size_cls'] = pd.cut(E.n, [0, 1, 3, 10, 1e9], labels=['1', '2-3', '4-10', '>10'])
print(pd.crosstab(E.month, E.size_cls).to_string())
print('\nnight share and multi-day share by month:\n', E.groupby('month').agg(n=('n', 'size'), night=('night', 'mean'), multiday=('days', lambda s: (s > 1).mean()), medfrpmax=('frp_max', 'median')).round(3).to_string())
E['managed_flag'] = (E.month.isin([11, 12, 1, 2]) | ((E.month == 2))) & (~E.night) & (E.days == 1) & (E.frp_max <= v.frp.median())
print('\nprobable managed (Nov-Feb, day-only, 1 day, FRPmax<=median):', int(E.managed_flag.sum()), 'of', int(E.month.isin([11, 12, 1, 2]).sum()), 'Nov-Feb events; all events', len(E))
print('elongated (>=3 pts & elong>=3) events by month:\n', E[(E.elong >= 3)].month.value_counts().sort_index().to_string())
# repeat-ignition cells: cells with VIIRS in many seasons
v['season'] = v.dt_ist.dt.year
cy = v.groupby('cell_id').season.nunique()
nyrs = v.season.nunique()
print('\n== repeat cells ==  seasons', nyrs, ' cells with any detection', len(cy))
print(cy.value_counts().sort_index().to_string())
# compare to null with same per-season counts placed at random among the cells that ever burned (any VIIRS or scar) -- Poisson-binomial approx
pcell = v.groupby('season').cell_id.nunique() / n
null = np.random.default_rng(1).random((2000, len(pcell), n)) < pcell.values[None, :, None]
nul = null.sum(1)
print('null (spatially random) share of cells with >=6 seasons:', (nul >= 6).mean().round(4), ' observed:', ((cy >= 6).sum() / n).round(4))
E.to_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/cause_an/events.parquet'); v.to_parquet('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/cause_an/viirs_cells.parquet')
