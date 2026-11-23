"""Step 5. Early burning of whole repeat patches as the strongest 'fire line' (a burnt block cannot carry a March fire).
Per tr3 patch: forest ha of the patch; fires that started inside it (majority of start cells in the patch) in 2017-21 and 2022-25:
forest ha they burnt inside the patch and outside it. Patches ranked on 2017-21 outside-ha per patch ha (what an early burn of
the patch would stop at most), then scored on 2022-25 at treated-area budgets. Upper bound: assumes an early-burnt patch carries no
fire in the season and the ignition does not move elsewhere.
Out: out/m5_patches.csv, out/m5_curve.csv"""
import pickle, glob, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0 as M
K = M.K
KEYS = sorted(p.split('fires_')[1][:-4] for p in glob.glob(M.SC26 + 'fires_*.pkl') if 'table' not in p)


def main():
    rows = []
    for key in KEYS:
        L, FOR, Z = K.load_div(key); H, W = L['H'], L['W']
        LAB = K.lab60(Z, 'tr3', H, W).ravel(); npat = int(LAB.max())
        if npat == 0: continue
        pha = np.bincount(LAB[FOR], minlength=npat + 1) * M.CELL_HA
        acc = {p: dict(key=key, div=L['div'], patch=p, patch_ha=pha[p], tr_in=0.0, tr_out=0.0, tr_n=0, te_in=0.0, te_out=0.0, te_n=0) for p in range(1, npat + 1)}
        for f in L['fires']:
            h, w = f['shape']; ig = f['ign'].astype(np.int64); gi = (ig // w + f['r0']) * W + (ig % w + f['c0'])
            lb = LAB[gi]; lb = lb[lb > 0]
            if len(lb) == 0 or len(lb) * 2 < len(ig): continue
            p = int(np.bincount(lb).argmax())
            Mm = np.unpackbits(f['M'])[:h * w].astype(bool); loc = np.nonzero(Mm)[0]; gl = (loc // w + f['r0']) * W + (loc % w + f['c0'])
            fo = FOR[gl]; inp = (LAB[gl] == p) & fo
            per = 'tr' if f['year'] in M.TRAIN else 'te'
            acc[p][per + '_in'] += inp.sum() * M.CELL_HA; acc[p][per + '_out'] += (fo & ~inp).sum() * M.CELL_HA; acc[p][per + '_n'] += 1
        rows += list(acc.values()); print(key, flush=True)
    D = pd.DataFrame(rows)
    for c in ('tr_in', 'tr_out'): D[c] /= len(M.TRAIN)
    for c in ('te_in', 'te_out'): D[c] /= len(M.TEST)
    D['lev_tr'] = D.tr_out / D.patch_ha; D['lev_te'] = D.te_out / D.patch_ha
    D = D.sort_values('lev_tr', ascending=False); D.to_csv(M.OUT + 'm5_patches.csv', index=False)
    tot = 718704.0
    D['cum_ha'] = D.patch_ha.cumsum(); D['cum_te_out'] = D.te_out.cumsum(); D['cum_te_in'] = D.te_in.cumsum(); D['cum_tr_out'] = D.tr_out.cumsum()
    out = []
    for B in (5000, 10000, 25000, 50000, 100000, 200000, 400000, 1e9):
        x = D[D.cum_ha <= B]
        if not len(x): continue
        out.append(dict(treated_ha=x.patch_ha.sum(), patches=len(x), te_out_ha=x.te_out.sum(), te_in_ha=x.te_in.sum(), tr_out_ha=x.tr_out.sum(),
                        pct_burnt_forest_out=100 * x.te_out.sum() / tot, out_per_100ha_treated=100 * x.te_out.sum() / x.patch_ha.sum(),
                        share_patches_with_out=float((x.te_out > 0).mean())))
    O = pd.DataFrame(out); O.to_csv(M.OUT + 'm5_curve.csv', index=False); print(O.round(2).to_string(index=False))
    print('all tr3 patches', D.patch_ha.sum(), 'te out', D.te_out.sum(), 'te in', D.te_in.sum())


if __name__ == '__main__':
    main()
