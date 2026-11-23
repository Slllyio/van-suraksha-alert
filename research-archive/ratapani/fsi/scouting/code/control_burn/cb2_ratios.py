"""Step 2. Re-burn ratio per class = VIIRS points seen on that ground / points expected if it burnt at the rate of not-yet-burnt
forest in the same division, season, 5 km square and week (indirect standardisation). 95% CI by bootstrap over division-seasons.
Out: out/cb2_age.csv (by age since burn, and by age x month of burn), out/cb2_cross.csv (last season / two seasons ago),
out/cb2_early.csv (pre-15 Feb VIIRS burn nearby), out/cb2_by_division.csv (12+ wk and 2-12 wk ratio per division)."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
NA = len(B.AGE_BINS) - 1
rng = np.random.default_rng(0)


def smr(D, ref_cls, groups, nboot=1000, by=None):
    """D: rows key,year,week,sq,cls,cells,pts. Expected points per row = cells x rate of ref class in the same key-year-sq-week."""
    ref = D[D.cls == ref_cls].set_index(['key', 'year', 'sq', 'week'])
    rate = (ref.pts / ref.cells).rename('rate')
    X = D.join(rate, on=['key', 'year', 'sq', 'week'], how='inner')
    X['exp'] = X.cells * X.rate
    X['g'] = X.cls.map(groups); X = X[X.g.notna()]
    if by is not None: X['g'] = X[by].astype(str) + '|' + X.g
    agg = X.groupby('g')[['pts', 'exp', 'cells']].sum()
    # bootstrap over division-seasons
    ds = X.groupby(['key', 'year']).ngroup().values; n = ds.max() + 1
    gi = X.g.astype('category'); gcodes = gi.cat.codes.values; gl = list(gi.cat.categories)
    P = np.zeros((n, len(gl))); E = np.zeros((n, len(gl)))
    np.add.at(P, (ds, gcodes), X.pts.values); np.add.at(E, (ds, gcodes), X.exp.values)
    bs = []
    for _ in range(nboot):
        w = np.bincount(rng.integers(0, n, n), minlength=n)
        bs.append((w @ P) / np.maximum(w @ E, 1e-9))
    bs = np.array(bs)
    out = pd.DataFrame({'g': gl, 'pts': [agg.loc[g, 'pts'] for g in gl], 'expected': [agg.loc[g, 'exp'] for g in gl],
                        'cells_wk': [agg.loc[g, 'cells'] for g in gl]})
    out['ratio'] = out.pts / out.expected; out['lo'] = np.percentile(bs, 2.5, axis=0); out['hi'] = np.percentile(bs, 97.5, axis=0)
    return out


def main():
    D = pd.read_parquet(B.OUT + 'cb1_classes.parquet')
    M = D[D.set == 'main']
    age_of = {2 + a * 3 + m: B.AGE_LAB[a] for a in range(NA) for m in range(3)}
    mon_of = {2 + a * 3 + m: B.MON_LAB[m] + ' burn, ' + B.AGE_LAB[a] for a in range(NA) for m in range(3)}
    A = smr(M, 0, age_of); A['kind'] = 'age'
    AM = smr(M, 0, mon_of); AM['kind'] = 'age x month'
    # coarse: 2-12 wk pooled, 12+ wk
    coarse = {k: ('2-12 wk' if v in ('2-4 wk', '4-6 wk', '6-8 wk', '8-12 wk') else v) for k, v in age_of.items()}
    AC = smr(M, 0, coarse); AC['kind'] = 'coarse'
    # by week of the season (does re-burn rise in April-May?)
    AW = smr(M, 0, {k: 'burnt >= 2 wk ago' for k in age_of if age_of[k] != '1-2 wk'}, by='week'); AW['kind'] = 'by week'
    pd.concat([A, AC, AM, AW]).to_csv(B.OUT + 'cb2_age.csv', index=False)
    print(pd.concat([A, AC]).round(3).to_string(index=False))
    X = D[D.set == 'xs']; C = smr(X, 0, {1: 'burnt last season', 2: 'burnt 2 seasons ago, not last'}); C.to_csv(B.OUT + 'cb2_cross.csv', index=False)
    print(C.round(3).to_string(index=False))
    E = D[D.set == 'eb']; Eb = smr(E, 0, {1: 'Jan-14 Feb VIIRS burn within 180 m'}); Eb.to_csv(B.OUT + 'cb2_early.csv', index=False)
    print(Eb.round(3).to_string(index=False))
    # per division, coarse classes, no bootstrap
    rows = []
    for key, g in M.groupby('key'):
        r = smr(g, 0, coarse, nboot=50)
        for _, q in r.iterrows(): rows.append(dict(key=key, cls=q.g, pts=q.pts, expected=q.expected, ratio=q.ratio))
    pd.DataFrame(rows).to_csv(B.OUT + 'cb2_by_division.csv', index=False)


if __name__ == '__main__':
    main()
