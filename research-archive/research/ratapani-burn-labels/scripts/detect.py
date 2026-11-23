"""Detect dated burn scars for one fire season from the per-date observations written by fetch.py.

A pixel burns at clear observation k when, compared with the previous clear observation j
(at most MAX_GAP days earlier), NBR drops sharply, NIR darkens, MIRBI rises, and the drop
persists in the next clear observations (leaf fall is gradual and bright; cloud-shadow and
haze artefacts recover at once). Its burn date is only known to lie in (date_j, date_k].
Only the first burn per pixel per season counts, and only on tree, shrub or grass cover.

Usage: python detect.py <year> <obsdir> <outdir>
"""
import os, sys, glob, datetime as dt
import numpy as np
from scipy.ndimage import label, uniform_filter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch

P = dict(dnbr=0.12, dnbr_jan=0.18, dnir=0.01, persist=0.07, max_gap=20, persist_days=25, min_px=50, win=75)
# Landsat/Sentinel-2 median ratios over Ratapani forest on near-same-day pairs (2017)
S2_TO_LS = dict(nir=0.955, swir1=0.91, swir2=0.88)
LANDCOVER_OK = (10, 20, 30)  # ESA WorldCover tree, shrub, grass
SEASON = (dt.date(1, 1, 1), dt.date(1, 6, 20))  # burns dated Jan 1 to Jun 20


def load(obsdir):
    files = sorted(glob.glob(os.path.join(obsdir, "*.npz")))
    dates = [dt.date.fromisoformat(os.path.basename(f)[:10]) for f in files]
    # one observation per date: prefer the file with more clear pixels
    keep = {}
    for f, d in zip(files, dates):
        v = np.load(f)["valid"].mean()
        if d not in keep or v > keep[d][1]:
            keep[d] = (f, v)
    dates = sorted(keep)
    n, m = len(dates), fetch.INSIDE.sum()
    nbr = np.full((n, m), np.nan, np.float32)
    nir = np.full((n, m), np.nan, np.float32)
    mirbi = np.full((n, m), np.nan, np.float32)
    for i, d in enumerate(dates):
        z = np.load(keep[d][0])
        v = z["valid"]
        r = {k: z[k].astype(np.float32) / 10000 for k in ("nir", "swir1", "swir2")}
        if keep[d][0].endswith("_s2.npz"):  # bring Sentinel-2 onto the Landsat scale
            r = {k: r[k] * S2_TO_LS[k] for k in r}
        s = r["nir"] + r["swir2"]
        ok = v & (s > 0.02)
        nbr[i, ok] = ((r["nir"] - r["swir2"]) / s)[ok]
        nir[i, ok] = r["nir"][ok]
        mirbi[i, ok] = (10 * r["swir2"] - 9.8 * r["swir1"] + 2)[ok]
    return dates, nbr, nir, mirbi


def local_mean(x, ok, size):
    """Clipped moving-window mean of x over pixels in ok (2-D window of size px)."""
    if ok.sum() < 100:
        return np.full(x.shape, np.nan, np.float32)
    F = np.zeros(fetch.INSIDE.shape, np.float32)
    Wt = np.zeros(fetch.INSIDE.shape, np.float32)
    lo, hi = np.percentile(x[ok], [10, 90])
    F[fetch.INSIDE] = np.where(ok, np.clip(x, lo, hi), 0)
    Wt[fetch.INSIDE] = ok
    m = uniform_filter(F, size) / np.maximum(uniform_filter(Wt, size), 1e-3)
    return m[fetch.INSIDE]


def detect(dates, nbr, nir, mirbi, lc, year):
    """Changes are taken relative to the surrounding ~1.5 km landscape, which removes leaf fall,
    green-down and date-to-date radiometric differences that affect whole hillsides at once.
    January needs a bigger drop: green-down is patchy then and fires are rare."""
    n, m = nbr.shape
    doy = np.array([(d - dt.date(year, 1, 1)).days for d in dates])  # negative in December
    last_day = (SEASON[1] - dt.date(1, 1, 1)).days
    start = np.full(m, -999, np.int16)
    end = np.full(m, -999, np.int16)
    mag = np.zeros(m, np.float32)
    last = np.full(m, -1)  # index of previous clear obs per pixel
    burned = np.zeros(m, bool)
    eligible = np.isin(lc, LANDCOVER_OK)
    ar = np.arange(m)
    for k in range(n):
        ok_k = ~np.isnan(nbr[k])
        pair = (last >= 0) & ok_k & eligible
        pair[pair] &= (doy[k] - doy[last[pair]]) <= P["max_gap"]
        if 0 <= doy[k] <= last_day and pair.sum() > 1000:
            j = np.where(pair, last, k)
            dn = nbr[j, ar] - nbr[k]
            dr = nir[j, ar] - nir[k]
            rdn = dn - local_mean(dn, pair, P["win"])
            rdr = dr - local_mean(dr, pair, P["win"])
            thr = P["dnbr_jan"] if doy[k] < 31 else P["dnbr"]
            cand = pair & ~burned & (rdn >= thr) & (rdr >= P["dnir"])
            later = np.where((doy > doy[k]) & (doy <= doy[k] + P["persist_days"]))[0]
            if cand.any() and len(later):
                with np.errstate(all="ignore"):
                    import warnings
                    warnings.simplefilter("ignore")
                    fut = np.nanmean(nbr[later], axis=0)
                df = nbr[j, ar] - fut
                okf = pair & ~np.isnan(df)
                rdf = np.full(m, np.nan, np.float32)
                rdf[okf] = (df - local_mean(np.nan_to_num(df), okf, P["win"]))[okf]
                ci = np.where(cand & (rdf >= P["persist"]))[0]
                start[ci] = doy[last[ci]]
                end[ci] = doy[k]
                mag[ci] = rdn[ci]
                burned[ci] = True
        last[ok_k] = k
    # keep only scars of at least min_px, where a scar is a connected patch (8-neighbour) of pixels
    # that first showed up on the same date; small isolated drops were mostly false alarms
    full_end = np.full(fetch.INSIDE.shape, -999, np.int16)
    full_end[fetch.INSIDE] = end
    drop2 = np.zeros(fetch.INSIDE.shape, bool)
    for e in np.unique(end[end > -999]):
        lab, _ = label(full_end == e, structure=np.ones((3, 3)))
        sizes = np.bincount(lab.ravel())
        small = sizes < P["min_px"]
        small[0] = False
        drop2 |= small[lab]
    drop = drop2[fetch.INSIDE]
    start[drop], end[drop], mag[drop] = -999, -999, 0
    burned &= ~drop
    return start, end, mag, burned


def main(year, obsdir, outdir):
    os.makedirs(outdir, exist_ok=True)
    lc = np.load(fetch.WORLDCOVER)
    dates, nbr, nir, mirbi = load(obsdir)
    start, end, mag, burned = detect(dates, nbr, nir, mirbi, lc, year)
    np.savez_compressed(os.path.join(outdir, f"burn_{year}.npz"), start=start, end=end, mag=mag,
                        dates=np.array([d.isoformat() for d in dates]))
    print(year, "obs", len(dates), "burned km2 %.1f" % (burned.sum() * 400 / 1e6))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], sys.argv[3])
