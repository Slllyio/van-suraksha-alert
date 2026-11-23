"""Controlled-burn (fire-line) filter test (fire_management_practice.md D2), lean model, real beats.
Tag an alert-scar event probable_managed if: date <= 20 Feb, all alerts daytime, cluster FRP <= season median,
and the scar is elongated (longest side of the minimum rotated rectangle / sqrt(area) >= 10) or linear-thin.
Then: how many SCORING.md positives (Feb) sit in a managed scar; retrain with them dropped from training;
score with and without them.
Usage: python3 managed.py OUTDIR
"""
import sys, os, json, numpy as np, pandas as pd, lightgbm as lgb
from shapely.geometry import shape, box
from shapely.ops import transform as stransform
from shapely.strtree import STRtree
import pyproj
FA = '/mnt/project-files/fire-alert-scars/'
lk = pd.read_csv(FA + 'alert_scar_lookup.csv', low_memory=False); lk['acq_date'] = pd.to_datetime(lk.acq_date)
lk['night'] = lk.acq_time.astype(str).str.zfill(4).str[:2].astype(int).between(18, 23) | lk.acq_time.astype(str).str.zfill(4).str[:2].astype(int).between(0, 5)
ev_stats = lk.groupby('event_id').agg(date=('acq_date', 'min'), any_night=('night', 'max'), frp=('frp', 'median'), n=('alert_id', 'size'))
ev_stats['season'] = np.where(ev_stats.date.dt.month >= 8, ev_stats.date.dt.year + 1, ev_stats.date.dt.year)
ev_stats['frp_med_season'] = ev_stats.groupby('season').frp.transform('median')
to_utm = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
feats = json.load(open(FA + 'event_scars.geojson'))['features']
geoms = {}; elong = {}
for f in feats:
    p = f['properties']
    if p.get('status') not in ('scar', 'scar_faint'): continue
    g = stransform(to_utm, shape(f['geometry'])); geoms[p['event_id']] = g
    mrr = g.minimum_rotated_rectangle; xs, ys = mrr.exterior.coords.xy
    sides = [np.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(2)]
    L = max(sides); elong[p['event_id']] = L / np.sqrt(max(g.area, 1.0))
ev_stats['elong'] = pd.Series(elong); ev_stats = ev_stats[ev_stats.elong.notna()]
m = ev_stats.date.dt.month; d = ev_stats.date.dt.day
ev_stats['winter'] = (m.isin([11, 12, 1])) | ((m == 2) & (d <= 20))
ev_stats['managed'] = ev_stats.winter & (~ev_stats.any_night.astype(bool)) & (ev_stats.frp <= ev_stats.frp_med_season) & (ev_stats.elong >= 10)
print('events with scar', len(ev_stats), 'winter', int(ev_stats.winter.sum()), 'managed', int(ev_stats.managed.sum()),
      'share of winter', round(float(ev_stats.managed.sum() / max(ev_stats.winter.sum(), 1)), 3), flush=True)
print('elongation quantiles winter', ev_stats[ev_stats.winter].elong.quantile([.5, .75, .9, .95]).round(1).tolist(), flush=True)
# cells of managed scars
RP_ = '/mnt/project-files/ratapani/'
G_ = json.load(open(RP_ + 'grid_500m.geojson'))['features']
cells = {f['properties']['cell_id']: box(f['properties']['x0'], f['properties']['y0'], f['properties']['x0'] + 500, f['properties']['y0'] + 500) for f in G_}
ids = np.array(list(cells)); tree = STRtree([cells[i] for i in ids])
rows = []
for eid in ev_stats[ev_stats.managed].index:
    g = geoms[eid]
    for j in tree.query(g):
        if g.intersection(cells[ids[j]]).area / 1e4 >= 0.25: rows.append((ev_stats.loc[eid, 'season'], int(ids[j]), ev_stats.loc[eid, 'date']))
mg = pd.DataFrame(rows, columns=['season', 'cell_id', 'mdate']).drop_duplicates(['season', 'cell_id'])
print('managed cell-seasons', len(mg), flush=True)
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lean_plus.py')).read()
src = src[:src.index('for cfg in CONFIGS:')]
sys.argv = [sys.argv[0], sys.argv[1], 'none']
exec(compile(src, 'lean_plus.py', 'exec'))
OUT = sys.argv[1]
# positives whose first-burn window overlaps a managed scar in that cell-season, within 10 days of the managed event date
fb = bw[['season', 'cell_id', 'window_start', 'window_end']].merge(mg, on=['season', 'cell_id'])
fb = fb[(fb.mdate >= fb.window_start - pd.Timedelta(days=10)) & (fb.mdate <= fb.window_end + pd.Timedelta(days=10))]
X = X.merge(fb[['season', 'cell_id']].assign(managed=1.0), on=['season', 'cell_id'], how='left'); X['managed'] = X.managed.fillna(0.0)
npos = int(X.pos.sum()); nman = int((X.pos & (X.managed == 1)).sum()); feb = X.date.dt.month == 2
print('positives', npos, 'in managed scars', nman, 'share', round(nman / npos, 4), 'Feb positives', int(X.pos[feb].sum()), 'Feb managed', int((X.pos & (X.managed == 1))[feb].sum()), flush=True)
res['counts'] = {'events_with_scar': len(ev_stats), 'winter_events': int(ev_stats.winter.sum()), 'managed_events': int(ev_stats.managed.sum()), 'positives': npos, 'positives_in_managed': nman, 'feb_positives': int(X.pos[feb].sum()), 'feb_managed': int((X.pos & (X.managed == 1))[feb].sum())}
def fit_drop(tr_seasons, te_seasons, feat):
    set_prior(tr_seasons)
    tr = X.season.isin(tr_seasons).values & (X.managed.values == 0); te = X.season.isin(te_seasons).values
    rs = np.random.default_rng(0); keep = tr & (X.pos.values | (rs.random(len(X)) < 0.25)); wt = np.where(X.pos.values[keep], 1.0, 4.0)
    gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1)
    gb.fit(X.loc[keep, feat], X.pos.values[keep], sample_weight=wt); return gb.predict_proba(X.loc[te, feat])[:, 1], te
def score_excl(col, seasons, excl):
    m = X[X.season.isin(seasons) & ~(excl & X.pos)]  # drop managed positives from scoring (keep as negatives? no: drop rows)
    r = m[col].fillna(-1e9).groupby([m.season, m.date, m.beat]).rank('first', ascending=False)
    return round(float(m.pos[r <= 5].sum() / m.pos.sum()), 4)
run('base', BASE)
P = np.full(len(X), np.nan)
for Y in range(2017, 2025):
    p, te = fit_drop([s for s in range(2017, 2025) if s != Y], [Y], BASE); P[te] = p
X['nomanaged'] = P; p, te = fit_drop(list(range(2017, 2025)), [2025, 2026], BASE); X.loc[te, 'nomanaged'] = p
ex = X.managed.values == 1
for col in ('base', 'nomanaged'):
    res[col + '_scoring'] = {'with_managed_loso': score_excl(col, range(2017, 2025), np.zeros(len(X), bool)), 'without_managed_loso': score_excl(col, range(2017, 2025), ex),
                             'with_managed_test': score_excl(col, [2025, 2026], np.zeros(len(X), bool)), 'without_managed_test': score_excl(col, [2025, 2026], ex)}
    print(col, res[col + '_scoring'], flush=True)
json.dump(res, open(os.path.join(OUT, 'managed_results.json'), 'w'), indent=1)
print('MANAGED_DONE', flush=True)
