"""Score the other thread's Guna new-cropland map (outputs/guna_newcrop, read-only) at the owner's labels, fixed map (no tuning here).
Labels: 284 reference points (area-weighted), 222 Bamori change polygons, 155 Bamori land-cover polygons (25 m interior; c, c2 = crop), e_Netra field sites, 51 fellings.
Splits: 2015 survey group (rotation vs new encroachment), range, patch size. Error causes, a 24-chip sheet, and overlap with our tree-loss and scrub-to-farm patches.
Writes outputs/final/guna_newcrop_scoring. Usage: e99_newcrop_score.py"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely import wkt

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from e23_guna_labels import A_H, wpr
from e33_map10m import jobs
from e48_tests import GT, load
from e69_rule_sweep import boot
from e72_map_wide import W
from e97_guna_eval import ENETRA, GD, SH, box_codes, grid, rd, survey_type

NC = OUT / "guna_newcrop"
SD = OUT / "final" / "guna_newcrop_scoring"
ROT, NEW = (1, 2, 3), (4, 5, 6)          # 2015 codes in the map's band 2: CULTIVATION, PATTA, ENCROACHMENT | BLANK, UNDER STOCK, PLANTATION
DOUBT = {26, 46, 77, 89, 149, 48}
YS = range(2017, 2026)


def group(s):
    return "rotation (2015 CULTIVATION/PATTA/ENCROACHMENT)" if s in ROT else "new encroachment (2015 BLANK/UNDER STOCK/PLANTATION)" if s in NEW else "other or not surveyed (tank, river, outside survey)"


def mosaic(tr, shp):
    yr = np.zeros(shp, "int16")
    for f in sorted(NC.glob("newcrop_*.tif")):
        with rasterio.open(f) as s:
            tmp = np.zeros(shp, "int16")
            reproject(s.read(1), tmp, src_transform=s.transform, src_crs=s.crs, dst_transform=tr, dst_crs=PROJ4, resampling=Resampling.nearest)
            np.maximum(yr, tmp, out=yr)
    # 2015 survey over the whole division (the map's band 2 carries it only inside its own patches)
    sv = gpd.read_file(SH / "forest-stock-2015" / "guna_stock_2015.gpkg").to_crs(PROJ4)
    code = {"CULTIVATION": 1, "PATTA": 2, "ENCROACHMENT": 3, "BLANK": 4, "UNDER STOCK": 5, "PLANTATION": 6}
    s15 = rasterize([(g, code.get(survey_type(t), 0)) for g, t in zip(sv.geometry, sv.Type) if g is not None], out_shape=shp, transform=tr, fill=0, dtype="int16")
    return yr, s15


def point_feats(p):
    """Per point: DW crop years (crops >= 0.30) early and late, ending land state, from the 5 x 5 box medians."""
    m = p.groupby("pid").median(numeric_only=True)
    f = pd.DataFrame(index=m.index)
    f["crop_yrs_1719"] = sum((m[f"c{y}"] >= .3).astype(int) for y in (2017, 2018, 2019))
    f["crop_yrs_2325"] = sum((m[f"c{y}"] >= .3).astype(int) for y in (2023, 2024, 2025))
    f["rabi_1719"] = m[[f"r{y}" for y in (2017, 2018, 2019)]].max(axis=1)
    f["rabi_2325"] = m[[f"r{y}" for y in (2023, 2024, 2025)]].max(axis=1)
    f["end_crop"] = m[["c2023", "c2024", "c2025"]].mean(axis=1) >= np.maximum(m[["t2023", "t2024", "t2025"]].mean(axis=1), m.la_s)
    return f


def cause(r):
    if r.label == 1 and r.flag == 0:
        if not r.end_crop:
            return "loss did not end as crop (tree loss, shrub or bare)"
        if r.crop_yrs_1719 > 0:
            return "crop already seen in 2017-19 (rule excludes it)"
        if r.crop_yrs_2325 < 2:
            return "fewer than 2 crop years in 2023-25"
        return "crop late and early clean, missed (likely below 0.5 ha or edge)"
    if r.label == 0 and r.flag == 1:
        if r.crop_yrs_1719 == 0 and r.crop_yrs_2325 >= 2:
            return "crop signal at an unchanged spot (old field not seen in 2017-19, or label miss)"
        if r.crop_yrs_2325 < 2:
            return "patch spills over the point (point itself not cropped)"
        return "point cropped throughout (fallow cycle read as new)"
    return ""


def points(tr, yr, s15, size, lab):
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    rows = []
    for q in g.itertuples():
        b = box_codes(yr, tr, q.x, q.y, 1)
        if b is None:
            continue
        hit = b > 0
        lb = box_codes(lab, tr, q.x, q.y, 1)
        sv = box_codes(s15, tr, q.x, q.y, 1)
        rows.append(dict(pid=q.pid, source=q.source, label=q.label, cls=q.cls, stratum=q.stratum, beat=q.beat, Range=q.Range, x=q.x, y=q.y, flag=int(hit.any()),
                         patch_ha=float(size[lb[hit]].max()) if hit.any() else 0., s15=int(np.bincount(sv.ravel().clip(0)).argmax())))
    d = pd.DataFrame(rows)
    d["group2015"] = d.s15.map(group)
    return d.join(point_feats(load()[lambda p: p.pid.isin(d.pid)]), on="pid")


def pr(q, res, labels, grp):
    if not len(q):
        return
    a, b = wpr(q.label.values, q.flag.values, q.w.values)
    ci = boot(q.label.values.astype(float), q.w.values, q.flag.values.astype(bool), q.beat.values) if q.label.sum() >= 3 and q.flag.sum() >= 3 else ("", "")
    res.append(dict(labels=labels, group=grp, n=len(q), real=int(q.label.sum()), flagged=int(q.flag.sum()), true_flags=int((q.label * q.flag).sum()),
                    precision=round(a, 3), p_range=ci[0], recall=round(b, 3), r_range=ci[1]))


def polygons(tr, shp, yr, s15, res):
    det = yr > 0
    bp = gpd.read_file(f"{ENETRA}/bamori_alphaearth_v2/FINAL_LABELS/bamori_validated_change_2017_2024.geojson").to_crs(PROJ4)
    lc = pd.DataFrame(json.load(open(SH / "bamori-polygons" / "polys.json")))
    lc = gpd.GeoDataFrame(lc, geometry=lc.wkt.map(wkt.loads), crs=PROJ4)
    fs = gpd.read_file(f"{ENETRA}/local_detector/field_verification/field_labeled_polygons.geojson").to_crs(PROJ4)
    out = []
    for nm, polys, key, buf in (("Bamori change polygons", bp, "change_type", 0), ("land-cover polygons 2022, interior", lc, "cls", -25), ("e_Netra field and reference sites", fs, "label", 0)):
        for i, q in polys.iterrows():
            gg = q.geometry.buffer(buf) if buf else q.geometry
            if gg is None or gg.is_empty:
                continue
            m = rasterize([(gg, 1)], out_shape=shp, transform=tr, fill=0, dtype="uint8").astype(bool)
            if not m.any():
                continue
            sv = s15[m]
            out.append(dict(set=nm, id=q.get("i", q.get("poly_id", i)), cls=str(q[key]), ha=m.sum() * .01, det_ha=(det & m).sum() * .01, group2015=group(int(np.bincount(sv.clip(0)).argmax()))))
    o = pd.DataFrame(out)
    o["flagged"] = o.det_ha > 0
    o["crop_label"] = o.cls.isin(["c", "c2"]) | o.cls.str.contains("crop")
    o.to_csv(SD / "polygons_scored.csv", index=False)
    for (nm, k), q in o.groupby(["set", "cls"]):
        res.append(dict(labels=nm, group=f"class {k}", n=len(q), flagged=int(q.flagged.sum()), share_polygons_flagged=round(q.flagged.mean(), 3), share_area_flagged=round(q.det_ha.sum() / q.ha.sum(), 3)))
    for (nm, k, gp), q in o[o.set != "e_Netra field and reference sites"].groupby(["set", "crop_label", "group2015"]):
        res.append(dict(labels=nm, group=f"{'crop' if k else 'not crop'} labels, {gp}", n=len(q), flagged=int(q.flagged.sum()), share_polygons_flagged=round(q.flagged.mean(), 3), share_area_flagged=round(q.det_ha.sum() / q.ha.sum(), 3)))
    q = o[(o.set == "land-cover polygons 2022, interior") & ~o.id.isin(DOUBT)]
    for k, qq in q.groupby("cls"):
        res.append(dict(labels="land-cover polygons 2022, interior, six doubtful removed", group=f"class {k}", n=len(qq), flagged=int(qq.flagged.sum()), share_polygons_flagged=round(qq.flagged.mean(), 3), share_area_flagged=round(qq.det_ha.sum() / qq.ha.sum(), 3)))
    q = o[o.set == "Bamori change polygons"]
    for k, qq in q.groupby(pd.cut(q.ha, [0, 1, 5, 1e9], labels=["<1 ha", "1-5 ha", ">5 ha"]), observed=True):
        res.append(dict(labels="Bamori change polygons", group=f"polygon size {k}", n=len(qq), flagged=int(qq.flagged.sum()), share_polygons_flagged=round(qq.flagged.mean(), 3), share_area_flagged=round(qq.det_ha.sum() / qq.ha.sum(), 3)))
    return o


def chip_index():
    idx = []
    for j in jobs():
        s, r, c, h, w, p = j
        idx.append((s.x0 + c * 10, s.y1 - r * 10, h, w, W / p.name))
    return idx


def chips(e, tr, yr, ours):
    idx = chip_index()
    pick = pd.concat([e[(e.label == 1) & (e.flag == 0)].head(12), e[(e.label == 0) & (e.flag == 1)].head(12)])
    fig, ax = plt.subplots(len(pick), 3, figsize=(7.5, 2.4 * len(pick)))
    for k, r in enumerate(pick.itertuples()):
        f = next((t for t in idx if t[0] <= r.x < t[0] + t[3] * 10 and t[1] - t[2] * 10 < r.y <= t[1] and t[4].exists()), None)
        col, row = map(int, ~tr * (r.x, r.y))
        sl = (slice(row - 30, row + 31), slice(col - 30, col + 31))
        for a in ax[k]:
            a.set_xticks([]), a.set_yticks([])
        if f is not None:
            z = np.load(f[4])
            cc, rr = int((r.x - f[0]) / 10), int((f[1] - r.y) / 10)
            for a, y in zip(ax[k][:2], (2018, 2024)):
                v = z[f"y_ln{y}"][max(rr - 30, 0):rr + 31, max(cc - 30, 0):cc + 31].astype(float)
                a.imshow(np.where(v == -128, np.nan, v / 100), cmap="RdYlGn", vmin=0, vmax=.8)
                a.plot(30, 30, "k+", ms=10)
                a.set_title(f"NDVI Oct-Nov {y}", fontsize=7)
        a = ax[k][2]
        a.imshow(np.where(yr[sl] > 0, 1, np.nan), cmap="autumn", vmin=0, vmax=1)
        a.contour(ours[sl] > 0, levels=[.5], colors="b", linewidths=.6)
        a.plot(30, 30, "k+", ms=10)
        a.set_title(("MISS" if r.label else "FALSE FLAG") + f" pid {r.pid}, {r.Range}", fontsize=7)
        ax[k][0].set_ylabel(r.cause[:38], fontsize=6)
    plt.tight_layout()
    plt.savefig(SD / "chips_12_misses_12_false_flags.png", dpi=110)
    plt.close()


def overlap(yr, s15, ours, beat):
    gm = beat > 0
    nc = (yr > 0) & gm
    kind = np.where(ours == 3, "our scrub-to-farm", np.where((ours == 1) | (ours == 2), "our tree loss", np.where(ours == 9, "our flooded mask", "not in our map")))
    df = pd.DataFrame(dict(kind=kind[nc], grp=pd.Series(s15[nc]).map(group)))
    t = df.groupby(["grp", "kind"]).size().unstack(fill_value=0) * .01
    t["total_ha"] = t.sum(axis=1)
    t.loc["all"] = t.sum()
    ours_ha = {k: float(((ours == v) & gm).sum() * .01) for k, v in (("scrub_to_farm", 3), ("clearing", 1), ("tree_to_shrub", 2))}
    ours_in_nc = {k: float(((ours == v) & nc).sum() * .01) for k, v in (("scrub_to_farm", 3), ("clearing", 1), ("tree_to_shrub", 2))}
    t.round(1).to_csv(SD / "overlap_with_our_map_ha.csv")
    union = float((nc | ((ours > 0) & (ours < 9) & gm)).sum() * .01)
    return t, ours_ha, ours_in_nc, union


def main():
    SD.mkdir(parents=True, exist_ok=True)
    tr, shp = grid()
    yr, s15 = mosaic(tr, shp)
    beat = np.load(GD / "guna_beat.npy")
    yr[beat == 0] = 0
    lab, n = ndimage.label(yr > 0, structure=np.ones((3, 3), bool))
    size = np.bincount(lab.ravel()) * .01
    print("new-crop map on our grid", round((yr > 0).sum() * .01), "ha,", n, "patches")
    res = []
    d = points(tr, yr, s15, size, lab)
    d["band"] = pd.cut(d.patch_ha, [0, .5, 1, 5, 1e9], labels=["<0.5", "0.5-1", "1-5", ">5"])
    ref = d[d.source == "blind_reference"].copy()
    n_ = ref.stratum.value_counts()
    ref["w"] = ref.stratum.map(lambda s: A_H[s] / n_[s])
    L = "owner's reference points, area-weighted, truth = any loss"
    pr(ref, res, L, "all")
    for key in ("group2015", "Range"):
        for k, q in ref.groupby(key):
            pr(q, res, L, f"{key}={k}")
    for (k1, k2), q in ref.groupby(["Range", "group2015"]):
        if q.flag.sum() or q.label.sum():
            pr(q, res, L, f"Range={k1}, {k2}")
    rc = ref[(ref.label == 0) | ref.end_crop]
    pr(rc, res, "owner's reference points, area-weighted, truth = loss that ends as crop (DW 2023-25 proxy)", "all")
    for k, q in rc.groupby("group2015"):
        pr(q, res, "owner's reference points, truth = loss ending as crop", f"group2015={k}")
    for k, q in ref[ref.flag == 1].groupby("band", observed=True):
        res.append(dict(labels=L, group=f"precision, patch {k} ha", n=len(q), flagged=len(q), true_flags=int(q.label.sum()), precision=round(float(np.average(q.label, weights=q.w)), 3)))
    for nm, src in (("owner's 51 dated fellings", "felling_alert_verdict"), ("owner's Bamori polygons, centre 3 x 3", "bamori_validated")):
        q = d[(d.source == src) & (d.label == 1)]
        res.append(dict(labels=nm, group="flagged as new crop", n=len(q), real=len(q), flagged=int(q.flag.sum()), recall=round(float(q.flag.mean()), 3)))
    o = polygons(tr, shp, yr, s15, res)
    ref["cause"] = ref.apply(cause, axis=1)
    e = ref[ref.cause != ""]
    e.round(3).to_csv(SD / "errors_reference_points.csv", index=False)
    ours = rd("guna_default")
    chips(e, tr, yr, ours)
    t, ours_ha, ours_in_nc, union = overlap(yr, s15, ours, beat)
    r = pd.DataFrame(res)
    r.to_csv(SD / "scores.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    print(r.to_string())
    print(e.groupby(["label", "cause"]).size().to_string())
    print(t.round(1).to_string())
    print("our default map ha", ours_ha, "of which inside new-crop map", ours_in_nc, "union of both maps ha", round(union))
    json.dump(dict(ours_ha=ours_ha, ours_inside_newcrop_ha=ours_in_nc, union_ha=union), open(SD / "overlap_summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
