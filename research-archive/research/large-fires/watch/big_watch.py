"""Big-fire watch list for one issue day: the squares most likely to see the first look of a 200 ha+ fire (forest ha,
scar truth) in the next 2 days. Short list on top of the daily list: top 1% and top 2% of each division's squares.
Tested on 2025 (research/large-fires/README.md, "Fair check"): top 1% caught 53% of 200 ha+ fires (PC daily models 40%),
59% of 500 ha+ (46%); top 2% 68% / 73%. About 1 in 100 flagged square-days gets one, ~20x the average square.

Inputs: the VIIRS archive (fire-alert-scars/alerts_mp, via ratapani/fsi/scouting/code/system_rebuild common.load_det)
plus, live, the season's new FIRMS VIIRS rows (latitude, longitude, acq_date, acq_time, type, confidence, frp,
daynight, scan, track, satellite, instrument, version and any FIRMS columns) passed as extra_firms; HLS dryness
ratapani/mp_grid/dryness/mp_dry_<S>.npz; static_gis_v1; this folder's model, calibration and scar_hist_<S>.npz.
Usage: python big_watch.py 2025-04-05 [--firms new.csv ...] [--out dir]
Writes big_watch_<date>.parquet: cell, division, score, pct, rank_in_division, top1, top2; and a per-division count csv."""
import os, sys, json, argparse
import numpy as np, pandas as pd, lightgbm as lgb
HERE = os.path.dirname(os.path.abspath(__file__)) + '/'
sys.path.insert(0, HERE + '../scripts')
import lf_sr
C, Fe = lf_sr.C, lf_sr.Fe


def detections(extra_firms=None):
    V = C.load_det()
    if extra_firms is None or len(extra_firms) == 0: return V
    v = extra_firms.copy()
    sat = {'N': 'snpp', 'N20': 'jpss1', 'N21': 'noaa21', '1': 'jpss1'}
    v['sat'] = v.satellite.astype(str).map(sat).fillna('snpp')
    x, y = C.TF.transform(v.longitude.values, v.latitude.values)
    v['x'] = x.astype(np.float32); v['y'] = y.astype(np.float32)
    v['col'] = np.floor((x - C.X0) / C.S).astype(np.int32); v['row'] = np.floor((C.Y1 - y) / C.S).astype(np.int32)
    t = v.acq_time.astype(int)
    v['utc'] = pd.to_datetime(v.acq_date) + pd.to_timedelta(t // 100, 'h') + pd.to_timedelta(t % 100, 'm')
    v['ld'] = (v.utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize(); v['season'] = v.ld.dt.year.astype(np.int16)
    v = v[[c for c in V.columns if c in v.columns and c != 'ctrl']]
    A = pd.concat([V.drop(columns='ctrl'), v], ignore_index=True).drop_duplicates(['sat', 'utc', 'x', 'y'])
    A['ctrl'] = C.ctrl_flag(A)
    return A


def score_day(day, extra_firms=None):
    day = pd.Timestamp(day); y = day.year
    sq = np.load(HERE + 'squares.npz'); U = sq['cells']; home = sq['home']; names = list(sq['divnames'])
    assert (U == Fe.base()['U']).all()
    feats = json.load(open(HERE + 'features.json')); m = lgb.Booster(model_file=HERE + 'big_model.txt'); ms = lgb.Booster(model_file=HERE + 'size_model.txt')
    cal = json.load(open(HERE + 'calibration.json'))
    s = pd.read_parquet(C.P + 'ratapani/mp_grid/static_gis_v1.parquet')
    st = {k: s[k].values.astype(np.float32) for k in s.columns if k not in ('cell', 'row', 'col')}
    sh = dict(np.load(HERE + f'scar_hist_{y}.npz'))
    for it in Fe.season_iter(y, {}, detections(extra_firms), static=st):
        if it['t'] != day: continue
        col = {n: i for i, n in enumerate(it['names'])}
        X = np.hstack([it['X'], np.stack([sh[k] for k in sh], 1)]); col.update({k: len(it['names']) + j for j, k in enumerate(sh)})
        Xf = X[:, [col[n] for n in feats]]; sc = m.predict(Xf, num_threads=4); sz = ms.predict(Xf, num_threads=4)
        break
    else:
        raise ValueError('issue days run 13 Feb - 30 May')
    D = pd.DataFrame(dict(cell=U, division=[names[h] if h >= 0 else '' for h in home], score=sc.astype(np.float32),
                          pct=np.interp(sc, cal['x'], cal['y']).astype(np.float32), size_score=sz.astype(np.float32)))
    D['rank_in_division'] = D.groupby('division').score.rank(ascending=False, method='first').astype(int)
    n = D.groupby('division').cell.transform('size')
    D['top1'] = D.rank_in_division <= np.ceil(0.01 * n); D['top2'] = D.rank_in_division <= np.ceil(0.02 * n)
    # season cuts (21 Oct, ../README.md 'Late season and the live rule'): fixed per-division score cuts from the 2025 season,
    # so busy days get more flags and quiet days fewer, like the tested season rule. 2026: 64% vs 46% of 200 ha+ (daily ranks).
    cuts = json.load(open(HERE + 'cuts_2025.json'))
    D['top1_cut'] = D.score >= D.division.map(cuts['top1']).fillna(np.inf); D['top2_cut'] = D.score >= D.division.map(cuts['top2']).fillna(np.inf)
    return D


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('date'); ap.add_argument('--firms', nargs='*', default=[]); ap.add_argument('--out', default='.')
    a = ap.parse_args()
    ex = pd.concat([pd.read_csv(f) for f in a.firms], ignore_index=True) if a.firms else None
    D = score_day(a.date, ex); os.makedirs(a.out, exist_ok=True)
    D.to_parquet(f'{a.out}/big_watch_{a.date}.parquet', index=False)
    D.groupby('division').agg(squares=('cell', 'size'), top1=('top1', 'sum'), top2=('top2', 'sum'), max_pct=('pct', 'max')).to_csv(f'{a.out}/big_watch_counts_{a.date}.csv')
    print(a.date, 'top1', int(D.top1.sum()), 'top2', int(D.top2.sum()))
