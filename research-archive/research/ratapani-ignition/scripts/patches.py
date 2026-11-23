"""Group burned 20 m pixels into scar patches and classify each as spread or new ignition.

A patch = 8-connected pixels of one season sharing the same date window (start, end].
For each patch, find the nearest earlier burn (any pixel outside the patch whose window_end
falls in [start-LOOKBACK, end]) and record its distance and date. "New ignition" at radius R =
no such burn within R metres.
Usage: python patches.py <burndir> <out.csv>
"""
import os, sys, glob, datetime as dt
import numpy as np, pandas as pd
from scipy.ndimage import label, distance_transform_edt

sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts")
import fetch

LOOKBACK = 7      # days before the patch's window start that still count as "fire nearby"
RADII = (500, 1000, 2000, 5000)
I = fetch.INSIDE
H, W = I.shape


def main(burndir, out):
    rows = []
    for f in sorted(glob.glob(os.path.join(burndir, "burn_*.npz"))):
        y = int(os.path.basename(f)[5:9]); b = np.load(f)
        start = np.full((H, W), -999, np.int16); end = np.full((H, W), -999, np.int16)
        start[I] = b["start"]; end[I] = b["end"]
        burned = end > -999
        win = np.where(burned, start.astype(np.int32) * 1000 + (end.astype(np.int32) + 500), 0)
        # label connected components per window value
        pid = np.zeros((H, W), np.int32); n = 0
        for v in np.unique(win[burned]):
            lab, k = label(win == v, structure=np.ones((3, 3)))
            pid[lab > 0] = lab[lab > 0] + n; n += k
        print(y, "patches", n, flush=True)
        # distance from each patch to earlier burns: one EDT per distinct window, over pixels whose
        # window_end lies in [start-LOOKBACK, end] and that are not in a patch with that same window
        info = {}
        from scipy import ndimage
        d0 = dt.date(y, 1, 1)
        # distances are computed on a 100 m (5x5 block) grid: accurate to ~100 m, 25x faster
        B = 5; Hb, Wb = H // B, W // B
        rb, cb = np.minimum(np.arange(H) // B, Hb - 1), np.minimum(np.arange(W) // B, Wb - 1)
        def block(m, how): return m[:Hb * B, :Wb * B].reshape(Hb, B, Wb, B).__getattribute__(how)(axis=(1, 3))
        ones = np.ones_like(pid)
        for v in np.unique(win[burned]):
            s, e = divmod(int(v), 1000); e -= 500
            prior = burned & (end >= s - LOOKBACK) & (end <= e) & (win != v)
            ids = np.unique(pid[win == v])
            if prior.any():
                db, idxb = distance_transform_edt(~block(prior, "any"), return_indices=True, sampling=fetch.RES * B)
                endb = block(np.where(prior, end, -999), "max")
                d_ = db[rb[:, None], cb[None, :]]
                dmin = ndimage.minimum(d_, pid, ids)
                pos = ndimage.minimum_position(d_, pid, ids)
            else:
                dmin = [np.inf] * len(ids); pos = [None] * len(ids)
            sizes = ndimage.sum(ones, pid, ids)
            cms = ndimage.center_of_mass(ones, pid, ids)
            for p, dm, ps, sz, cm in zip(ids, dmin, pos, sizes, cms):
                if np.isfinite(dm):
                    r_, c_ = rb[ps[0]], cb[ps[1]]
                    pe = int(endb[idxb[0][r_, c_], idxb[1][r_, c_]])
                else:
                    pe = None
                info[p] = dict(season=y, patch=int(p), window_start=(d0 + dt.timedelta(days=s)).isoformat(),
                               window_end=(d0 + dt.timedelta(days=e)).isoformat(), gap_days=e - s,
                               ha=round(float(sz) * 0.04, 2), row=int(cm[0]), col=int(cm[1]),
                               dist_prior_m=None if not np.isfinite(dm) else round(float(dm)),
                               prior_end=None if pe is None else (d0 + dt.timedelta(days=pe)).isoformat())
                for R in RADII:
                    info[p][f"new_{R}"] = int(not np.isfinite(dm) or dm > R)
        rows += list(info.values())
        np.save(os.path.join(os.path.dirname(out), f"patch_id_{y}.npy"), pid[I])
    df = pd.DataFrame(rows); df.to_csv(out, index=False)
    print(df.groupby("season")[[f"new_{R}" for R in RADII]].mean().round(2))
    print("area share new (1 km):", (df.ha * df.new_1000).sum() / df.ha.sum())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
