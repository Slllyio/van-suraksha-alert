"""Recommended layer: flagged pixels with fitted-break fall >= 0.15 in NDVI and NBR and at least 2 such pixels in the 5 x 5 box around them (the 50 m box used for scoring); plantation zone unfiltered.
Nothing is deleted: unfiltered totals and every patch stay, with attributes. Boxes stop at chunk edges. Built from chunks and their time-series sidecars, no GEE.
Writes interim_filtered_vs_unfiltered.csv and interim_patches_attributes.csv. Usage: e54_recommended.py"""
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy import ndimage

from common import *
from e33_map10m import D
from e53_ts_chunks import FALL, OUTD
from zones import zone as zone_of

REPORT = OUT / "interim" / "report"
CLS = {1: "clearing", 2: "tree_to_shrub", 3: "shrub_to_crop"}
PA = .01
MIN_PX = 2


def layers(a, s):
    """Pixel masks for one chunk: ts = both falls pass; rec = ts with enough ts pixels in its box."""
    h, w = a["cls"].shape
    nf, rf = np.full((h, w), np.nan, "float32"), np.full((h, w), np.nan, "float32")
    nf[s["r"], s["c"]], rf[s["r"], s["c"]] = s["ndvi_fall"], s["nbr_fall"]
    with np.errstate(invalid="ignore"):
        ts = (nf >= FALL) & (rf >= FALL)
    n = ndimage.uniform_filter(ts.astype("float32"), 5, mode="constant") * 25
    return nf, rf, ts, ts & (np.rint(n) >= MIN_PX)


def main():
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as src:
        zb = src.read(1)
    b = gpd.read_parquet(WORK / "beats_albers.parquet")
    lk = b.set_index("zone_id")[["Division", "Range", "Beat"]]
    global NOFILT
    NOFILT = np.zeros(int(b.zone_id.max()) + 1, bool)     # held-out test: the filter cuts real plantation felling, so plantation keeps every flagged pixel
    NOFILT[b.zone_id[b.Division.map(zone_of) == "plantation_mprvvn"].values] = True
    tr = Transformer.from_crs(PROJ4, "EPSG:4326", always_xy=True)
    px, pt = [], []
    files = [f for f in sorted(D.glob("*.npz")) if (OUTD / f.name).exists()]
    for f in files:
        s0 = np.load(OUTD / f.name)
        if not len(s0["r"]):
            continue
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        a = np.load(f)
        h, w = a["cls"].shape
        zz = zb[np.ix_(np.arange(h) // 3 + s.row + r // 3, np.arange(w) // 3 + s.col + c // 3)]
        nf, rf, ts, rec = layers(a, s0)
        hit = (a["cls"] > 0) & (zz > 0)
        rec = rec | (hit & NOFILT[zz])
        i = np.nonzero(hit)
        if not len(i[0]):
            continue
        px.append(pd.DataFrame(dict(zone_id=zz[i], cls=a["cls"][i], year=a["yr"][i].astype(int) + 2000, ts=ts[i], rec=rec[i])).value_counts().rename("px").reset_index())
        lab, n = ndimage.label(hit, structure=np.ones((3, 3), bool))
        idx = np.arange(1, n + 1)
        o = ndimage.find_objects(lab)
        for j, sl in zip(idx, o):
            m = lab[sl] == j
            k = a["cls"][sl][m]
            rr, cc = np.nonzero(m)
            x, y = s.x0 + (c + sl[1].start + cc.mean() + .5) * 10, s.y1 - (r + sl[0].start + rr.mean() + .5) * 10
            lon, lat = tr.transform(x, y)
            z0 = np.bincount(zz[sl][m]).argmax()
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    pt.append(dict(ha=round(m.sum() * PA, 2), main_class=CLS[int(np.bincount(k, minlength=4)[1:].argmax()) + 1], year_mode=int(np.bincount(a["yr"][sl][m]).argmax()) + 2000, ndvi_fall=round(float(np.nanmean(nf[sl][m])), 3), nbr_fall=round(float(np.nanmean(rf[sl][m])), 3),
                                   npix=int(ts[sl][m].sum()), rec_px=int(rec[sl][m].sum()), ts_pass=int(rec[sl][m].any()), zone_filter="none (plantation)" if NOFILT[z0] else "ndvi and nbr fall >= 0.15, 2 px", lat=round(lat, 6), lon=round(lon, 6), Division=lk.Division.get(z0, ""), Range=lk.Range.get(z0, ""), Beat=lk.Beat.get(z0, "")))
    d = pd.concat(px).groupby(["zone_id", "cls", "year", "ts", "rec"], as_index=False).px.sum().merge(lk.reset_index(), on="zone_id")
    d["ha"], d["c"], d["zone"] = d.px * PA, d.cls.map(CLS), d.Division.map(zone_of)
    rows = []
    for level, keys in (("state", []), ("year x class", ["year", "c"]), ("zone", ["zone"]), ("zone x class", ["zone", "c"]), ("division", ["Division"])):
        g = d.assign(_="all").groupby(keys or ["_"])
        o = pd.DataFrame(dict(unfiltered_ha=g.ha.sum(), filter_only_ha=d[d.ts].assign(_="all").groupby(keys or ["_"]).ha.sum(), recommended_ha=d[d.rec].assign(_="all").groupby(keys or ["_"]).ha.sum())).fillna(0).reset_index()
        o["kept_pct"] = (100 * o.recommended_ha / o.unfiltered_ha).round(1)
        o.insert(0, "level", level)
        rows.append(o.round(1))
    out = pd.concat(rows, ignore_index=True).drop(columns="_", errors="ignore")
    out = out[["level"] + [c for c in ("year", "c", "zone", "Division") if c in out] + ["unfiltered_ha", "filter_only_ha", "recommended_ha", "kept_pct"]].rename(columns=dict(c="class"))
    out.to_csv(REPORT / "interim_filtered_vs_unfiltered.csv", index=False)
    p = pd.DataFrame(pt).sort_values("ha", ascending=False)
    p.to_csv(REPORT / "interim_patches_attributes.csv.gz", index=False)
    print("chunks with attributes", len(files), "patches", len(p), "patches passing", int(p.ts_pass.sum()), "ha in passing patches", round(p[p.ts_pass == 1].ha.sum()))
    print(out[out.level.isin(["state", "zone", "zone x class"])].to_string(index=False))


if __name__ == "__main__":
    main()
