"""Maps from stored statistics, no GEE: rule or wide net, filters, pixels in the 5 x 5 box, minimum patch size. Also the old-vs-new check on chunks that exist in both formats.
Usage: e79_views.py fetch3 | compare | mmu"""
import sys

import numpy as np
import pandas as pd
from scipy import ndimage

from common import *
from e33_map10m import D as OLD, init_retry, jobs
from e49_ts import series_feats
from e53_ts_chunks import OUTD as OLDTS
from e62_s2f_chunks import OUTD as S2F
from e72_map_wide import W, YS, fetch

STRUCT = np.ones((3, 3), bool)
# owner's choice is the default: wide net + scrub-to-farm, NBR fall >= .15, 3 px, 0.1 ha minimum. Net "wide" or "net90" per view.
VIEWS = {"default: more recall 66/68": ("wide", 0, .15, 3), "balanced 97/51": ("wide", .15, .20, 5), "maximum recall 26/79": ("net90", .10, 0, 1)}
DEFAULT_MIN_PX = 10


def inputs(a):
    """Dynamic World and NDVI windows from 30 m to 10 m, as fractions; missing = NaN."""
    h, w = a["y_ln2020"].shape
    out = {}
    for k in a.files:
        if k.startswith("d_"):
            v = a[k].astype("float32")
            if k != "d_water":
                v[a[k] == -128] = np.nan
                v = v / 100
            out[k[2:]] = np.repeat(np.repeat(v, 3, 0), 3, 1)[:h, :w]
    return out


def net(d, forest="woody", td=.06, nd=.05):
    nda, ndb = d["nea"] - d["nla"], d["neb"] - d["nlb"]
    if forest == "trees":
        fa, fb = d["ea_t"] >= .30, d["eb_t"] >= .30
        tree_a, tree_b = fa & (d["ea_t"] - d["la_t"] >= .12) & (nda >= .08), fb & (d["eb_t"] - d["lb_t"] >= .12) & (ndb >= .08)
        rec = fa & (nda >= .08) & (d["mon0"] - d["mon24"] >= .17)
    else:
        fa, fb = d["ea_t"] + d["ea_s"] >= .40, d["eb_t"] + d["eb_s"] >= .40
        tree_a, tree_b = fa & (d["ea_t"] - d["la_t"] >= td) & (nda >= nd), fb & (d["eb_t"] - d["lb_t"] >= td) & (ndb >= nd)
        rec = fa & (nda >= nd) & (d["mon0"] - d["mon24"] >= .17)
    s2c = ((d["ea_t"] + d["ea_s"] >= .40) & (d["ea_t"] < .30) & (d["la_c"] - d["ea_c"] >= .15) & (nda >= .08)) | ((d["eb_t"] + d["eb_s"] >= .40) & (d["eb_t"] < .30) & (d["lb_c"] - d["eb_c"] >= .15) & (ndb >= .08))
    return (tree_a | tree_b | rec | s2c) & (d["water"] == 0)


def net90(a, d, base):
    """Wide net plus the window NBR and bare-soil triggers."""
    mean = lambda b, ys: np.nanmean(np.stack([np.where(a[f"y_{b}{y}"] == -128, np.nan, a[f"y_{b}{y}"] / 100) for y in ys]), axis=0)
    with np.errstate(invalid="ignore"):
        wood = (d["ea_t"] + d["ea_s"] >= .3) | (d["eb_t"] + d["eb_s"] >= .3)
        return base | (wood & (d["water"] == 0) & ((mean("lr", (2017, 2018, 2019)) - mean("lr", (2022, 2023, 2024)) >= .10) | (mean("lb", (2022, 2023, 2024)) - mean("lb", (2017, 2018, 2019)) >= .03)))


def scrub(name, shape):
    f = S2F / name
    return np.load(f)["f"] > 0 if f.exists() else None


def falls(a, mask):
    r, c = np.nonzero(mask)
    t = pd.DataFrame({f"{b}{y}": a[f"y_{b}{y}"][r, c].astype("float32") for b in ("ln", "lr") for y in YS}).replace(-128, np.nan) / 100
    sf = series_feats(t)
    nf, rf = np.full(mask.shape, np.nan, "float32"), np.full(mask.shape, np.nan, "float32")
    nf[r, c], rf[r, c] = sf.drop_n.values, sf.drop_r.values
    return nf, rf


def view(mask, nf, rf, fn, fr, npx, min_px=0):
    with np.errstate(invalid="ignore"):
        ok = mask & (nf >= fn if fn else True) & (rf >= fr if fr else True)
    if npx > 1:
        ok = ok & (np.rint(ndimage.uniform_filter(ok.astype("float32"), 5, mode="constant") * 25) >= npx)
    if min_px:
        lab, n = ndimage.label(ok, structure=STRUCT)
        if n:
            size = np.bincount(lab.ravel())
            size[0] = 0
            ok = size[lab] >= min_px
    return ok


def fetch3():
    init_retry()
    js = {j[5].name: j for j in jobs()}
    ranked = sorted((f.name for f in OLD.glob("*.npz") if (OLDTS / f.name).exists()), key=lambda n: -int((np.load(OLD / n)["cls"] > 0).sum()))
    pick = [ranked[3], ranked[len(ranked) // 10], ranked[len(ranked) // 5]]
    for n in pick:
        j = js[n]
        print(n, "fetched", fetch(*j[:5], W / n), flush=True)


def compare():
    rows, pts = [], []
    for f in sorted(W.glob("*.npz")):
        if not (OLD / f.name).exists():
            continue
        a = np.load(f)
        d = inputs(a)
        old = np.load(OLD / f.name)["cls"] > 0
        new = net(d, "trees")
        i, u = (old & new).sum(), (old | new).sum()
        lo, _ = ndimage.label(old, structure=STRUCT)
        hit = np.unique(lo[new & (lo > 0)])
        sizes = np.bincount(lo.ravel())[1:]
        big = np.flatnonzero(sizes >= 10) + 1
        row = dict(chunk=f.stem, old_ha=round(old.sum() * .01, 1), new_ha=round(new.sum() * .01, 1), both_ha=round(i * .01, 1), iou=round(float(i / max(u, 1)), 3), old_patches_ge_01ha=len(big), found_in_new=int(np.isin(big, hit).sum()))
        s = np.load(OLDTS / f.name)
        if len(s["r"]):
            nf, rf = falls(a, old)
            o1, o2 = s["ndvi_fall"], s["nbr_fall"]
            n1, n2 = nf[s["r"], s["c"]], rf[s["r"], s["c"]]
            ok = np.isfinite(o1) & np.isfinite(n1) & np.isfinite(o2) & np.isfinite(n2)
            pa, pb = (o1 >= .15) & (o2 >= .15), (n1 >= .15) & (n2 >= .15)
            row.update(corr_ndvi_fall=round(float(np.corrcoef(o1[ok], n1[ok])[0, 1]), 3), corr_nbr_fall=round(float(np.corrcoef(o2[ok], n2[ok])[0, 1]), 3), filter_pass_old_ha=round(pa.sum() * .01, 1), filter_pass_new_ha=round(pb.sum() * .01, 1), filter_both_ha=round((pa & pb).sum() * .01, 1), missing_new=round(float(np.isnan(n1).mean()), 3))
        rows.append(row)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(t.to_string())
    t.to_csv(OUT / "interim" / "report" / "old_vs_new_layout.csv", index=False)


def mmu():
    rows, tot, used, have = [], {}, 0, 0
    for f in sorted(W.glob("*.npz")):
        sc = scrub(f.name, None)
        a = np.load(f)
        if sc is None:
            sc = np.zeros(a["y_ln2020"].shape, bool)
        else:
            have += 1
        used += 1
        d = inputs(a)
        wide = net(d) | sc
        with_90 = net90(a, d, wide)
        nf, rf = falls(a, with_90)
        for nm, (kind, fn, fr, n) in VIEWS.items():
            m = wide if kind == "wide" else with_90
            for mp, lab in ((0, "none"), (10, "0.1 ha"), (50, "0.5 ha")):
                ok = view(m, nf, rf, fn, fr, n, mp)
                tot[(nm, lab)] = tot.get((nm, lab), 0) + int(ok.sum())
                if nm.startswith("default"):
                    tot[(nm + ", scrub-to-farm pixels", lab)] = tot.get((nm + ", scrub-to-farm pixels", lab), 0) + int((ok & sc & ~net(d)).sum())
    for (nm, lab), v in tot.items():
        rows.append(dict(view=nm, minimum=lab, ha=round(v * .01, 1), chunks=used))
    print("chunks", used, "with scrub-to-farm so far", have)
    t = pd.DataFrame(rows)
    t["share_of_no_minimum"] = (100 * t.ha / t.groupby("view").ha.transform("max")).round(1)
    print(t.to_string())
    t.to_csv(OUT / "interim" / "report" / "minimum_patch_chunks.csv", index=False)


if __name__ == "__main__":
    {"fetch3": fetch3, "compare": compare, "mmu": mmu}[sys.argv[1]]()
