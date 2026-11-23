"""Layer 1a check: does the detected fire rate depend on how well a square was viewed that day?
For union squares (all 87 divisions), 15 Feb-31 May 2022-24: share of square-days with a type-0 detection by best view
zenith angle of the day and by number of views. Out: out/s6_rate_by_view.csv"""
import numpy as np, pandas as pd
import common as C
import os; os.environ['R22_SUB'] = '0'
if __name__ == '__main__':
    U = np.unique(np.concatenate([r * C.W + c for r, c in C.grids().values()]))
    V = C.load_det(range(2019, 2027)); V = V[V.type == 0]
    rows = []
    for y in range(2019, 2027):
        L = np.load(C.SC + f'looks_{y}.npz'); days = pd.date_range(f'{y}-01-01', f'{y}-06-02')
        m = (days.month * 100 + days.day >= 215) & (days.month <= 5)
        v = V[V.season == y]; idx = np.searchsorted(U, v.row.values * C.W + v.col.values); ok = (idx < len(U)) & (U[np.minimum(idx, len(U) - 1)] == v.row.values * C.W + v.col.values) & v.ld.isin(days).values
        F = np.zeros((len(days), len(U)), bool); F[pd.Series(np.arange(len(days)), index=days)[v.ld.values[ok]].values, idx[ok]] = True
        mv = L['mv'][m].ravel(); nv = L['nv'][m].ravel(); f = F[m].ravel(); ef = L['ef'][m].astype(np.float32).ravel()
        vb = pd.cut(mv, [0, 20, 35, 50, 60, 75]); eb = pd.qcut(ef, 5, duplicates='drop')
        for k, g in pd.DataFrame(dict(b=vb, f=f)).groupby('b', observed=True).f: rows.append(dict(season=y, by='best_vza', bin=str(k), share=len(g) / len(f), rate_per_1000=1000 * g.mean()))
        for k, g in pd.DataFrame(dict(b=eb, f=f)).groupby('b', observed=True).f: rows.append(dict(season=y, by='eff_looks_quintile', bin=str(k), share=len(g) / len(f), rate_per_1000=1000 * g.mean()))
        print(y, flush=True)
    T = pd.DataFrame(rows); T.to_csv(C.OUT + 's6_rate_by_view.csv', index=False)
    print(T.groupby(['by', 'bin']).agg(share=('share', 'mean'), rate=('rate_per_1000', 'mean')).round(3))
