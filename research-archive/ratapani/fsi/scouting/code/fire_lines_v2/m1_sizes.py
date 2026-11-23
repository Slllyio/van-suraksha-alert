"""Step 1. What limits a fire line's saving: fire sizes, where big fires recur, and how much burning starts inside repeat patches.
(a) share of burnt forest ha by fire size, per season;  (b) 5 km squares: do the squares that burnt most in 2017-21 burn most in
2022-25 (rank correlation, share held by the top squares), for all fires and for fires >= 500 ha;  (c) fires that start inside a
repeat patch (tr3, held out 2022-25; all5, in-sample 2017-25): forest ha burnt inside and outside the patch per year.
Out: out/m1_sizes.json, out/m1_squares.csv"""
import pickle, glob, json, os, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0 as M
K = M.K
BIN = 5000.0
KEYS = sorted(p.split('fires_')[1][:-4] for p in glob.glob(M.SC26 + 'fires_*.pkl') if 'table' not in p)


def main():
    rows = []; sq = {}; starts = []
    for key in KEYS:
        L, FOR, Z = K.load_div(key); H, W = L['H'], L['W']
        ins = np.kron(Z['ins'], np.ones((M.AGG, M.AGG), bool))[:H, :W].ravel()
        LAB3 = K.lab60(Z, 'tr3', H, W).ravel(); LAB5 = K.lab60(Z, 'all5', H, W).ravel()
        # forest per 5 km square (inside the division)
        g = np.nonzero(FOR & ins)[0]
        bx = np.floor((L['x0'] + (g % W + .5) * M.RES) / BIN).astype(int); by = np.floor((L['y1'] - (g // W + .5) * M.RES) / BIN).astype(int)
        for b, n in zip(*np.unique(np.c_[bx, by], axis=0, return_counts=True)):
            d = sq.setdefault((int(b[0]), int(b[1])), dict(forest=0.0, tr=0.0, te=0.0, tr_big=0.0, te_big=0.0, tr_nbig=0, te_nbig=0))
            d['forest'] += n * M.CELL_HA
        for f in L['fires']:
            h, w = f['shape']; Mm = np.unpackbits(f['M'])[:h * w].astype(bool)
            loc = np.nonzero(Mm)[0]; gl = (loc // w + f['r0']) * W + (loc % w + f['c0'])
            fo = FOR[gl]; fha = fo.sum() * M.CELL_HA
            rows.append(dict(key=key, year=f['year'], ha=f['ha'], forest_ha=fha))
            cx = L['x0'] + (f['c0'] + w / 2) * M.RES; cy = L['y1'] - (f['r0'] + h / 2) * M.RES
            d = sq.setdefault((int(cx // BIN), int(cy // BIN)), dict(forest=0.0, tr=0.0, te=0.0, tr_big=0.0, te_big=0.0, tr_nbig=0, te_nbig=0))
            per = 'tr' if f['year'] in M.TRAIN else 'te'
            d[per] += fha
            if fha >= 500: d[per + '_big'] += fha; d[per + '_nbig'] += 1
            # starts inside patches
            ig = f['ign'].astype(np.int64); gi = (ig // w + f['r0']) * W + (ig % w + f['c0'])
            for name, LAB, yrs in (('tr3', LAB3, M.TEST), ('all5', LAB5, M.ALL)):
                if f['year'] not in yrs: continue
                inside = LAB[gi] > 0
                inp = (LAB[gl] > 0) & fo
                starts.append(dict(key=key, set=name, year=f['year'], start_in=bool(inside.mean() >= 0.5), touches=bool(inp.any()),
                                   forest_ha=fha, in_patch_ha=inp.sum() * M.CELL_HA, out_patch_ha=(fo & ~(LAB[gl] > 0)).sum() * M.CELL_HA))
        print(key, flush=True)
    F = pd.DataFrame(rows); S = pd.DataFrame(starts)
    res = {}
    # (a) sizes
    tot = F.forest_ha.sum() / 9; res['forest_ha_per_yr'] = tot; res['fires_per_yr'] = len(F) / 9
    res['by_size'] = {}
    for lo, hi in ((0, 10), (10, 50), (50, 100), (100, 200), (200, 500), (500, 1000), (1000, 1e9)):
        m = (F.forest_ha >= lo) & (F.forest_ha < hi)
        res['by_size'][f'{lo}-{hi}'] = dict(fires_per_yr=m.sum() / 9, share_ha=F.forest_ha[m].sum() / F.forest_ha.sum(),
                                            share_fires=m.mean(), mean_ha=F.forest_ha[m].mean() if m.any() else 0)
    res['by_year'] = {int(y): dict(forest_ha=g.forest_ha.sum(), fires=len(g), share_ge500=g.forest_ha[g.forest_ha >= 500].sum() / g.forest_ha.sum())
                      for y, g in F.groupby('year')}
    # (b) squares
    Q = pd.DataFrame([dict(bx=k[0], by=k[1], **v) for k, v in sq.items()]); Q = Q[Q.forest > 0]
    Q['tr'] /= 5; Q['te'] /= 4; Q['tr_big'] /= 5; Q['te_big'] /= 4
    Q.to_csv(M.OUT + 'm1_squares.csv', index=False)
    res['squares'] = dict(n=len(Q), spearman_all=float(spearmanr(Q.tr, Q.te)[0]), spearman_big=float(spearmanr(Q.tr_big, Q.te_big)[0]),
                          spearman_all_te_vs_forest=float(spearmanr(Q.forest, Q.te)[0]))
    for col in ('tr', 'tr_big'):
        o = Q.sort_values(col, ascending=False)
        for frac in (0.02, 0.05, 0.10, 0.20):
            n = int(np.ceil(frac * len(Q))); top = o.iloc[:n]
            res['squares'][f'top{int(frac*100)}_by_{col}'] = dict(n_squares=n, share_forest=top.forest.sum() / Q.forest.sum(),
                share_te_all=top.te.sum() / Q.te.sum(), share_te_big=top.te_big.sum() / Q.te_big.sum(),
                te_ha_per_yr=top.te.sum(), te_big_ha_per_yr=top.te_big.sum(), burn_rate_te=top.te.sum() / top.forest.sum())
    res['squares']['base_burn_rate_te'] = Q.te.sum() / Q.forest.sum()
    had = Q.tr_nbig > 0
    res['squares']['big_fire_persistence'] = dict(squares_with_big_tr=int(had.sum()), share_with_big_te_given_tr=float((Q.te_nbig[had] > 0).mean()),
                                                  share_with_big_te_overall=float((Q.te_nbig > 0).mean()), share_te_big_ha_in_squares_with_big_tr=float(Q.te_big[had].sum() / Q.te_big.sum()))
    # (c) patch starts
    res['patch_starts'] = {}
    for name, g in S.groupby('set'):
        ny = len(M.TEST) if name == 'tr3' else len(M.ALL)
        tot_ha = F[F.year.isin(M.TEST if name == 'tr3' else M.ALL)].forest_ha.sum() / ny
        si = g[g.start_in]; so = g[~g.start_in & g.touches]
        res['patch_starts'][name] = dict(years=ny, total_forest_ha_per_yr=tot_ha, fires_start_in_per_yr=len(si) / ny,
            start_in_forest_ha_per_yr=si.forest_ha.sum() / ny, start_in_inside_ha_per_yr=si.in_patch_ha.sum() / ny, start_in_outside_ha_per_yr=si.out_patch_ha.sum() / ny,
            enter_from_outside_fires_per_yr=len(so) / ny, enter_inside_ha_per_yr=so.in_patch_ha.sum() / ny, enter_total_forest_ha_per_yr=so.forest_ha.sum() / ny,
            all_in_patch_ha_per_yr=g.in_patch_ha.sum() / ny, share_of_burnt_forest_touching=g[g.touches].forest_ha.sum() / ny / tot_ha,
            start_in_share_of_burnt=si.forest_ha.sum() / ny / tot_ha, start_in_outside_share_of_burnt=si.out_patch_ha.sum() / ny / tot_ha,
            by_year={int(y): dict(start_in_outside=gg[gg.start_in].out_patch_ha.sum(), start_in_inside=gg[gg.start_in].in_patch_ha.sum()) for y, gg in g.groupby('year')})
    json.dump(res, open(M.OUT + 'm1_sizes.json', 'w'), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float)[:3000])


if __name__ == '__main__':
    main()
