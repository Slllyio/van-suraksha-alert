"""Step 5. Landscape leverage: in a 5 km square-season, does more early burning (15 Feb-15 Mar scar ha, or Jan-14 Feb VIIRS
points) go with less later burning (16 Mar-15 Jun scar forest ha)?  Two-way fixed effects (square; division x season), slope on
hectares (= leverage: later ha lost per early ha) and on shares (elasticity-like). CI: bootstrap over divisions.
Also a matched comparison and the reserve table (Satpura, Kuno, Kanha). Out: out/cb5_leverage.csv, out/cb5_reserves.csv"""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
rng = np.random.default_rng(1)


def twoway(S, ycol, xcol, it=20):
    X = S[[ycol, xcol]].astype(float).copy()
    a = S.sqid.values; b = S.dyid.values
    for _ in range(it):
        for col in (ycol, xcol):
            v = X[col].values
            v = v - pd.Series(v).groupby(a).transform('mean').values
            v = v - pd.Series(v).groupby(b).transform('mean').values
            X[col] = v
    x, y = X[xcol].values, X[ycol].values
    return float((x * y).sum() / (x * x).sum())


def fit(S, ycol, xcol, nboot=300):
    b0 = twoway(S, ycol, xcol)
    keys = S.key.unique(); bs = []
    for _ in range(nboot):
        ks = rng.choice(keys, len(keys))
        T = pd.concat([S[S.key == k].assign(key=k + str(i)) for i, k in enumerate(ks)])
        T['sqid'] = T.groupby(['key', 'sq']).ngroup(); T['dyid'] = T.groupby(['key', 'year']).ngroup()
        bs.append(twoway(T, ycol, xcol, it=8))
    return b0, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main():
    S = pd.read_parquet(B.OUT + 'cb3_squares.parquet')
    S = S[S.forest_ha >= 200].copy()
    # fill missing square-seasons with zeros (a square with forest but no burn that season is a real zero)
    full = S[['key', 'sq', 'forest_ha']].drop_duplicates().merge(pd.DataFrame({'year': list(B.YEARS)}), how='cross')
    S = full.merge(S, on=['key', 'sq', 'forest_ha', 'year'], how='left').fillna(0)
    S['ha_early'] = S.ha_p1 + S.ha_p2
    S['sh_early'] = S.ha_early / S.forest_ha; S['sh_late'] = S.ha_late / S.forest_ha; S['eb100'] = 100 * S.eb_pts / S.forest_ha
    S['sqid'] = S.groupby(['key', 'sq']).ngroup(); S['dyid'] = S.groupby(['key', 'year']).ngroup()
    rows = []
    for y, x, lab in (('ha_late', 'ha_early', 'later ha per 15 Feb-15 Mar scar ha'), ('sh_late', 'sh_early', 'later share per unit early scar share'),
                      ('ha_late', 'eb_pts', 'later ha per Jan-14 Feb VIIRS point'), ('sh_late', 'eb100', 'later share per Jan-14 Feb point per 100 ha')):
        b, lo, hi = fit(S, y, x); rows.append(dict(test=lab, slope=b, lo=lo, hi=hi, n=len(S)))
        print(lab, round(b, 4), round(lo, 4), round(hi, 4), flush=True)
    # matched: squares with early share >= 5% vs 0 in the same division-season
    T = S.copy(); T['grp'] = np.where(T.sh_early >= 0.05, 'early>=5%', np.where(T.sh_early == 0, 'no early burn', 'other'))
    m = T[T.grp != 'other'].groupby(['key', 'year', 'grp']).sh_late.mean().unstack()
    m = m.dropna(); d = (m['early>=5%'] - m['no early burn'])
    rows.append(dict(test='matched: later share, early>=5% minus none (same division-season)', slope=d.mean(), lo=d.mean() - 1.96 * d.std() / np.sqrt(len(d)), hi=d.mean() + 1.96 * d.std() / np.sqrt(len(d)), n=len(d)))
    rows.append(dict(test='matched: mean later share in the no-early group', slope=m['no early burn'].mean(), lo=np.nan, hi=np.nan, n=len(d)))
    pd.DataFrame(rows).to_csv(B.OUT + 'cb5_leverage.csv', index=False); print(pd.DataFrame(rows).round(4).to_string(index=False))
    # reserves
    R = S.groupby(['key', 'year']).agg(forest_ha=('forest_ha', 'sum'), eb_pts=('eb_pts', 'sum'), ha_early=('ha_early', 'sum'), ha_late=('ha_late', 'sum'), late_pts=('late_pts', 'sum')).reset_index()
    R['late_pct'] = 100 * R.ha_late / R.forest_ha; R['eb_per_100ha'] = 100 * R.eb_pts / R.forest_ha
    R.to_csv(B.OUT + 'cb5_reserves.csv', index=False)
    for k in ('Satpura_TR', 'Kuno', 'Kanha_Tiger_Reserve', 'Obedullahganj', 'PTR_MP', 'Noradehi'):
        r = R[R.key == k]
        if len(r): print(k, r[['year', 'eb_pts', 'ha_early', 'ha_late', 'late_pct']].round(1).to_string(index=False))


if __name__ == '__main__':
    main()
