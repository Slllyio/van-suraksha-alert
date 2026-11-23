"""Check that evalr.py reproduces the mp_check strict numbers, using the two simple rules:
history = fire square-days in the 3x3 block, 15 Feb-31 May of the training seasons (ctrl dropped); recent = fire
square-days in the 7x7 block over t-6..t, ties broken by history x division day-of-year rate (approximation of the
mp_check tie-break). Random tie-breaks differ from mp_check, so expect agreement within a few tenths of a point."""
import sys, json, numpy as np, pandas as pd
from scipy.ndimage import uniform_filter
import common as C, features as Fe, evalr as E

if __name__ == '__main__':
    per = sys.argv[1] if len(sys.argv) > 1 else 'held'
    tr, te = C.PERIODS[per]; V = C.load_det(); B = Fe.base(); U, ur, uc = B['U'], B['ur'], B['uc']
    v = V[(V.type == 0) & ~V.ctrl]; md = v.ld.dt.month * 100 + v.ld.dt.day; v = v[(md >= 215) & (md <= 531) & v.season.isin(tr)].drop_duplicates(['row', 'col', 'ld'])
    hd = np.zeros((C.H, C.W)); ok = (v.row >= 0) & (v.row < C.H) & (v.col >= 0) & (v.col < C.W); np.add.at(hd, (v.row[ok], v.col[ok]), 1)
    hist = (np.round(uniform_filter(hd, 3, mode='constant') * 9, 3))[ur, uc]
    rng = np.random.default_rng(0)
    cubes = {'history': {}, 'recent': {}}
    for y in te:
        rec = []; hs = []
        for it in Fe.season_iter(y, {}, V):
            nm = it['names']; j7 = nm.index('f_r3_w7'); jc = nm.index('div_rate')
            ch = hist * it['X'][:, jc]; rec.append(it['X'][:, j7] * 1e3 + ch / (ch.max() + 1e-9) + 1e-6 * rng.random(len(U)))
            hs.append(hist + 1e-6 * rng.random(len(U)))
        cubes['history'][y] = np.stack(hs).astype(np.float32)
        cubes['recent'][y] = np.stack(rec).astype(np.float32); print(y, flush=True)
    out = {}
    for k, cu in cubes.items():
        sm, ev, dv = E.score(cu, U, per); sm.update(E.boot(ev)); out[k] = sm
        ev.to_parquet(C.SC + f'ev_rule_{k}_{per}.parquet'); print(k, json.dumps(sm, default=float), flush=True)
    json.dump(out, open(C.OUT + f'results/rules_{per}.json', 'w'), indent=1, default=float)
