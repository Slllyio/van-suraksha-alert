"""Scouting round 4 on the lean model (real beats, SCORING.md):
 FINE  fine-scale terrain and litter-moisture proxies: McCune-Keon heat load, TPI (1 km, 2 km rings), floor radiation
       (clear-sky slope insolation x canopy transmittance), litter-surface T and RH proxy, FMIgen dead fuel moisture,
       FM<20% flag, days since FM<20% this season, days since >=5 mm rain, within-beat FM rank, night cold-pool proxy
 plus a looks-per-cell label check: do clear-look counts drive the scar labels?
Usage: python3 round4.py OUTDIR
"""
import sys, os, json, numpy as np, pandas as pd, lightgbm as lgb
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lean_plus.py')).read()
src = src[:src.index('for cfg in CONFIGS:')]
sys.argv = [sys.argv[0], sys.argv[1], 'none']
exec(compile(src, 'lean_plus.py', 'exec'))
OUT = sys.argv[1]
cs = pd.read_csv(RS + 'ratapani-ignition/cells_static.csv').set_index('cell_id').reindex(range(n))
lat = np.radians(22.95); slope = np.radians(cs.slope.values); asp = np.arctan2(cs.eastness.values, cs.northness.values)
asp_deg = (np.degrees(asp) + 360) % 360; fold = np.radians(np.abs(180 - np.abs(asp_deg - 225)))
hli = np.exp(-1.467 + 1.582 * np.cos(lat) * np.cos(slope) - 1.5 * np.cos(fold) * np.sin(slope) * np.sin(lat) - 0.262 * np.sin(lat) * np.sin(slope) + 0.607 * np.sin(fold) * np.sin(slope))
elev = cs.elev.values; deg1 = np.asarray(A1.sum(1)).ravel(); deg2 = np.asarray(A2.sum(1)).ravel()
tpi1 = elev - np.where(deg1 > 0, A1 @ elev / np.maximum(deg1, 1), elev); tpi2 = elev - np.where(deg2 > 0, A2 @ elev / np.maximum(deg2, 1), elev)
stat = pd.DataFrame({'fine_hli': hli, 'fine_tpi1': tpi1, 'fine_tpi2': tpi2}, index=range(n))
X = X.join(stat, on='cell_id')
ins = np.load(RS + 'ratapani-ignition/insolation.npy')  # cells x 172 (Jan 1..Jun 20), relative to flat
tau = np.exp(-1.2 * cs.tree.values)  # canopy transmittance proxy from tree cover
fr = {}
rain = w.PRECTOTCORR; dsr = pd.Series(np.nan, index=w.index); c = 0; vals = []
for r in rain.values: c = 0 if r >= 5 else c + 1; vals.append(c)
w['fine_days_since_rain5'] = pd.Series(vals, index=w.index).shift(1)
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days); doy = days.dayofyear.values - 1
    R = ins[:, doy].T * tau[None, :]                      # T x n floor radiation index (0..~1.3)
    tmax = w.T2M_MAX.reindex(days).values[:, None]; rh = w.RH2M.reindex(days).values[:, None]; t2 = w.T2M.reindex(days).values[:, None]
    Ts = tmax + 12.0 * (R - R.mean(1, keepdims=True))     # +-12 K across the cell spread of floor radiation
    es = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))
    ea = rh / 100 * es(t2); RHs = np.clip(100 * ea / es(Ts), 1, 100)
    FM = 11.063 - 0.146 * Ts + 0.106 * RHs
    f = {'fine_rfloor': R, 'fine_ts': Ts, 'fine_rhs': RHs, 'fine_fm': FM, 'fine_fm_lt20': (FM < 20).astype(np.float32)}
    below = (FM < 20); first = np.where(below.any(0), below.argmax(0), 10 ** 6); d = np.arange(T)[:, None] - first[None, :]
    f['fine_days_fm_lt20'] = np.where(d >= 0, d, np.nan).astype(np.float32)
    f['fine_fm_beatrank'] = pd.DataFrame(FM).T.groupby(beat_code).rank(pct=True).T.to_numpy(np.float32)
    f['fine_fm_minus_beat'] = FM - pd.DataFrame(FM).T.groupby(beat_code).transform('median').T.to_numpy(np.float32)
    calm = ((w.WS10M.reindex(days).values < 2.0) & (w.PRECTOTCORR.reindex(days).values == 0)).astype(np.float32)[:, None]
    f['fine_coldpool'] = calm * (tpi1 < -5)[None, :].astype(np.float32)
    fr[Y] = f
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days); tt, cc_ = np.meshgrid(np.arange(T), np.arange(n), indexing='ij')
    df = pd.DataFrame({k: np.asarray(v, np.float32).reshape(-1) for k, v in fr[Y].items()}); df['season'] = Y; df['date'] = days[tt.reshape(-1)]; df['cell_id'] = cc_.reshape(-1); frames.append(df)
X = X.merge(pd.concat(frames, ignore_index=True), on=['season', 'date', 'cell_id'], how='left'); del frames, fr
X = X.join(w[['fine_days_since_rain5']], on='date')
FINE = [c for c in X.columns if c.startswith('fine_')]
print('FINE', FINE, flush=True)
# ---- looks-per-cell label check
lk = sc.groupby(['cell_id']).size(); sc_s = sc.copy(); sc_s['season'] = np.where(sc_s.date.dt.month >= 8, sc_s.date.dt.year + 1, sc_s.date.dt.year)
looks_cs = sc_s[(sc_s.date.dt.month >= 2) & (sc_s.date.dt.month <= 6)].groupby(['season', 'cell_id']).size().rename('looks')
bcs = bw[['season', 'cell_id']].assign(burned=1)
chk = looks_cs.reset_index().merge(bcs, on=['season', 'cell_id'], how='left').fillna({'burned': 0})
chk['lq'] = pd.qcut(chk.looks, 5, duplicates='drop')
tab = chk.groupby('lq', observed=True).burned.agg(['mean', 'size'])
sp = chk.groupby('season').apply(lambda g: g[['looks', 'burned']].corr('spearman').iloc[0, 1])
res['looks_check'] = {'burned_rate_by_looks_quintile': {str(k): [round(float(a), 4), int(b)] for k, (a, b) in tab.iterrows()}, 'spearman_by_season': sp.round(3).to_dict()}
print(json.dumps(res['looks_check'], indent=1), flush=True)
def run2(name, feat):
    run(name, feat); run('rank_' + name, feat, rank=True)
    m = X[['season', 'date', 'beat']]
    X['ra_' + name] = X[name].groupby([m.season, m.date, m.beat]).rank(pct=True) + X['rank_' + name].groupby([m.season, m.date, m.beat]).rank(pct=True)
    res['ra_' + name] = {'loso': score_pred('ra_' + name, range(2017, 2025)), 'test': score_pred('ra_' + name, [2025, 2026])}
    print('ra_' + name, res['ra_' + name]['loso']['real94_recall@5'], res['ra_' + name]['test']['real94_recall@5'], flush=True)
    # by period: Feb, Mar, Apr-Jun
    for lo, hi, tag in ((2, 2, 'feb'), (3, 3, 'mar'), (4, 6, 'apr_jun')):
        mm = X.date.dt.month.between(lo, hi)
        for col in (name, 'ra_' + name):
            sub = X[mm & X.season.isin(range(2017, 2025))]; r = sub[col].fillna(-1e9).groupby([sub.season, sub.date, sub.beat]).rank('first', ascending=False)
            res[col].setdefault('loso_by_period', {})[tag] = round(float(sub.pos[r <= 5].sum() / sub.pos.sum()), 4) if col in res else None
    json.dump(res, open(os.path.join(OUT, 'round4_results.json'), 'w'), indent=1)
run2('base', BASE); run2('fine', BASE + FINE)
json.dump(res, open(os.path.join(OUT, 'round4_results.json'), 'w'), indent=1)
print('ROUND4_DONE', flush=True)
