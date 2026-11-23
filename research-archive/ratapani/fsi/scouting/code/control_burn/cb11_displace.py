"""Step 11. Displacement beyond the square: does early burning (15 Feb-15 Mar scar ha) in a 5 km square go with MORE later
burning (16 Mar-15 Jun) in the neighbouring squares (ring 1 = the 8 squares around it, 5-10 km; ring 2 = the 16 squares beyond,
10-15 km)? Two-way fixed effects (square; division x season) on later ha with own early ha and the ring sums as regressors,
bootstrap over divisions. Net leverage per early ha = own slope + 8 x ring-1 slope + 16 x ring-2 slope (an early ha sits in the
ring-1 sum of its 8 neighbours and the ring-2 sum of the 16 beyond). Rings stop at the division edge (each division has its own grid).
Out: out/cb11_displace.csv"""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
rng = np.random.default_rng(2)


def rings(S, col):
    """ring-1 and ring-2 sums of col over squares of the same division-season."""
    S = S.copy(); S['r'] = S.sq // 1000; S['c'] = S.sq % 1000
    idx = {(k, y, r, c): v for k, y, r, c, v in zip(S.key, S.year, S.r, S.c, S[col])}
    r1 = np.zeros(len(S)); r2 = np.zeros(len(S))
    for i, (k, y, r, c) in enumerate(zip(S.key, S.year, S.r, S.c)):
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dr == 0 and dc == 0: continue
                v = idx.get((k, y, r + dr, c + dc))
                if v is None: continue
                if max(abs(dr), abs(dc)) == 1: r1[i] += v
                else: r2[i] += v
    return r1, r2


def demean(S, cols, it=20):
    X = S[cols].astype(float).copy(); a = S.sqid.values; b = S.dyid.values
    for _ in range(it):
        for col in cols:
            v = X[col].values
            v = v - pd.Series(v).groupby(a).transform('mean').values
            v = v - pd.Series(v).groupby(b).transform('mean').values
            X[col] = v
    return X


def ols(S, ycol, xcols, it=20):
    X = demean(S, [ycol] + xcols, it)
    A = X[xcols].values; y = X[ycol].values
    return np.linalg.lstsq(A, y, rcond=None)[0]


def fit(S, ycol, xcols, nboot=200):
    b0 = ols(S, ycol, xcols); keys = S.key.unique(); bs = []
    for _ in range(nboot):
        ks = rng.choice(keys, len(keys))
        T = pd.concat([S[S.key == k].assign(key=k + str(i)) for i, k in enumerate(ks)])
        T['sqid'] = T.groupby(['key', 'sq']).ngroup(); T['dyid'] = T.groupby(['key', 'year']).ngroup()
        bs.append(ols(T, ycol, xcols, it=8))
    bs = np.array(bs)
    return b0, np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0), bs


def main():
    S = pd.read_parquet(B.OUT + 'cb3_squares.parquet')
    full = S[['key', 'sq', 'forest_ha']].drop_duplicates().merge(pd.DataFrame({'year': list(B.YEARS)}), how='cross')
    S = full.merge(S, on=['key', 'sq', 'forest_ha', 'year'], how='left').fillna(0)
    S['ha_early'] = S.ha_p1 + S.ha_p2
    S['e1'], S['e2'] = rings(S, 'ha_early')
    S['p1'], S['p2'] = rings(S, 'eb_pts')
    S['f1'], S['f2'] = rings(S, 'forest_ha')
    S = S[S.forest_ha >= 200].copy()
    S['sqid'] = S.groupby(['key', 'sq']).ngroup(); S['dyid'] = S.groupby(['key', 'year']).ngroup()
    print('square-seasons', len(S), 'squares with full ring 1', int((S.f1 > 0).sum()))
    rows = []
    for ycol, xcols, lab, mult in (('ha_late', ['ha_early', 'e1', 'e2'], 'scar ha 15 Feb-15 Mar', (1, 8, 16)),
                                   ('ha_late', ['eb_pts', 'p1', 'p2'], 'VIIRS points Jan-14 Feb', (1, 8, 16))):
        b, lo, hi, bs = fit(S, ycol, xcols)
        net = (bs * np.array(mult)).sum(1); net0 = float((b * np.array(mult)).sum())
        for x, bb, l, h, m, nm in zip(xcols, b, lo, hi, mult, ('own square', 'ring 1 (5-10 km), per neighbour', 'ring 2 (10-15 km), per neighbour')):
            rows.append(dict(early=lab, term=nm, slope=bb, lo=l, hi=h, squares_in_ring=m))
        rows.append(dict(early=lab, term='net per early unit (own + 8 x ring 1 + 16 x ring 2)', slope=net0, lo=float(np.percentile(net, 2.5)), hi=float(np.percentile(net, 97.5)), squares_in_ring=np.nan))
        rows.append(dict(early=lab, term='displaced to rings per early unit (8 x ring 1 + 16 x ring 2)', slope=net0 - b[0], lo=float(np.percentile(net - bs[:, 0], 2.5)), hi=float(np.percentile(net - bs[:, 0], 97.5)), squares_in_ring=np.nan))
        print(lab, np.round(b, 4), np.round(lo, 4), np.round(hi, 4), 'net', round(net0, 4), flush=True)
    R = pd.DataFrame(rows); R.to_csv(B.OUT + 'cb11_displace.csv', index=False); print(R.round(4).to_string(index=False))


if __name__ == '__main__':
    main()
