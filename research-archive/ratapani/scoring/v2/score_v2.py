"""Score any all-cell-day prediction on the v2 key (see dated_once.py for the rule): % of VIIRS-dated first burns
(fire day Feb 17 - Jun 15) whose square was listed 1-2 days before, 5 per beat (94 real beats), live pool.
Usage: python3 score_v2.py <pred.parquet> <column> [<pred.parquet> <column> ...]  -> prints JSON (rules: same list daily, skip1, skip2)"""
import sys, json, numpy as np, pandas as pd
P = '/mnt/project-files/'; n = 3614; SEAS = list(range(2017, 2027))
fb = pd.read_parquet(P + 'ratapani/scoring/v2/dated_burns_2017_2026.parquet')
burns = fb[fb.fire_day.notna()]; burns = burns[(burns.fire_day.dt.strftime('%m-%d') >= '02-17') & (burns.fire_day.dt.strftime('%m-%d') <= '06-15')]
beat = pd.read_csv(P + 'ratapani/beats/cell_beat.csv').set_index('cell_id').beat_uid.reindex(range(n))
inb = beat.notna().values; bid = pd.factorize(beat.fillna(-1))[0]
def pick(score, ok):
    s = np.where(ok & inb, score, -np.inf); o = np.lexsort((-s, bid)); sel = np.zeros(n, bool)
    b = bid[o]; first = np.r_[0, np.flatnonzero(np.diff(b)) + 1]; rank = np.arange(n) - np.repeat(first, np.diff(np.r_[first, n]))
    sel[o[(rank < 5) & np.isfinite(s[o])]] = True; return sel
def run(pred, col):
    pr = pd.read_parquet(pred, columns=['season', 'date', 'cell_id', col]); pr['date'] = pd.to_datetime(pr['date'])
    hits = {g: [] for g in (0, 1, 2)}
    for Y in SEAS:
        days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20')
        M = pr[pr.season == Y].pivot(index='date', columns='cell_id', values=col).reindex(index=days, columns=range(n)).to_numpy()
        conf = np.full(n, np.datetime64('2100-01-01'), 'datetime64[ns]')
        for r in fb[fb.season == Y].itertuples(): conf[r.cell_id] = np.datetime64(r.window_end + pd.Timedelta('25D'))
        jit = 1e-9 * np.random.default_rng(Y).random(n)
        for g in hits:
            Lst = np.zeros((len(days), n), bool)
            for ti, t in enumerate(days):
                ok = ~(conf <= np.datetime64(t - pd.Timedelta('1D')))
                if g: ok &= ~Lst[max(0, ti - g):ti].any(0)
                Lst[ti] = pick(np.nan_to_num(M[ti], nan=-1) + jit, ok)
            for r in burns[burns.season == Y].itertuples():
                di = (r.fire_day - days[0]).days; hits[g].append((Y, bool(Lst[max(0, di - 2):di, r.cell_id].any())))
    o = {}
    for g, h in hits.items():
        h = pd.DataFrame(h, columns=['s', 'w']); nm = {0: 'same_list', 1: 'skip1', 2: 'skip2'}[g]
        o[nm] = {'loso_2017_24': round(100 * h[h.s < 2025].w.mean(), 1), 'test_2025_26': round(100 * h[h.s >= 2025].w.mean(), 1)}
    return o
a = sys.argv[1:]; res = {f'{a[i]}:{a[i + 1]}': run(a[i], a[i + 1]) for i in range(0, len(a), 2)}
print(json.dumps(res, indent=1))
