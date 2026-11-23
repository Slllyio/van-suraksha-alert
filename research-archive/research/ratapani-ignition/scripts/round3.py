"""Scouting round 3 feature groups on top of the lean model (real beats, SCORING.md).
Groups (all causal: values up to t-1 only, climatologies leave-season-out):
  PHEN  leaf-fall phenology: frac_dropped, days since d10/d50/d85, slope15/30, frac_dropped anomaly, NDMI drop,
        within-beat ranks, looks in last 30 d, age of newest look
  MEM   EWMA memory (half-lives 3/7/15 d) of Tmax, RH, rain, NDMI
  HIST  same +-7-day calendar window burned in other training seasons, cell and 3x3 block
  CAL   days since Holi
  VSIG  per-cell VIIRS signature from other years: night share, median first-detection DOY, early burner, detections/yr
Also: share of top-5 picks on cells already burned this season; leaf fall -> fire lag.
Usage: python3 round3.py OUTDIR [configs]
"""
import sys, os, json, numpy as np, pandas as pd, lightgbm as lgb
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lean_plus.py')).read()
src = src[:src.index('for cfg in CONFIGS:')]
CFG = sys.argv[2].split(',') if len(sys.argv) > 2 else ['base', 'phen', 'mem', 'hist', 'cal', 'vsig', 'all']
sys.argv = [sys.argv[0], sys.argv[1], 'none']
exec(compile(src, 'lean_plus.py', 'exec'))
OUT = sys.argv[1]
X['t'] = X.date.values
# ------------------------------------------------------------------ PHEN
mo = pd.read_csv(RP + 'ee/modis_ndvi_ndmi.csv', parse_dates=['date'])
mo['season'] = np.where(mo.date.dt.month >= 8, mo.date.dt.year + 1, mo.date.dt.year)
pk = mo[(mo.date.dt.month >= 8) & (mo.date.dt.month <= 10)].groupby(['season', 'cell_id']).ndvi.quantile(0.95).rename('ndvi_peak').reset_index()
pk_cell = pk.groupby('cell_id').ndvi_peak.median()
# floor: cell median over seasons of 5th pct Mar-May S2 NDVI, leave-season-out
s2 = sc.copy(); s2['season'] = np.where(s2.date.dt.month >= 8, s2.date.dt.year + 1, s2.date.dt.year)
fl = s2[s2.date.dt.month.isin([3, 4, 5])].groupby(['season', 'cell_id']).ndvi.quantile(0.05).rename('fl').reset_index()
def loso_med(df, col, Y):
    return df[df.season != Y].groupby('cell_id')[col].median()
nd_last = dyn['ndvi_last']; ndmi_last = dyn['ndmi_last']
looks = sc.pivot_table(index='date', columns='cell_id', values='ndvi', aggfunc='size').reindex(index=cal, columns=range(n)).notna().astype(float).shift(1)
looks30 = looks.rolling(30, min_periods=1).sum()
age = (looks.cumsum() > 0).astype(float)  # placeholder, replaced per day below
ph = {}
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); di = cal.get_indexer(days)
    peak = pk[pk.season == Y].set_index('cell_id').ndvi_peak.reindex(range(n)).fillna(pk_cell).to_numpy(np.float32)
    floor = loso_med(fl, 'fl', Y).reindex(range(n)).to_numpy(np.float32)
    amp = np.maximum(peak - floor, 0.05)
    start = cal.get_loc(max(pd.Timestamp(f'{Y-1}-11-01'), cal[0]))
    nd = nd_last.to_numpy(np.float32)[start: di[-1] + 1]  # Nov 1 .. Jun 20, past-only ffilled values
    fd = np.clip((peak[None, :] - nd) / amp[None, :], -0.2, 1.2)
    f = {}
    off = di[0] - start; T = len(days)
    f['ph_frac_dropped'] = fd[off: off + T]
    for q, tag in ((0.10, 'd10'), (0.50, 'd50'), (0.85, 'd85')):
        hit = np.where(np.isnan(fd), False, fd >= q); first = np.where(hit.any(0), hit.argmax(0), 10 ** 6)
        dsd = np.arange(off, off + T)[:, None] - first[None, :]
        f[f'ph_days_since_{tag}'] = np.where(dsd >= 0, dsd, np.nan).astype(np.float32)
    f['ph_slope15'] = (nd[off: off + T] - nd[off - 15: off - 15 + T]) / 15
    f['ph_slope30'] = (nd[off: off + T] - nd[off - 30: off - 30 + T]) / 30
    nm = ndmi_last.to_numpy(np.float32)[di]
    nm_peak = mo[(mo.season == Y) & (mo.date.dt.month >= 8) & (mo.date.dt.month <= 10)].groupby('cell_id').ndmi.quantile(0.95).reindex(range(n)).to_numpy(np.float32)
    nm_fl = loso_med(s2[s2.date.dt.month.isin([3, 4, 5])].groupby(['season', 'cell_id']).ndmi.quantile(0.05).rename('fl').reset_index(), 'fl', Y).reindex(range(n)).to_numpy(np.float32)
    f['ph_ndmi_drop'] = np.clip((nm_peak[None, :] - nm) / np.maximum(nm_peak - nm_fl, 0.05)[None, :], -0.2, 1.2)
    f['ph_looks30'] = looks30.to_numpy(np.float32)[di]
    lk = looks.to_numpy()[:di[-1] + 1]; idx = np.where(lk == 1, np.arange(len(lk))[:, None], -10 ** 6); last_look = np.maximum.accumulate(idx, 0)
    f['ph_age_look'] = np.clip(np.arange(di[0], di[-1] + 1)[:, None] - last_look[di], 0, 200).astype(np.float32)
    ph[Y] = f
# frac_dropped anomaly vs cell's same-DOY median in other seasons
doy_fd = {Y: ph[Y]['ph_frac_dropped'] for Y in SEAS}
for Y in SEAS:
    others = np.stack([doy_fd[Z][:len(doy_fd[Y])] if len(doy_fd[Z]) >= len(doy_fd[Y]) else np.pad(doy_fd[Z], ((0, len(doy_fd[Y]) - len(doy_fd[Z])), (0, 0)), constant_values=np.nan) for Z in SEAS if Z != Y])
    ph[Y]['ph_fd_anom'] = doy_fd[Y] - np.nanmedian(others, 0)
    for k in ('ph_frac_dropped', 'ph_days_since_d50'):
        v = ph[Y][k]; ph[Y][k.replace('ph_', 'ph_beatrank_')] = pd.DataFrame(v).T.groupby(beat_code).rank(pct=True).T.to_numpy(np.float32)
def attach(group):
    frames = []
    for Y in SEAS:
        days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days)
        tt, cc_ = np.meshgrid(np.arange(T), np.arange(n), indexing='ij')
        df = pd.DataFrame({k: np.asarray(v, np.float32).reshape(-1) for k, v in group[Y].items()}); df['season'] = Y; df['date'] = days[tt.reshape(-1)]; df['cell_id'] = cc_.reshape(-1)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
X = X.merge(attach(ph), on=['season', 'date', 'cell_id'], how='left'); del ph
PHEN = [c for c in X.columns if c.startswith('ph_')]
# ------------------------------------------------------------------ MEM
mem = {}
for hl in (3, 7, 15):
    a = np.exp(-np.log(2) / hl)
    for c in ('T2M_MAX', 'RH2M', 'PRECTOTCORR'):
        mem[f'mem_{c}_{hl}'] = w[c].ewm(alpha=1 - a).mean().shift(1)
wm = pd.DataFrame(mem); X = X.join(wm, on='date')
ndmi_d = sc.pivot_table(index='date', columns='cell_id', values='ndmi').reindex(index=cal, columns=range(n)).shift(1)
memc = {}
for hl in (7, 15):
    memc[hl] = ndmi_d.ewm(halflife=hl, ignore_na=True).mean()
mc = {Y: {f'mem_ndmi_{hl}': memc[hl].to_numpy(np.float32)[cal.get_indexer(pd.date_range(f'{Y}-02-01', f'{Y}-06-20'))] for hl in (7, 15)} for Y in SEAS}
X = X.merge(attach(mc), on=['season', 'date', 'cell_id'], how='left'); del mc, memc
MEM = [c for c in X.columns if c.startswith('mem_')]
# ------------------------------------------------------------------ HIST (leave-season-out; test seasons use 2017-24)
bdoy = bw.copy(); bdoy['d0'] = (bdoy.window_start - pd.to_datetime(bdoy.season.astype(str) + '-01-01')).dt.days; bdoy['d1'] = (bdoy.window_end - pd.to_datetime(bdoy.season.astype(str) + '-01-01')).dt.days
hist = {}
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days); dd = days.dayofyear.values - 1
    pool = [Z for Z in range(2017, 2025) if Z != Y]
    cnt = np.zeros((T, n), np.float32)
    for Z in pool:
        g = bdoy[bdoy.season == Z]; M = np.zeros((T, n), bool)
        for r in g.itertuples():
            lo, hi = r.d0 - 7, r.d1 + 7; M[(dd >= lo) & (dd <= hi), r.cell_id] = True
        cnt += M
    cnt /= len(pool)
    hist[Y] = {'hist_cell_win7': cnt, 'hist_n1_win7': (A1 @ cnt.T).T / 8.0}
X = X.merge(attach(hist), on=['season', 'date', 'cell_id'], how='left'); del hist
HIST = ['hist_cell_win7', 'hist_n1_win7']
# ------------------------------------------------------------------ CAL
holi = {2017: '03-13', 2018: '03-02', 2019: '03-21', 2020: '03-10', 2021: '03-29', 2022: '03-18', 2023: '03-08', 2024: '03-25', 2025: '03-14', 2026: '03-04'}
hd = X.season.map({Y: pd.Timestamp(f'{Y}-{m}') for Y, m in holi.items()})
X['cal_days_since_holi'] = (X.date - hd).dt.days.astype(np.float32)
CAL = ['cal_days_since_holi']
# ------------------------------------------------------------------ VSIG
v = pd.read_parquet(RP + 'viirs_snpp_2013_2024.parquet'); v['date'] = pd.to_datetime(v.date)
from scipy.spatial import cKDTree
_pt = pd.read_csv(RS + 'ratapani-ignition/cell_point.csv')
import pyproj
tr_ = pyproj.Transformer.from_crs(4326, 32643, always_xy=True)
vx, vy = tr_.transform(v.longitude.values, v.latitude.values)
_d, _i = cKDTree(xy).query(np.c_[vx, vy]); v = v[_d <= 400].assign(cell_id=_i[_d <= 400])
v['season'] = np.where(v.date.dt.month >= 8, v.date.dt.year + 1, v.date.dt.year); v['night'] = (v.daynight == 'N').astype(float); v['doy'] = v.date.dt.dayofyear
vs = {}
for Y in SEAS:
    o = v[v.season != Y]
    g = o.groupby('cell_id'); first = o.groupby(['season', 'cell_id']).doy.min().groupby('cell_id').median()
    d = pd.DataFrame({'vsig_night_share': g.night.mean(), 'vsig_first_doy': first, 'vsig_n_per_yr': g.size() / o.season.nunique()}).reindex(range(n))
    d['vsig_early'] = (d.vsig_first_doy < 60).astype(float).where(d.vsig_first_doy.notna())
    d['vsig_n_per_yr'] = d.vsig_n_per_yr.fillna(0)
    vs[Y] = d
vsd = pd.concat([vs[Y].reset_index(drop=True).assign(season=Y, cell_id=np.arange(n)) for Y in SEAS]); X = X.merge(vsd, on=['season', 'cell_id'], how='left')
VSIG = [c for c in X.columns if c.startswith('vsig_')]
print('groups', {k: len(v) for k, v in dict(PHEN=PHEN, MEM=MEM, HIST=HIST, CAL=CAL, VSIG=VSIG).items()}, flush=True)
# ------------------------------------------------------------------ analyses
# (1) share of top-5 picks on cells already burned (scar closed) this season by t-1: those rows are invalid under the rule, so count from X vs full grid
X['burned_known'] = 0.0
for Y in SEAS:
    g = bw[bw.season == Y]; m = X.season == Y
    k = X.loc[m, ['cell_id', 'date']].merge(g[['cell_id', 'window_end']], on='cell_id', how='left')
    X.loc[m, 'burned_known'] = (k.window_end.values <= (k.date - pd.Timedelta(days=1)).values).astype(float)
print('rows with cell already burned (closed scar) by t-1 inside the valid set:', float(X.burned_known.mean()), flush=True)
# (2) leaf fall -> fire lag: at each cell's first-burn window_end (and VIIRS fire day when known), days since d50
tl = pd.read_parquet(RP + 'fsi/true_lead_labels.parquet')
print('true_lead cols', tl.columns.tolist(), flush=True)
fb = bw[['season', 'cell_id', 'window_start', 'window_end']].copy(); fb['date'] = fb.window_start
lag = fb.merge(X[['season', 'cell_id', 'date', 'ph_days_since_d50', 'ph_frac_dropped']], on=['season', 'cell_id', 'date'], how='left')
res = {'analysis': {'burned_known_share_valid_rows': float(X.burned_known.mean()),
       'lag_days_since_d50_at_window_start': lag.ph_days_since_d50.describe().round(1).to_dict(),
       'frac_dropped_at_window_start': lag.ph_frac_dropped.describe().round(3).to_dict()}}
# hazard: positive rate by days_since_d50 bin (first-burn positives per valid cell-day)
bins = [-1, 0, 7, 14, 21, 35, 50, 70, 100, 400]
X['dsb'] = pd.cut(X.ph_days_since_d50.fillna(-0.5), bins)
hz = X.groupby('dsb', observed=True).pos.agg(['mean', 'size']); res['analysis']['hazard_by_days_since_d50'] = {str(k): [round(float(a), 5), int(b)] for k, (a, b) in hz.iterrows()}
hz2 = X.groupby(pd.cut(X.ph_frac_dropped, [-0.3, 0.2, 0.4, 0.6, 0.8, 1.0, 1.3]), observed=True).pos.agg(['mean', 'size']); res['analysis']['hazard_by_frac_dropped'] = {str(k): [round(float(a), 5), int(b)] for k, (a, b) in hz2.iterrows()}
print(json.dumps(res['analysis'], indent=1), flush=True)
json.dump(res, open(os.path.join(OUT, 'round3_results.json'), 'w'), indent=1)
# ------------------------------------------------------------------ models
def run2(name, feat):
    run(name, feat); run('rank_' + name, feat, rank=True)
    m = X[['season', 'date', 'beat']]
    X['ra_' + name] = X[name].groupby([m.season, m.date, m.beat]).rank(pct=True) + X['rank_' + name].groupby([m.season, m.date, m.beat]).rank(pct=True)
    res['ra_' + name] = {'loso': score_pred('ra_' + name, range(2017, 2025)), 'test': score_pred('ra_' + name, [2025, 2026])}
    print('ra_' + name, res['ra_' + name]['loso']['real94_recall@5'], res['ra_' + name]['test']['real94_recall@5'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'round3_results.json'), 'w'), indent=1)
G = {'base': BASE, 'phen': BASE + PHEN, 'mem': BASE + MEM, 'hist': BASE + HIST, 'cal': BASE + CAL, 'vsig': BASE + VSIG, 'all': BASE + PHEN + MEM + HIST + CAL + VSIG}
for c in CFG: run2(c, G[c])
X[['season', 'date', 'cell_id', 'pos', 'beat'] + [c for c in X.columns if c.startswith('ra_')]].to_parquet(os.path.join(OUT, 'round3_pred.parquet'))
print('ROUND3_DONE', flush=True)
