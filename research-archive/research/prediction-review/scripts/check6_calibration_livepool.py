"""Calibration of the honest lean classifier's % chances, and scoring on a live candidate pool.
Input: ../results/pred_allcells_honest.parquet (check3: every cell-day Feb 1-Jun 20, 2017-26, with scorer validity).
1) Reliability on scorer-valid cell-days: predicted % vs observed share, by bins; Brier skill vs the season-average
   day-of-year rate (climatology from training seasons). Raw and after leave-season-out isotonic.
2) Live pool: the scorer only lets valid cells be picked. A live system cannot know which cells burned in the last
   25 days (scar not yet confirmed) or will stay cloud-hidden. Here every cell not confirmed-burned (window_end + 25 d)
   can be picked; hits still count only on valid positives. -> ../results/check6.json"""
import json, numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression
RS = '/mnt/project-files/research/'; RA = '/mnt/project-files/ratapani/'; OUT = RS + 'prediction-review/results/'
p = pd.read_parquet(OUT + 'pred_allcells_honest.parquet'); p['date'] = pd.to_datetime(p['date'])
beat = pd.read_csv(RA + 'beats/cell_beat.csv').set_index('cell_id').beat_uid; p['b'] = p.cell_id.map(beat).values
res = {}
v = p[p.valid].copy(); v['doy'] = v.date.dt.dayofyear
# climatology and isotonic, leave-season-out within 2017-24; 2017-24 fit for 2025-26
v['clim'] = np.nan; v['iso'] = np.nan
for Y in range(2017, 2027):
    tr = v[(v.season != Y) & (v.season < 2025)]
    c = tr.groupby('doy').pos.mean().rolling(7, center=True, min_periods=1).mean()
    k = v.season == Y; v.loc[k, 'clim'] = v.loc[k, 'doy'].map(c).fillna(tr.pos.mean()).values
    ir = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(tr.honest, tr.pos)
    v.loc[k, 'iso'] = ir.predict(v.loc[k, 'honest'])
def brier(a, y): return float(np.mean((a - y) ** 2))
for nm, sl in (('loso', v.season < 2025), ('test2526', v.season >= 2025)):
    d = v[sl]; y = d.pos.values.astype(float); bc = brier(d.clim.values, y)
    out = {'base_rate': round(float(y.mean()), 4), 'mean_pred_raw': round(float(d.honest.mean()), 4), 'mean_pred_iso': round(float(d.iso.mean()), 4),
           'brier_skill_raw_vs_doy_climatology': round(1 - brier(d.honest.values, y) / bc, 3),
           'brier_skill_iso_vs_doy_climatology': round(1 - brier(d.iso.values, y) / bc, 3)}
    bins = [0, .01, .02, .05, .1, .2, .3, 1]; d = d.assign(bin=pd.cut(d.iso, bins, include_lowest=True))
    out['reliability_iso'] = {str(k): {'pred': round(float(g.iso.mean()), 3), 'obs': round(float(g.pos.mean()), 3), 'share_of_celldays': round(len(g) / len(d), 3)} for k, g in d.groupby('bin', observed=True)}
    out['per_season_mean_pred_vs_obs'] = {int(s): [round(float(g.iso.mean()), 4), round(float(g.pos.mean()), 4)] for s, g in d.groupby('season')}
    res['calibration_' + nm] = out
# live pool
bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
bw = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
p = p.merge(bw[['season', 'cell_id', 'window_end']], on=['season', 'cell_id'], how='left')
known = p.window_end.notna() & (p.date > p.window_end + pd.Timedelta(days=25))
p['rnd'] = np.random.default_rng(0).random(len(p))
def rec(d, col):
    r = d[col].groupby([d.season, d.date, d.b]).rank('first', ascending=False); return round(100 * float((d.pos & d.valid & (r <= 5)).sum() / (d.pos & d.valid).sum()), 1)
for nm, sl in (('loso', p.season < 2025), ('test2526', p.season >= 2025)):
    res['livepool_' + nm] = {'scorer_pool_model': rec(p[sl & p.valid], 'honest'), 'scorer_pool_random': rec(p[sl & p.valid], 'rnd'),
                             'live_pool_model': rec(p[sl & ~known], 'honest'), 'live_pool_random': rec(p[sl & ~known], 'rnd'),
                             'share_of_live_picks_cells_already_burned_unconfirmed': None}
    d = p[sl & ~known]; r = d.honest.groupby([d.season, d.date, d.b]).rank('first', ascending=False) <= 5
    already = d.window_end.notna() & (d.date > d.window_end)
    res['livepool_' + nm]['share_of_live_picks_cells_already_burned_unconfirmed'] = round(float(already[r].mean()), 3)
json.dump(res, open(OUT + 'check6.json', 'w'), indent=1); print(json.dumps(res, indent=1)); print('CHECK6_DONE')
