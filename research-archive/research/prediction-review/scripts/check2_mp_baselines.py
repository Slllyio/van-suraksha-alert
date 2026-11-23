"""How much of the MP division models' "~85% of fire points in or next to the top 10% of squares" would trivial rules get?
The division models live on Akkshay's PC, so this does not rerun them. It rebuilds the scoring rule as described
(report/PROJECT_REPORT.md section 10.2; train 2019-21, test 2022-24) on the all-MP VIIRS archive and scores three
rankings that need no model at all:
  history   = fire square-days in the square and its 8 neighbours, Feb 15-Jun 15 2019-21 (all satellites)
  recent    = any VIIRS point in the square or its neighbours in the last 7 days, ties broken by history
  random
Target: squares with a VIIRS point (any satellite) on day t+1, issue days Feb 15-Jun 15 2022-24. Squares = the 500 m
MP beat grid (ratapani/mp_grid/mp_cells.parquet). Flagged = top 10% of a division's squares on that day. A target
square counts if it or any of its 8 neighbours is flagged. "New fire" = no VIIRS within 5 km in the past 7 days.
Assumptions that may differ from the PC rule: horizon (next day), the square grid, all-satellite target.
Usage: python3 check2_mp_baselines.py -> ../results/check2_mp.json"""
import json, numpy as np, pandas as pd
from scipy import ndimage
from pyproj import Transformer
P = '/mnt/project-files/'; OUT = P + 'research/prediction-review/results/'
g = json.load(open(P + 'ratapani/mp_grid/mp_grid.json')); X0, Y1, W, H, S = g['X0'], g['Y1'], g['W'], g['H'], g['S']
cells = pd.read_parquet(P + 'ratapani/mp_grid/mp_cells.parquet'); cells['div'] = cells.beat_uid.str[:3]
inbeat = np.zeros((H, W), bool); inbeat[cells.row, cells.col] = True
div = np.full((H, W), '', object); div[cells.row, cells.col] = cells['div'].values
tf = Transformer.from_crs(4326, 32643, always_xy=True)
def load(years):
    fs = []
    for y in years:
        for sat in ('snpp', 'jpss1', 'noaa21'):
            try: d = pd.read_csv(P + f'fire-alert-scars/alerts_mp/viirs-{sat}_{y}.csv', usecols=['latitude', 'longitude', 'acq_date', 'confidence'])
            except FileNotFoundError: continue
            d['sat'] = sat; fs.append(d)
    v = pd.concat(fs); v = v[v.confidence != 'l']
    x, yy = tf.transform(v.longitude.values, v.latitude.values)
    v['col'] = ((x - X0) // S).astype(int); v['row'] = ((Y1 - yy) // S).astype(int)
    v = v[(v.col >= 0) & (v.col < W) & (v.row >= 0) & (v.row < H)]
    v = v[inbeat[v.row, v.col]]; v['date'] = pd.to_datetime(v.acq_date); return v
k3 = np.ones((3, 3)); k21 = np.ones((21, 21))   # 21 x 500 m ~ 5 km box for the "new fire" rule
hist = load([2019, 2020, 2021]); hist = hist[(hist.date.dt.month * 100 + hist.date.dt.day).between(215, 615)]
hc = np.zeros((H, W)); np.add.at(hc, (hist.row.values, hist.col.values), 1)  # point count (proxy for square-days)
hsq = hist.drop_duplicates(['date', 'row', 'col']); hd = np.zeros((H, W)); np.add.at(hd, (hsq.row.values, hsq.col.values), 1)
hist_score = ndimage.convolve(hd, k3, mode='constant')
test = load([2022, 2023, 2024])
rng = np.random.default_rng(0)
divs = sorted(set(cells['div']))
R, C = cells.row.values, cells.col.values
didx = {d: np.where(cells['div'].values == d)[0] for d in divs}
acc = {k: {} for k in ('history', 'recent', 'random')}; acc_new = {k: {} for k in acc}; tot = {}; tot_new = {}; area = {k: [] for k in acc}
for y in (2022, 2023, 2024):
    v = test[test.date.dt.year == y]
    days = pd.date_range(f'{y}-02-15', f'{y}-06-15')
    grids = {}
    for d in pd.date_range(f'{y}-02-01', f'{y}-06-16'):
        q = v[v.date == d]; G = np.zeros((H, W), bool); G[q.row.values, q.col.values] = True; grids[d] = G
    for t in days:
        tgt = grids[t + pd.Timedelta(days=1)]
        if not tgt.any(): continue
        rec7 = np.zeros((H, W), bool)
        for k in range(0, 7): rec7 |= grids[t - pd.Timedelta(days=k)]
        near1 = ndimage.maximum_filter(rec7.astype(np.uint8), size=3) > 0; near5 = ndimage.maximum_filter(rec7.astype(np.uint8), size=21) > 0
        scores = {'history': hist_score + 1e-6 * rng.random((H, W)), 'recent': near1 * 1e6 + hist_score + 1e-6 * rng.random((H, W)), 'random': rng.random((H, W))}
        for nm, sc in scores.items():
            sf = sc[R, C]; fl = np.zeros(len(R), bool)
            for d_, ix in didx.items():
                s = sf[ix]; kk = max(1, int(round(0.1 * len(ix))))
                thr = np.partition(s, -kk)[-kk]; fl[ix] = s >= thr
            flag = np.zeros((H, W), bool); flag[R[fl], C[fl]] = True
            cov = (ndimage.maximum_filter(flag.astype(np.uint8), size=3) > 0) & inbeat
            hit = (tgt & cov)[R, C]; tg = tgt[R, C]; nw = ~near5[R, C]
            for d_, ix in didx.items():
                nt = int(tg[ix].sum())
                if nt == 0: continue
                acc[nm][d_] = acc[nm].get(d_, 0) + int(hit[ix].sum()); acc_new[nm][d_] = acc_new[nm].get(d_, 0) + int((hit[ix] & nw[ix]).sum())
                if nm == 'history':
                    tot[d_] = tot.get(d_, 0) + nt; tot_new[d_] = tot_new.get(d_, 0) + int((tg[ix] & nw[ix]).sum())
            if t.day == 1: area[nm].append(float(cov.sum() / inbeat.sum()))
    print(y, 'done', flush=True)
res = {'note': __doc__.split('Usage')[0], 'target_square_days': int(sum(tot.values())), 'new_fire_square_days': int(sum(tot_new.values()))}
for nm in acc:
    pooled = sum(acc[nm].values()) / sum(tot.values()); pooled_new = sum(acc_new[nm].values()) / max(1, sum(tot_new.values()))
    per = [acc[nm][d] / tot[d] for d in tot if tot[d] >= 50]; pern = [acc_new[nm][d] / tot_new[d] for d in tot_new if tot_new[d] >= 30]
    res[nm] = {'pooled_all': round(100 * pooled, 1), 'pooled_new_fires': round(100 * pooled_new, 1),
               'division_mean_all': round(100 * float(np.mean(per)), 1), 'division_min_all': round(100 * float(np.min(per)), 1),
               'division_mean_new': round(100 * float(np.mean(pern)), 1), 'ground_share_flagged_or_adjacent': round(100 * float(np.mean(area[nm])), 1)}
res['n_divisions_scored'] = len([d for d in tot if tot[d] >= 50])
json.dump(res, open(OUT + 'check2_mp.json', 'w'), indent=1); print(json.dumps(res, indent=1)); print('CHECK2_DONE')
