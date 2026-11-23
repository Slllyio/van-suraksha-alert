"""Step 1. The fuel-recovery clock: how often does ground that burnt earlier get fire again, compared with ground not yet burnt
in the same 5 km square and the same week?  Measured with VIIRS heat points (a re-burn leaves no second scar).
Per division, season, 5 km square, week and cell class: forest cells and VIIRS points.  Classes:
  U      not yet burnt this season (and 3x3 neighbourhood not burnt)        [reference]
  E      burnt, but within 7 days or at a scar edge (the fire itself)       [not reported]
  A<age><mon>  deep inside (3x3 cells = 180 m) a scar that burnt >= 7 days ago; age bin x month of that old burn
  Cross-season (on U cells): L1 burnt last season, L2 burnt 2 seasons ago not last, L0 neither (2019-25 only)
  Pre-15 Feb (on U cells): EB a Jan-14 Feb VIIRS point within 3 cells this season, else NB
Out: scratch cb/clock_<div>.parquet; out/cb1_classes.parquet (all)."""
import sys, os
import numpy as np, pandas as pd
from scipy import ndimage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B

NA = len(B.AGE_BINS) - 1
FS = int(os.environ.get('CB_FS', 3)); SUF = '' if FS == 3 else f'_fs{FS}'   # neighbourhood that must be burnt: 3 = 60 m from an edge, 7 = 180 m


def classify(bd, bdmax, doy):
    """Class code per cell at day doy: 0 U, 1 E, 2.. A(age,mon). 9999 = never."""
    cls = np.zeros(bd.shape, np.int16)
    burnt = bd <= doy
    cls[burnt] = 1
    age = doy - bdmax
    deep = burnt & (bdmax <= doy) & (age >= 7)
    ab = np.digitize(age, B.AGE_BINS[1:], right=False)       # 0..NA-1
    mon = np.where(bdmax < 60, 0, np.where(bdmax < 91, 1, 2))
    cls[deep] = 2 + (ab * 3 + mon)[deep]
    # U requires the 3x3 neighbourhood unburnt too (bdmin > doy)
    return cls


def run(key):
    fn = B.SC + f'clock_{key}{SUF}.parquet'
    if os.path.exists(fn): return
    L, FOR = B.load_div(key); H, W = L['H'], L['W']
    sq = (np.arange(H)[:, None] // B.SQ) * 1000 + (np.arange(W)[None, :] // B.SQ)
    rows = []
    prev = {}
    for y in B.YEARS:
        bd = B.burn_day(L, y); prev[y] = bd < 9999
        bdmax = ndimage.maximum_filter(bd, FS); bdmin = ndimage.minimum_filter(bd, 3)
        P = B.points(L['div'], y)
        r, c = B.rc(L, P.latitude.values, P.longitude.values)
        ok = (r >= 0) & (r < H) & (c >= 0) & (c < W); P = P[ok]; r, c = r[ok], c[ok]
        early = (P.doy.values < B.D0)
        EB = np.zeros((H, W), bool)
        if early.any():
            EB[r[early], c[early]] = True; EB = ndimage.binary_dilation(EB, iterations=3)
        L1 = prev.get(y - 1); L2 = prev.get(y - 2)
        for w0 in B.WEEKS:
            mid = w0 + 3
            cls = classify(bd, bdmax, mid)
            U = (bdmin > mid)
            cls[(cls == 0) & ~U] = 1
            inw = (P.doy.values >= w0) & (P.doy.values < w0 + 7)
            pr, pc_ = r[inw], c[inw]
            fp = FOR[pr, pc_]; pr, pc_ = pr[fp], pc_[fp]
            # main classes
            code = (sq * 64 + cls)[FOR]
            cc = np.bincount(code.ravel()); pp = np.bincount((sq[pr, pc_] * 64 + cls[pr, pc_]), minlength=len(cc))
            nz = np.nonzero(cc)[0]
            for i in nz:
                rows.append((key, y, w0, 'main', int(i // 64), int(i % 64), int(cc[i]), int(pp[i])))
            # cross-season and pre-15 Feb on U cells
            if L1 is not None and L2 is not None:
                xc = np.where(L1, 1, np.where(L2, 2, 0)).astype(np.int16)
                code = (sq * 64 + xc)[FOR & U]; cc = np.bincount(code.ravel())
                sel = U[pr, pc_]
                pp = np.bincount((sq[pr, pc_] * 64 + xc[pr, pc_])[sel], minlength=len(cc))
                for i in np.nonzero(cc)[0]:
                    rows.append((key, y, w0, 'xs', int(i // 64), int(i % 64), int(cc[i]), int(pp[i])))
            ec = EB.astype(np.int16)
            code = (sq * 64 + ec)[FOR & U]; cc = np.bincount(code.ravel()); sel = U[pr, pc_]
            pp = np.bincount((sq[pr, pc_] * 64 + ec[pr, pc_])[sel], minlength=len(cc))
            for i in np.nonzero(cc)[0]:
                rows.append((key, y, w0, 'eb', int(i // 64), int(i % 64), int(cc[i]), int(pp[i])))
    D = pd.DataFrame(rows, columns=['key', 'year', 'week', 'set', 'sq', 'cls', 'cells', 'pts'])
    D.to_parquet(fn); print(key, len(D), flush=True)


if __name__ == '__main__':
    import multiprocessing as mp
    keys = B.KEYS if len(sys.argv) < 2 else sys.argv[1:]
    with mp.Pool(4) as pool: pool.map(run, keys, chunksize=1)
    D = pd.concat([pd.read_parquet(B.SC + f'clock_{k}{SUF}.parquet') for k in keys if os.path.exists(B.SC + f'clock_{k}{SUF}.parquet')])
    D.to_parquet(B.OUT + f'cb1_classes{SUF}.parquet'); print('all', len(D))
