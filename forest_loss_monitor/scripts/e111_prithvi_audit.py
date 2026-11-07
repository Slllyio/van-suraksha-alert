"""Prithvi diagnosis, step 1 (label audit) and inputs for step 3: class counts per range, 2015 signal per class (rabi / summer / post-monsoon NDVI, brightness),
likely-mislabelled pixels under a fixed rule, per-range band statistics, patch layout per range, and an alignment overlay of 5 random patches.
Mislabel rule (declared here, from 2015 HLS only, before any variant is scored):
  forest label looks non-wooded: post-monsoon (Oct-Dec) NDVI < 0.40;
  farm label looks wooded: post-monsoon NDVI >= 0.60 and summer (Apr-Jun) NDVI >= 0.30 and rabi - summer NDVI < 0.10 (no crop cycle).
  open (BLANK) is not cleaned (blank land may legitimately hold scrub, grass or fallow).
Writes work/survey_model/clean_mask.npy and outputs/final/survey_model/audit_*.csv / audit_alignment.png. Usage: e111_prithvi_audit.py"""
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from e106_survey_data import NAMES, SM, hls, ndvi
from e107_survey_states import OD

IMG = 224


def main():
    L = np.load(SM / "labels30.npz")
    lab, rng, cid, zone = L["lab"], L["rng"], L["cid"], L["zone"]
    ranges = pd.read_csv(SM / "ranges.csv", index_col=0).iloc[:, 0].to_dict()
    a = hls(2015)
    nr, ns, npm = ndvi(a, 0), ndvi(a, 1), ndvi(a, 2)
    bright = np.where(a[3 * 0 + 2] == -9999, np.nan, (a[2].astype("float32") + a[3] + a[4]) / 3e4)   # rabi red+NIR+SWIR1 mean reflectance
    miss = (a[[2, 3, 8, 9, 14, 15]] == -9999).any(0)
    m = lab > 0
    d = pd.DataFrame(dict(cls=lab[m], rng=rng[m], cid=cid[m], rabi=nr[m], summer=ns[m], post=npm[m], bright=bright[m], miss=miss[m]))
    d["range"] = d.rng.map(ranges)
    d["class"] = d.cls.map(NAMES)
    # counts
    cnt = d.groupby(["range", "class"]).size().unstack(fill_value=0)
    cnt["forest_share"] = (cnt.forest / cnt.sum(axis=1)).round(3)
    cnt.loc["ALL"] = cnt.drop(columns="forest_share").sum().tolist() + [round(float((d.cls == 1).mean()), 3)]
    cnt.to_csv(OD / "audit_counts.csv")
    # signal per class
    q = d.groupby("class")[["rabi", "summer", "post", "bright"]].describe(percentiles=[.1, .25, .5, .75, .9]).round(3)
    q.to_csv(OD / "audit_signal_by_class.csv")
    # mislabel rule
    bad_f = (d.cls == 1) & (d.post < .40)
    bad_c = (d.cls == 3) & (d.post >= .60) & (d.summer >= .30) & ((d.rabi - d.summer) < .10)
    d["suspect"] = bad_f | bad_c
    sus = d.groupby("class").agg(pixels=("suspect", "size"), suspect=("suspect", "sum"), missing_2015=("miss", "mean"))
    sus["suspect_share"] = (sus.suspect / sus.pixels).round(3)
    comp = d.groupby(["class", "cid"]).suspect.mean()
    sus["compartments_majority_suspect"] = [int((comp.loc[c] > .5).sum()) if c in comp.index.get_level_values(0) else 0 for c in sus.index]
    sus["compartments"] = [int(comp.loc[c].shape[0]) if c in comp.index.get_level_values(0) else 0 for c in sus.index]
    sus.to_csv(OD / "audit_suspect.csv")
    clean = lab.copy()
    rr, cc = np.nonzero(m)
    clean[rr[d.suspect.values], cc[d.suspect.values]] = 0
    np.save(SM / "clean_lab.npy", clean)
    # per-range band statistics (z of each range's mean against the all-Guna mean, in all-Guna std units)
    bands = [f"s{k}_B{b}" for k in range(3) for b in (2, 3, 4, 5, 6, 7)]
    rows = []
    for g, nm in ranges.items():
        mm = (rng == g)
        rows.append(dict(range=nm, **{b: float(np.nanmean(np.where(a[i][mm] == -9999, np.nan, a[i][mm]))) for i, b in enumerate(bands)}))
    st = pd.DataFrame(rows).set_index("range")
    allm = pd.Series({b: float(np.nanmean(np.where(a[i][zone > 0] == -9999, np.nan, a[i][zone > 0]))) for i, b in enumerate(bands)})
    alls = pd.Series({b: float(np.nanstd(np.where(a[i][zone > 0] == -9999, np.nan, a[i][zone > 0]))) for i, b in enumerate(bands)})
    ((st - allm) / alls).round(2).to_csv(OD / "audit_range_band_shift_z.csv")
    # patch layout: share of each patch's labelled pixels in its majority range
    org = pd.read_csv(SM / "prithvi_tok2015" / "origins.csv").values
    pure = []
    for r, c in org:
        w = rng[max(r, 0):r + IMG, max(c, 0):c + IMG]
        w = w[(w > 0)]
        pure.append(np.bincount(w).max() / len(w) if len(w) else np.nan)
    pure = np.array(pure)
    # alignment overlay: 5 random patches with labelled pixels
    rs = np.random.default_rng(3)
    pick = rs.choice([i for i, (r, c) in enumerate(org) if (lab[max(r, 0):r + IMG, max(c, 0):c + IMG] > 0).mean() > .2], 5, replace=False)
    fig, ax = plt.subplots(5, 3, figsize=(10, 17))
    for k, i in enumerate(pick):
        r, c = org[i]
        sl = (slice(max(r, 0), r + IMG), slice(max(c, 0), c + IMG))
        rgb = np.stack([a[14][sl], a[15][sl], a[16][sl]], -1).astype("float32") / 4000      # post-monsoon NIR, SWIR1, SWIR2 false colour
        ax[k, 0].imshow(np.clip(np.nan_to_num(rgb), 0, 1))
        ax[k, 1].imshow(npm[sl], cmap="RdYlGn", vmin=0, vmax=.8)
        ax[k, 2].imshow(np.where(lab[sl] > 0, lab[sl], np.nan), cmap="viridis", vmin=1, vmax=3, interpolation="nearest")
        for j in (0, 1):
            ax[k, j].contour(cid[sl], levels=np.unique(cid[sl])[1:] - .5, colors="w", linewidths=.3)
        for j, t in enumerate(("post-monsoon false colour + compartments", "post-monsoon NDVI + compartments", "labels: forest / open / farm")):
            ax[k, j].set_title(f"patch {i}: {t}", fontsize=7)
            ax[k, j].set_xticks([]), ax[k, j].set_yticks([])
    plt.tight_layout()
    plt.savefig(OD / "audit_alignment.png", dpi=90)
    pd.set_option("display.width", 250)
    print(cnt.to_string())
    print(q[["post", "summer", "rabi"]].xs("50%", axis=1, level=1).to_string())
    print(sus.to_string())
    print("patches", len(org), "median majority-range share", round(float(np.nanmedian(pure)), 3), "patches >95% one range", int((pure > .95).sum()))
    print(((st - allm) / alls).round(2)[["s0_B5", "s1_B5", "s2_B5", "s2_B6"]].to_string())


if __name__ == "__main__":
    main()
