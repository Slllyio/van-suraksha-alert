"""Step 9. Where and when to put fire watchers: forest ha burnt and fires started per 5 km square and week, 2017-25.
(a) which 45-day window holds most of the burning; (b) held out: square-weeks ranked on 2017-21, share of 2022-25 burning covered
at watcher-week budgets, against 'every forest square for a fixed window'. Out: out/cb9_sqweek.parquet, cb9_windows.csv,
cb9_budget.csv, cb9_squares.csv (per square: division, centre lat/lon, forest ha, mean ha/yr, starts/yr, peak weeks)."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
NW = 21


def run(key):
    L, FOR = B.load_div(key); H, W = L['H'], L['W']
    sq = (np.arange(H)[:, None] // B.SQ) * 1000 + (np.arange(W)[None, :] // B.SQ)
    nsq = sq.max() + 1
    fha = np.bincount(sq[FOR].ravel(), minlength=nsq) * B.CELL_HA
    rows = []
    for y in B.YEARS:
        bd = B.burn_day(L, y); m = FOR & (bd < 9999)
        wk = ((bd[m] - B.D0) // 7).clip(0, NW - 1); code = sq[m] * NW + wk
        cnt = np.bincount(code, minlength=nsq * NW) * B.CELL_HA
        st = np.zeros(nsq * NW)
        for f in L['fires']:
            if f['year'] != y: continue
            w, h = f['shape'][1], f['shape'][0]; ig = f['ign'].astype(np.int64)
            if len(ig) == 0: continue
            r = ig // w + f['r0']; c = ig % w + f['c0']; s = np.bincount(sq[r, c]).argmax()
            wk0 = int(min(max((f['t0'].dayofyear - B.D0) // 7, 0), NW - 1)); st[s * NW + wk0] += 1
        for i in np.nonzero((cnt > 0) | (st > 0))[0]:
            rows.append((key, L['div'], y, int(i // NW), int(i % NW), float(cnt[i]), float(st[i])))
    # square centres
    cen = []
    for s in np.nonzero(fha > 0)[0]:
        r0, c0 = (s // 1000) * B.SQ, (s % 1000) * B.SQ
        x = L['x0'] + (c0 + B.SQ / 2) * B.RES; yv = L['y1'] - (r0 + B.SQ / 2) * B.RES
        lon, lat = B.C25.TB.transform(x, yv); cen.append((key, L['div'], int(s), round(lat, 4), round(lon, 4), float(fha[s])))
    return pd.DataFrame(rows, columns=['key', 'division', 'year', 'sq', 'week', 'ha', 'starts']), pd.DataFrame(cen, columns=['key', 'division', 'sq', 'lat', 'lon', 'forest_ha'])


def main():
    import multiprocessing as mp
    with mp.Pool(4) as pool: res = pool.map(run, B.KEYS, chunksize=1)
    D = pd.concat([r[0] for r in res]); C = pd.concat([r[1] for r in res])
    D.to_parquet(B.OUT + 'cb9_sqweek.parquet')
    tot = D.ha.sum()
    # (a) 45-day windows
    wkha = D.groupby('week').ha.sum(); out = []
    for start in range(0, 10):
        days = list(range(start, start + 7))  # 7 weeks = 49 days
        sh = wkha.reindex(days).fillna(0).sum() / tot
        d0 = pd.Timestamp('2025-01-01') + pd.Timedelta(days=B.D0 + 7 * start - 1)
        out.append(dict(window_start=d0.strftime('%d %b'), window_end=(d0 + pd.Timedelta(days=48)).strftime('%d %b'), share_of_burnt_forest=round(sh, 3)))
    Wn = pd.DataFrame(out); Wn.to_csv(B.OUT + 'cb9_windows.csv', index=False); print(Wn.to_string(index=False))
    # (b) held-out square-week ranking
    tr = D[D.year <= 2021].groupby(['key', 'sq', 'week']).ha.sum() / 5; te = D[D.year >= 2022].groupby(['key', 'sq', 'week']).ha.sum() / 4
    te_tot = te.sum()
    rank = tr.sort_values(ascending=False)
    te_al = te.reindex(rank.index).fillna(0)
    cum = te_al.cumsum()
    nsq_forest = (C.forest_ha >= 200).sum()
    rows = []
    for n in (1000, 2000, 5000, 10000, 20000, 30000, 50000):
        rows.append(dict(plan=f'top {n:,} square-weeks (ranked on 2017-21)', watcher_weeks=n, share_2022_25=round(cum.iloc[min(n, len(cum)) - 1] / te_tot, 3)))
    # fixed windows over all forest squares (>= 200 ha)
    teW = D[(D.year >= 2022)].merge(C[C.forest_ha >= 200][['key', 'sq']], on=['key', 'sq']).groupby('week').ha.sum() / 4
    for start, n in ((5, 2), (4, 4), (3, 7), (0, 17)):
        sh = teW.reindex(range(start, start + n)).fillna(0).sum() / te_tot
        rows.append(dict(plan=f'every forest square, weeks {start}-{start+n-1} ({n} wk from {(pd.Timestamp("2025-01-01")+pd.Timedelta(days=B.D0+7*start-1)).strftime("%d %b")})', watcher_weeks=int(nsq_forest * n), share_2022_25=round(sh, 3)))
    # top squares (ranked on 2017-21 total) x peak 4 weeks (weeks 4-7)
    trs = D[D.year <= 2021].groupby(['key', 'sq']).ha.sum().sort_values(ascending=False)
    tes = D[(D.year >= 2022) & D.week.between(4, 7)].groupby(['key', 'sq']).ha.sum() / 4
    for n in (500, 1000, 2500, 5000):
        sh = tes.reindex(trs.index[:n]).fillna(0).sum() / te_tot
        rows.append(dict(plan=f'top {n:,} squares x peak 4 weeks (15 Mar-11 Apr)', watcher_weeks=n * 4, share_2022_25=round(sh, 3)))
    Bd = pd.DataFrame(rows); Bd.to_csv(B.OUT + 'cb9_budget.csv', index=False); print(Bd.to_string(index=False))
    print('forest squares >= 200 ha:', nsq_forest, ' total forest squares:', len(C))
    # squares file
    S = D.groupby(['key', 'sq']).agg(ha_yr=('ha', lambda s: s.sum() / 9), starts_yr=('starts', lambda s: s.sum() / 9)).reset_index()
    pk = D.groupby(['key', 'sq', 'week']).ha.sum().reset_index().sort_values('ha', ascending=False).groupby(['key', 'sq']).head(3)
    pk = pk.groupby(['key', 'sq']).week.apply(lambda w: ','.join((pd.Timestamp('2025-01-01') + pd.Timedelta(days=B.D0 + 7 * int(x) - 1)).strftime('%d %b') for x in sorted(w))).rename('peak_weeks_start').reset_index()
    S = C.merge(S, on=['key', 'sq'], how='left').merge(pk, on=['key', 'sq'], how='left').fillna({'ha_yr': 0, 'starts_yr': 0})
    S = S.sort_values('ha_yr', ascending=False); S['rank'] = np.arange(1, len(S) + 1); S['cum_share'] = S.ha_yr.cumsum() / S.ha_yr.sum()
    S.to_csv(B.OUT + 'cb9_squares.csv', index=False)
    print(S.head(10).to_string(index=False))


if __name__ == '__main__':
    main()
