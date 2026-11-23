"""Simple rules on the PC's exact all-MP scoring rule (van-suraksha-alert PR #1, mp/scripts/mp_all_eval.py + mp_features.py).
PC rule, reproduced: division grids = 500 m MP cells with >= 25% inside the division (divisions dissolved from
ratapani/beats/mp_beats.geojson); fires = VIIRS S-NPP + NOAA-20 + NOAA-21, type 0, all confidences, local IST date;
issue days Jan-May of 2022-24; y = fire in the cell on t+1 or t+2; flagged = top 10% of ALL the division's test cell-days
(one threshold over the three seasons, so busy days can get many flags); a positive counts if a flagged cell is in its
3x3 block that day; "new" = no fire within 5 km over days t-6..t. Rules (no model):
  random     random score
  history    fire cell-days in the 3x3 block, Jan-May 2019-21 (static: same cells every day)
  cal_hist   history x the division's day-of-year fire rate in 2019-21 (7-day smoothed): where AND when, nothing live
  recent     fire cell-days in the 7x7 block over t-6..t (persistence), ties broken by cal_hist
Also: share of test cell-days flagged or next to a flag ("ground share"), per division.
Out: mp_check/simple_rules_by_division.csv, simple_rules_summary.json"""
import json, numpy as np, pandas as pd, shapely
from shapely.geometry import shape
from shapely.ops import transform as stf
from pyproj import Transformer
TF = Transformer.from_crs(4326, 32643, always_xy=True)
from scipy.ndimage import maximum_filter, uniform_filter, distance_transform_edt
from multiprocessing import Pool
P = '/mnt/project-files/'; OUT = P + 'ratapani/scoring/mp_check/'
X0, Y1, S, NCOL = 399000.0, 2996000.0, 500.0, 1829
TRAIN, TEST = (2019, 2020, 2021), (2022, 2023, 2024)
import os as _os
if _os.environ.get('FWD') == '2026':   # 2026 season only (as the PC's daily-rule table)
    TRAIN, TEST = (2019, 2020, 2021, 2022, 2023, 2024, 2025), (2026,)
elif _os.environ.get('FWD') == '1':   # forward test: history from 2019-24, scored on 2025-26
    TRAIN, TEST = (2019, 2020, 2021, 2022, 2023, 2024), (2025, 2026)
import os; SEASON = os.environ.get('MPV') == 'season'; SUF = '_season' if SEASON else ''

def load_fires():
    fs = []
    for y in TRAIN + TEST:
        for sat in ('snpp', 'jpss1', 'noaa21'):
            try: d = pd.read_csv(P + f'fire-alert-scars/alerts_mp/viirs-{sat}_{y}.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'type', 'daynight', 'frp'])
            except FileNotFoundError: continue
            fs.append(d)
    for y in (2018,):   # Dec 2018 not needed; Jan windows only look back 7 days within Jan-May seasons
        pass
    v = pd.concat(fs, ignore_index=True); v = v[v.type == 0]
    x, y_ = TF.transform(v.longitude.values, v.latitude.values)
    v['col'] = np.floor((x - X0) / S).astype(int); v['row'] = np.floor((Y1 - y_) / S).astype(int)
    utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, 'h') + pd.to_timedelta(v.acq_time % 100, 'm')
    v['ld'] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
    v = v[['row', 'col', 'ld', 'daynight', 'frp', 'longitude', 'latitude']].copy()
    v['ctrl'] = False
    if SEASON:   # likely control burns, 15-28 Feb: day-only cluster, <=2 points, max FRP <=5 MW, nothing else within 1 km on d-2..d+3
        from scipy.spatial import cKDTree
        xy = np.c_[*TF.transform(v.longitude.values, v.latitude.values)]; dn = (v.ld - pd.Timestamp('2000-01-01')).dt.days.values
        md = v.ld.dt.month.values * 100 + v.ld.dt.day.values; cand = np.where((md >= 215) & (md <= 228))[0]
        tree = cKDTree(np.c_[xy, dn * 1e6]); ctrl = np.zeros(len(v), bool)
        for i in cand:
            same = [j for j in tree.query_ball_point(np.r_[xy[i], dn[i] * 1e6], r=1000) if dn[j] == dn[i]]
            if len(same) > 2 or (v.daynight.values[same] != 'D').any() or v.frp.values[same].max() > 5: continue
            near = 0
            for dd in range(-2, 4):
                if dd == 0: continue
                near += len(tree.query_ball_point(np.r_[xy[i], (dn[i] + dd) * 1e6], r=1000))
            if near == 0: ctrl[i] = True
        v['ctrl'] = ctrl; print('control burns dropped', int(ctrl.sum()), 'of', len(cand), 'Feb 15-28 points', flush=True)
    return v[['row', 'col', 'ld', 'ctrl']].drop_duplicates(['row', 'col', 'ld', 'ctrl'])

def grids():
    F = json.load(open(P + 'ratapani/beats/mp_beats.geojson'))['features']
    by = {}
    for f in F: by.setdefault(f['properties']['Division'], []).append(stf(TF.transform, shape(f['geometry']).buffer(0)))
    out = {}
    for name, ps in by.items():
        poly = shapely.union_all(ps).buffer(0); x0, y0, x1, y1 = poly.bounds
        c0, c1 = int(np.floor((x0 - X0) / S)), int(np.ceil((x1 - X0) / S)); r0, r1 = int(np.floor((Y1 - y1) / S)), int(np.ceil((Y1 - y0) / S))
        cols, rows = np.meshgrid(np.arange(c0, c1), np.arange(r0, r1)); cols, rows = cols.ravel(), rows.ravel()
        g = shapely.box(X0 + cols * S, Y1 - (rows + 1) * S, X0 + (cols + 1) * S, Y1 - rows * S); shapely.prepare(poly)
        k = shapely.intersects(poly, g); frac = np.zeros(len(g)); frac[k] = shapely.area(shapely.intersection(g[k], poly)) / (S * S)
        keep = frac >= 0.25; out[name.replace(' ', '_')] = (rows[keep], cols[keep])
    return out

def score_div(args):
    name, rows, cols, v = args
    r0, c0 = rows.min(), cols.min(); NJ, NI = rows.max() - r0 + 1, cols.max() - c0 + 1
    gi, gj = rows - r0, cols - c0
    v = v[(v.row >= r0) & (v.row < r0 + NJ) & (v.col >= c0) & (v.col < c0 + NI)]
    rng = np.random.default_rng(0); res = {'division': name, 'cells': len(rows)}
    def raster(y):
        days = pd.date_range(f'{y}-01-01', f'{y}-06-02'); di = pd.Series(np.arange(len(days)), index=days)
        q = v[v.ld.isin(days)]; FR = np.zeros((len(days), NJ, NI), bool); FR[di[q.ld].values, q.row.values - r0, q.col.values - c0] = True
        q = q[~q.ctrl]; FT = np.zeros_like(FR); FT[di[q.ld].values, q.row.values - r0, q.col.values - c0] = True
        return days, FR, FT
    # history and day-of-year rate from 2019-21
    hd = np.zeros((NJ, NI)); rate = np.zeros(400); nd = np.zeros(400)
    for y in TRAIN:
        days, FR, _ = raster(y); m = days.month <= 5
        hd += FR[m].sum(0); fc = FR[:, rows - r0, cols - c0].sum(1)
        np.add.at(rate, days.dayofyear[m], fc[m]); np.add.at(nd, days.dayofyear[m], 1)
    hist = uniform_filter(hd, 3, mode='constant')[gi, gj] * 9
    rate = pd.Series(rate / np.maximum(nd, 1)).rolling(7, center=True, min_periods=1).mean().values
    res['train_fire_cell_days'] = int(hd[gi, gj].sum())
    S_ = {k: [] for k in ('random', 'history', 'cal_hist', 'recent')}; Y, NEW, DAY = [], [], []
    for y in TEST:
        days, FR, FT = raster(y); FRf = FR.astype(np.float32)
        nb7 = uniform_filter(FRf, size=(1, 7, 7), mode='constant') * 49
        c7 = np.cumsum(nb7, 0); w7 = c7.copy(); w7[7:] -= c7[:-7]
        cum = np.cumsum(FR, 0)
        for t in np.where(days.month <= 5)[0]:
            yy = (FT[t + 1] | FT[t + 2])[gi, gj]
            if SEASON:   # targets only on 15 Feb - 31 May
                ok_ = [(days[t + k].month * 100 + days[t + k].day) >= 215 and days[t + k].month <= 5 for k in (1, 2)]
                yy = (FT[t + 1] & ok_[0] | FT[t + 2] & ok_[1])[gi, gj]
                if not any(ok_): continue
            win = (cum[t] - (cum[t - 7] if t >= 7 else 0)) > 0
            fd = distance_transform_edt(~win)[gi, gj] * 0.5 if win.any() else np.full(len(gi), 99.)
            ch = hist * rate[days[t].dayofyear] + 1e-6 * hist
            S_['random'].append(rng.random(len(gi))); S_['history'].append(hist + 1e-6 * rng.random(len(gi)))
            S_['cal_hist'].append(ch + 1e-9 * rng.random(len(gi)))
            S_['recent'].append(w7[t][gi, gj] * 1e3 + ch / (ch.max() + 1e-9) + 1e-9 * rng.random(len(gi)))
            Y.append(yy); NEW.append(fd > 5); DAY.append(t + 1000 * y)
    Y = np.concatenate(Y); NEW = np.concatenate(NEW)
    T = len(DAY); n = len(gi)
    res['n_pos'] = int(Y.sum()); res['n_new'] = int((Y & NEW).sum())
    for k, lst in S_.items():
        s = np.concatenate(lst); flag = s >= np.quantile(s, 0.90)
        F = flag.reshape(T, n); cov = np.zeros_like(F)
        for i in range(T):
            r = np.zeros((NJ, NI), bool); r[gi, gj] = F[i]; cov[i] = maximum_filter(r, 3)[gi, gj]
        cov = cov.reshape(-1)
        res[f'{k}_recall'] = float(cov[Y].mean()) if Y.any() else np.nan
        res[f'{k}_recall_new'] = float(cov[Y & NEW].mean()) if (Y & NEW).any() else np.nan
        res[f'{k}_ground'] = float(cov.mean())
    print(name, res['n_pos'], {k: round(res[f'{k}_recall'], 3) for k in S_}, flush=True)
    return res

if __name__ == '__main__':
    v = load_fires(); G = grids(); print('fires', len(v), 'divisions', len(G), flush=True)
    with Pool(4) as p: R = p.map(score_div, [(k, r, c, v) for k, (r, c) in G.items()], chunksize=1)
    R = pd.DataFrame(R); R.to_csv(OUT + f'simple_rules_by_division{SUF}.csv', index=False)
    ok = R[R.n_pos > 0]; sm = {'divisions': len(ok), 'pos_cell_days': int(ok.n_pos.sum()), 'cells': int(ok.cells.sum())}
    for k in ('random', 'history', 'cal_hist', 'recent'):
        sm[k] = {'recall': round(100 * np.average(ok[f'{k}_recall'], weights=ok.n_pos), 1),
                 'recall_new': round(100 * np.average(ok[f'{k}_recall_new'].fillna(0), weights=ok.n_new), 1),
                 'ground_share': round(100 * np.average(ok[f'{k}_ground'], weights=ok.cells), 1),
                 'median_division': round(100 * ok[f'{k}_recall'].median(), 1)}
    json.dump(sm, open(OUT + f'simple_rules_summary{SUF}.json', 'w'), indent=1); print(json.dumps(sm, indent=1)); print('MPCHECK_DONE')
