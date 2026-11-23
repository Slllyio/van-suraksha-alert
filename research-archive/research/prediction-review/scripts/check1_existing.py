"""Independent re-check of the 2-day cell headline from saved predictions (read-only inputs).
Reproduces the lean-ensemble recall at 5 per beat per day, then asks what the number is made of:
simple baselines, perfect-model ceiling, window widths, after-fire days, near-active-fire share, within-day AUC.
Usage: python3 check1_existing.py   -> ../results/check1.json"""
import json, importlib.util, numpy as np, pandas as pd
from scipy.spatial import cKDTree
RS = '/mnt/project-files/research/'; RA = '/mnt/project-files/ratapani/'; OUT = RS + 'prediction-review/results/'
spec = importlib.util.spec_from_file_location('ps', RS + 'ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
beat = pd.read_csv(RA + 'beats/cell_beat.csv').set_index('cell_id').beat_uid
n = 3614; res = {}

lab = ps.labels(range(2017, 2027)); lab['b'] = lab.cell_id.map(beat).values
ens = pd.read_parquet(RS + 'ratapani-ignition/results/lean_ensemble_pred.parquet'); ens['date'] = pd.to_datetime(ens['date'])
m = lab.merge(ens, on=['season', 'date', 'cell_id'], how='left')

# burn-history prior from other seasons (LOSO inside 2017-24; 2017-24 only for 2025-26)
bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
bw1 = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
B = {Y: np.zeros(n) for Y in range(2017, 2027)}
for r in bw1.itertuples():
    if r.season in B: B[r.season][r.cell_id] = 1
def prior(Y):
    tr = [s for s in range(2017, 2025) if s != Y]; return sum(B[s] for s in tr) / len(tr)
m['prior'] = np.nan
for Y in range(2017, 2027):
    k = m.season == Y; m.loc[k, 'prior'] = prior(Y)[m.cell_id[k].values]
rng = np.random.default_rng(0); m['random'] = rng.random(len(m)); m['prior_tb'] = m.prior + 1e-6 * m.random
m['perfect'] = m.pos.astype(float) + 1e-6 * m.random

def rec(d, col, k=5, w=None):
    r = d[col].fillna(-1e9).groupby([d.season, d.date, d.b]).rank('first', ascending=False)
    sel = r <= k
    if w is None: return round(100 * float(d.pos[sel].sum() / d.pos.sum()), 1)
    return round(100 * float((d.pos & sel)[w].sum() / d.pos[w].sum()), 1)
win = (m.date.dt.month * 100 + m.date.dt.day).between(215, 615)
for nm, sl in (('loso', m.season < 2025), ('test2526', m.season >= 2025)):
    for wn, ww in (('feb1_jun20', True), ('feb15_jun15', win)):
        d = m[sl & ww]
        res[f'{nm}_{wn}'] = {c: rec(d, c) for c in ('random', 'prior_tb', 'lean_clf', 'lean_ensemble', 'perfect')}
        res[f'{nm}_{wn}']['positives'] = int(d.pos.sum()); res[f'{nm}_{wn}']['valid_cell_days'] = len(d)
print(json.dumps(res, indent=1), flush=True)

# ── what the positives are made of ──
first = bw1[bw1.season.between(2017, 2026)].copy(); first['width'] = (first.window_end - first.window_start).dt.days
P = m[m.pos].merge(first[['season', 'cell_id', 'window_start', 'window_end', 'width', 'burned_ha']], on=['season', 'cell_id'])
res['window_width_days_of_first_burns'] = first.width.describe(percentiles=[.25, .5, .75, .9]).round(1).to_dict()
res['share_positive_celldays_in_windows_gt7d'] = round(float((P.width > 7).mean()), 3)
res['share_positive_celldays_in_windows_gt14d'] = round(float((P.width > 14).mean()), 3)
res['share_first_burns_lt2ha'] = round(float((first.burned_ha < 2).mean()), 3)
res['share_positive_celldays_burned_lt2ha'] = round(float((P.burned_ha < 2).mean()), 3)

# cell-window recall: a first-burn window counts once, caught if listed on any of its positive days
r5 = m.lean_ensemble.fillna(-1e9).groupby([m.season, m.date, m.b]).rank('first', ascending=False) <= 5
rr = m.random.groupby([m.season, m.date, m.b]).rank('first', ascending=False) <= 5
m['sel_ens'] = r5; m['sel_rand'] = rr
cw = m[m.pos].groupby(['season', 'cell_id']).agg(ens=('sel_ens', 'any'), rnd=('sel_rand', 'any'), ndays=('pos', 'size'))
for nm, sl in (('loso', cw.index.get_level_values(0) < 2025), ('test2526', cw.index.get_level_values(0) >= 2025)):
    c = cw[sl]; res[f'cell_window_recall_{nm}'] = {'lean_ensemble': round(100 * c.ens.mean(), 1), 'random': round(100 * c.rnd.mean(), 1), 'windows': len(c)}
    # windows short enough to be a real 2-day forecast (<=3 positive days)
    s = c[c.ndays <= 3]; res[f'cell_window_recall_short_{nm}'] = {'lean_ensemble': round(100 * s.ens.mean(), 1), 'random': round(100 * s.rnd.mean(), 1), 'windows': len(s)}

# ── concentration: how many positives sit on beat-days with many burning cells ──
bd = m[m.season < 2025].groupby(['season', 'date', 'b']).pos.sum()
pos_bd = bd[bd > 0]
res['positives_on_beatdays_with_gt5'] = round(float(pos_bd[pos_bd > 5].sum() / pos_bd.sum()), 3)
res['positives_on_beatdays_with_gt10'] = round(float(pos_bd[pos_bd > 10].sum() / pos_bd.sum()), 3)
res['beatdays_with_any_positive_share'] = round(float((bd > 0).mean()), 3)

# ── after-fire days and near-active-fire share (S-NPP VIIRS, the only sensor in every season 2017-26) ──
G = json.load(open(RA + 'grid_500m.geojson'))['features']; xy = np.zeros((n, 2))
for f in G: p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)
from pyproj import Transformer
tf = Transformer.from_crs(4326, 32643, always_xy=True)
v = pd.concat([pd.read_csv(f'/mnt/project-files/fire-alert-scars/alerts/viirs-snpp_{y}.csv') for y in range(2017, 2027)])
v['date'] = pd.to_datetime(v.acq_date); vx, vy = tf.transform(v.longitude.values, v.latitude.values); v['x'] = vx; v['y'] = vy
tree = cKDTree(xy)
# for each cell-day: VIIRS within 1.5 km of the cell centre in days t-3..t-1 (what a live system knows at issue time)
near = set()
for r in v.itertuples():
    for c in tree.query_ball_point((r.x, r.y), 1500):
        for k in (1, 2, 3): near.add((r.date + pd.Timedelta(days=k), c))
m['near_recent'] = [(d, c) in near for d, c in zip(m.date, m.cell_id)]
for nm, sl in (('loso', m.season < 2025), ('test2526', m.season >= 2025)):
    d = m[sl]
    res[f'near_recent_{nm}'] = {
        'share_of_positives_near_recent_viirs': round(float(d.near_recent[d.pos].mean()), 3),
        'share_of_valid_celldays_near_recent_viirs': round(float(d.near_recent.mean()), 3),
        'base_rate_near': round(float(d.pos[d.near_recent].mean()), 4), 'base_rate_far': round(float(d.pos[~d.near_recent].mean()), 4),
        'recall_ens_positives_near': rec(d, 'lean_ensemble', w=d.near_recent), 'recall_ens_positives_far': rec(d, 'lean_ensemble', w=~d.near_recent),
        'recall_rand_positives_near': rec(d, 'random', w=d.near_recent), 'recall_rand_positives_far': rec(d, 'random', w=~d.near_recent),
        'recall_prior_positives_far': rec(d, 'prior_tb', w=~d.near_recent)}
    # a trivial "near recent VIIRS first, then prior" ranker
    d = d.assign(nearprior=d.near_recent * 10 + d.prior_tb)
    res[f'near_recent_{nm}']['recall_nearrecent_then_prior_all'] = rec(d, 'nearprior')

# ── true-lead split (FSI thread's v2 labels): which positive days are before vs after the VIIRS fire day ──
tl = pd.read_parquet(RA + 'fsi/true_lead_labels_v2.parquet'); tl['date'] = pd.to_datetime(tl['date'])
q = m[m.season < 2025].merge(tl[['season', 'date', 'cell_id', 'fire_day', 'dated']], on=['season', 'date', 'cell_id'], how='left')
qp = q[q.pos & q.dated.fillna(False)]
lead = (qp.fire_day - qp.date).dt.days
res['dated_positive_celldays'] = int(len(qp))
res['positive_days_lead_ge1_true_forecast'] = round(float((lead >= 1).mean()), 3)
res['positive_days_lead_ge3'] = round(float((lead >= 3).mean()), 3)
res['positive_days_lead_le0_after_fire'] = round(float((lead <= 0).mean()), 3)
for nm, w_ in (('lead_1_2', lead.between(1, 2)), ('lead_3plus', lead >= 3), ('after_fire', lead <= 0)):
    idx = qp.index[w_.values]
    res[f'ens_hit_rate_{nm}'] = round(100 * float(q.loc[idx, 'sel_ens'].mean()), 1); res[f'rand_hit_rate_{nm}'] = round(100 * float(q.loc[idx, 'sel_rand'].mean()), 1)

# ── within-day ranking AUC (mean over issue days of AUC across valid cells) ──
from sklearn.metrics import roc_auc_score
def wd_auc(d, col):
    a = [roc_auc_score(g.pos, g[col]) for _, g in d.groupby(['season', 'date']) if 0 < g.pos.sum() < len(g)]
    return round(float(np.mean(a)), 3)
for nm, sl in (('loso', m.season < 2025), ('test2526', m.season >= 2025)):
    d = m[sl]; res[f'within_day_auc_{nm}'] = {c: wd_auc(d, c) for c in ('prior_tb', 'lean_ensemble')}
json.dump(res, open(OUT + 'check1.json', 'w'), indent=1); print(json.dumps(res, indent=1)); print('CHECK1_DONE')
