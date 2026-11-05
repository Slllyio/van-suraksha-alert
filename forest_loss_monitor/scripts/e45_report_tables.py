"""Report tables and charts from finished chunks, no GEE. Written to outputs/interim/report/. Usage: e45_report_tables.py
Patches are connected flagged pixels inside one chunk, so a patch crossing a chunk edge counts as two."""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from e14_accuracy import boot, metrics
from e23_guna_labels import A_H, cluster_ci, wpr
from e34_eval10m import sample
from e32_enetra10m import variants
from zones import zone as zone_of

D = WORK / "map10m"
I = OUT / "interim"
R = I / "report"
GT = ROOT / "ground_truth"
CLS = {1: "clearing", 2: "tree_to_shrub", 3: "shrub_to_crop"}
COL = {"clearing": "#7f1d1d", "tree_to_shrub": "#d97706", "shrub_to_crop": "#65a30d"}
BINS = [(0.1, 0.5), (0.5, 1), (1, 2), (2, 5), (5, 10), (10, 1e9)]
BN = ["0.1-0.5", "0.5-1", "1-2", "2-5", "5-10", ">10"]
PA = 0.01
RULE = "recent + late + shrub-to-crop + water"


def unit_table(name, label):
    t = pd.read_csv(I / f"interim_by_{label}_total.csv")
    return t


def divisions(zb):
    b = pd.read_csv(OUT / "beat_lookup.csv")
    cov = pd.read_csv(OUT / "coverage_divisions.csv")
    t = pd.read_csv(I / "interim_by_division_total.csv")
    d = cov[["Division"]].merge(t, on="Division", how="left")
    return d


def main():
    R.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    g = json.load(open(WORK / "grid.json"))
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    with rasterio.open(WORK / "zone_district.tif") as s:
        zd = s.read(1)
    bg = gpd.read_parquet(WORK / "beats_albers.parquet")
    dist = gpd.read_parquet(WORK / "districts_albers.parquet")
    lk = bg.set_index("zone_id")[["Division", "Range", "Beat"]]
    par = gpd.read_file(GT / "parivesh_polygons_good.gpkg").to_crs(PROJ4)
    par = par[par.geometry.notna() & ~par.geometry.is_empty].reset_index(drop=True)
    done = np.zeros(zb.shape, bool)
    fr, hist = [], []
    disp_shape = (g["height"] * 3 // 30 + 2, g["width"] * 3 // 30 + 2)
    disp = np.zeros(disp_shape, "uint16")
    par_hit = np.zeros(len(par), "float64")
    par_seen = np.zeros(len(par), "float64")
    par_after = np.zeros(len(par), "float64")
    sidx = par.sindex
    earliest = par.earliest.values
    for f in sorted(D.glob("*.npz")):
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        a = np.load(f)
        h, w = a["cls"].shape
        done[s.row + r // 3:s.row + (r + h) // 3, s.col + c // 3:s.col + (c + w) // 3] = True
        rr, cc = np.arange(h) // 3 + s.row + r // 3, np.arange(w) // 3 + s.col + c // 3
        zz = zb[np.ix_(rr, cc)]
        hit = (a["cls"] > 0) & (zz > 0)
        i = np.nonzero(hit)
        x0, y1 = s.x0 + c * 10, s.y1 - r * 10
        q = list(sidx.query(gpd.points_from_xy([x0], [y1]).buffer(1)[0].envelope.union(gpd.points_from_xy([x0 + w * 10], [y1 - h * 10]).buffer(1)[0].envelope).envelope))
        for k in q:
            m = rasterize([(par.geometry[k], 1)], out_shape=(h, w), transform=from_origin(x0, y1, 10, 10), fill=0, dtype="uint8", all_touched=True).astype(bool)
            if m.any():
                par_seen[k] += m.sum() * PA
                ph = m & (a["cls"] > 0)
                par_hit[k] += ph.sum() * PA
                if np.isfinite(earliest[k]):
                    par_after[k] += (ph & (a["yr"].astype(int) + 2000 >= earliest[k])).sum() * PA
        if not len(i[0]):
            continue
        fr.append(pd.DataFrame(dict(zone_id=zz[i], dist_id=zd[np.ix_(rr, cc)][i], cls=a["cls"][i], year=a["yr"][i].astype(int) + 2000)).value_counts().rename("px").reset_index())
        np.add.at(disp, ((s.row * 3 + r + i[0]) // 30, (s.col * 3 + c + i[1]) // 30), 1)
        lab, n = ndimage.label(hit, structure=np.ones((3, 3), bool))
        idx = np.arange(1, n + 1)
        size = np.bincount(lab.ravel(), minlength=n + 1)[1:]
        cl = np.stack([np.bincount(lab[a["cls"] == v], minlength=n + 1)[1:] for v in (1, 2, 3)])
        main_c = cl.argmax(0) + 1
        hist.append(pd.DataFrame(dict(ha=size * PA, cls=main_c)))
    d = pd.concat(fr).groupby(["zone_id", "dist_id", "cls", "year"], as_index=False).px.sum()
    d["ha"] = d.px * PA
    d["c"] = d.cls.map(CLS)
    d = d.merge(lk.reset_index(), on="zone_id", how="left").merge(dist[["dist_id", "dtname"]], on="dist_id", how="left")
    d["zone"] = d.Division.map(zone_of)
    n = int(bg.zone_id.max()) + 1
    fa, ca = np.bincount(zb.ravel(), minlength=n) * PX_HA, np.bincount(zb[done], minlength=n) * PX_HA
    z = lk.reset_index().assign(forest_ha=fa[lk.index], covered_ha=ca[lk.index])

    def table(key, area):
        w = d.pivot_table(index=key, columns="c", values="ha", aggfunc="sum", fill_value=0)
        for c in CLS.values():
            w[c] = w.get(c, 0.0)
        o = area.merge(w[list(CLS.values())].reset_index(), on=key, how="left").fillna(0)
        o = o.rename(columns=dict(clearing="clearing_ha", tree_to_shrub="tree_to_shrub_ha", shrub_to_crop="shrub_to_crop_ha"))
        o["total_ha"] = o.clearing_ha + o.tree_to_shrub_ha + o.shrub_to_crop_ha
        o["covered_pct"] = (100 * o.covered_ha / o.forest_ha.replace(0, np.nan)).round(1).fillna(0)
        o["rate_pct"] = (100 * o.total_ha / o.covered_ha.replace(0, np.nan)).round(3)
        return o

    dv = table("Division", z.groupby("Division", as_index=False)[["forest_ha", "covered_ha"]].sum())
    dv.insert(1, "zone", dv.Division.map(zone_of))
    dv = dv[["Division", "zone", "forest_ha", "covered_ha", "covered_pct", "clearing_ha", "tree_to_shrub_ha", "shrub_to_crop_ha", "total_ha", "rate_pct"]].sort_values("total_ha", ascending=False).round(2)
    dv.to_csv(R / "1_divisions.csv", index=False)
    m = zb > 0
    dfa, dca = np.bincount(zd[m], minlength=len(dist) + 2) * PX_HA, np.bincount(zd[m & done], minlength=len(dist) + 2) * PX_HA
    dt = table("dtname", dist.assign(forest_ha=dfa[dist.dist_id], covered_ha=dca[dist.dist_id])[["dtname", "forest_ha", "covered_ha"]])
    dt = dt[["dtname", "forest_ha", "covered_ha", "covered_pct", "clearing_ha", "tree_to_shrub_ha", "shrub_to_crop_ha", "total_ha", "rate_pct"]].sort_values("total_ha", ascending=False).round(2)
    dt.to_csv(R / "2_districts.csv", index=False)
    bt = table("zone_id", z[["zone_id", "forest_ha", "covered_ha"]]).merge(lk.reset_index(), on="zone_id")
    bt = bt[["Division", "Range", "Beat", "forest_ha", "covered_pct", "clearing_ha", "tree_to_shrub_ha", "shrub_to_crop_ha", "total_ha", "rate_pct"]].sort_values("total_ha", ascending=False).round(2)
    bt.head(50).to_csv(R / "3_top50_beats.csv", index=False)
    yz = d.groupby(["year", "c", "zone"]).ha.sum().round(1).unstack("zone", fill_value=0).reset_index().rename(columns=dict(c="class"))
    yz.to_csv(R / "4_year_class_zone.csv", index=False)
    hh = pd.concat(hist)
    rows = []
    for (lo, hi), nm in zip(BINS, BN):
        q = hh[(hh.ha >= lo) & (hh.ha < hi)]
        row = dict(size_ha=nm)
        for v, c in CLS.items():
            row[f"{c}_count"], row[f"{c}_ha"] = int((q.cls == v).sum()), round(float(q[q.cls == v].ha.sum()), 1)
        rows.append(row)
    rows.append(dict(size_ha="under 0.1 (not a patch; 1-9 px)", **{k: v for v, c in CLS.items() for k, v in ((f"{c}_count", int(((hh.ha < .1) & (hh.cls == v)).sum())), (f"{c}_ha", round(float(hh[(hh.ha < .1) & (hh.cls == v)].ha.sum()), 1)))}))
    pd.DataFrame(rows).to_csv(R / "5_patch_sizes.csv", index=False)
    pd.read_csv(I / "interim_patches_over_half_ha.csv").sort_values("ha", ascending=False).head(10)[["Division", "Range", "Beat", "year_mode", "main_class", "ha", "lat", "lon"]].to_csv(R / "7_top10_patches.csv", index=False)
    accuracy(zb)
    par["seen_ha"], par["mapped_ha"], par["mapped_after_approval_ha"] = par_seen, par_hit, par_after
    c = par[par.seen_ha >= .9 * par.kml_ha]
    p_summary = dict(good_polygons=len(par), inside_finished_chunks=len(c), overlap_mapped=int((c.mapped_ha > 0).sum()), overlap_after_approval_year=int((c.mapped_after_approval_ha > 0).sum()),
                     kml_ha=round(float(c.kml_ha.sum()), 1), approved_ha=round(float(c.approved_ha.sum()), 1), mapped_ha=round(float(c.mapped_ha.sum()), 1), mapped_after_approval_ha=round(float(c.mapped_after_approval_ha.sum()), 1),
                     share_of_area_mapped_pct=round(100 * float(c.mapped_ha.sum() / c.kml_ha.sum()), 1))
    json.dump(p_summary, open(R / "8_parivesh.json", "w"), indent=1)
    c.groupby("Category").agg(n=("kml_ha", "size"), kml_ha=("kml_ha", "sum"), mapped_ha=("mapped_ha", "sum"), any_hit=("mapped_ha", lambda s: int((s > 0).sum()))).round(1).sort_values("kml_ha", ascending=False).to_csv(R / "8_parivesh_by_category.csv")
    print(p_summary)
    charts(d, dv, disp, done, zb, g, bg)


def accuracy(zb):
    """Guna reference on the map by class, round 2 by zone with the same rule at points, Hansen on both."""
    rows = []
    g = pd.read_csv(GT / "guna_labels.csv")
    ref = g[g.source == "blind_reference"].copy()
    s_ = [sample(a, b) for a, b in zip(ref.x, ref.y)]
    ref["seen"], ref["c"] = [a[0] for a in s_], [a[1] for a in s_]
    aux = np.load(WORK / "aux_state.npz")
    hy = aux["hansen_year"]

    def box(df):
        out = np.zeros(len(df), bool)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                v = hy[df.row.values + dr, df.col.values + dc]
                out |= (v >= 18) & (v <= 25)
        return out
    ref = ref[ref.seen].copy()
    n = ref.stratum.value_counts()
    ref["_w"] = ref.stratum.map(lambda s: A_H[s] / n[s])
    ref["hansen"] = box(ref)
    for name, m in (("10 m map, all classes", ref.c > 0), ("clearing + tree-to-shrub", ref.c.isin([1, 2])), ("clearing only", ref.c == 1), ("tree-to-shrub only", ref.c == 2), ("shrub-to-crop only", ref.c == 3), ("Hansen 2018-25, same points", ref.hansen)):
        ref["m"] = m.astype(int).values
        p, r = wpr(ref.label.values, ref.m.values, ref._w.values)
        ci = cluster_ci(ref, "m")
        rows.append(dict(test="Owner's Guna reference (owner's labels)", group=name, n=len(ref), real=int(ref.label.sum()), flagged=int(ref.m.sum()), precision=round(p, 3), p_lo=ci[0][0], p_hi=ci[0][1], recall=round(r, 3), r_lo=ci[1][0], r_hi=ci[1][1]))
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id")
    k = k.assign(pid=k.sample_id + 200000).merge(pd.read_csv(GT / "enetra10m_points.csv"), on="pid")
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    k["real"] = k.label.isin(list("LD")).astype(int)
    k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
    k["zone"] = k.Division.map(zone_of)
    k["rule"] = variants(k)[RULE].astype(int).values
    k["hansen"] = box(k).astype(int)
    for meth, col in (("10 m rule at points", "rule"), ("Hansen 2018-25", "hansen")):
        for gn, q in [("ALL", k), ("deciduous (teak + mixed dry)", k[k.zone.isin(["teak_belt", "mixed_dry_deciduous"])])] + list(k.groupby("zone")):
            p, r, f = metrics(q.real.values, q[col].values, q._w.values)
            lo, hi = boot(q, area, "real", col) if q.real.sum() else ((np.nan,) * 3, (np.nan,) * 3)
            rows.append(dict(test=f"Round 2 random points (my labels): {meth}", group=gn, n=len(q), real=int(q.real.sum()), flagged=int(q[col].sum()), precision=round(p, 3), p_lo=round(lo[0], 3), p_hi=round(hi[0], 3), recall=round(r, 3), r_lo=round(lo[1], 3), r_hi=round(hi[1], 3)))
    pd.DataFrame(rows).to_csv(R / "6_accuracy.csv", index=False)


def charts(d, dv, disp, done, zb, g, bg):
    y = d.pivot_table(index="year", columns="c", values="ha", aggfunc="sum", fill_value=0).reset_index()
    fig, ax = plt.subplots(figsize=(9, 4.4))
    bot = np.zeros(len(y))
    for c in CLS.values():
        ax.bar(y.year, y[c], bottom=bot, color=COL[c], label=c.replace("_", " ").capitalize(), edgecolor="white", linewidth=.5)
        bot += y[c].values
    ax.set_xticks(y.year)
    ax.set_ylabel("Mapped hectares, finished chunks only")
    ax.set_title("Interim mapped loss by year and class (year is approximate)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1, 1))
    fig.tight_layout()
    fig.savefig(R / "interim_year_class.png", dpi=150)
    plt.close(fig)
    q = dv[dv.covered_pct >= 50].sort_values("rate_pct")
    zc = dict(mixed_dry_deciduous="#b45309", sal_belt="#166534", teak_belt="#1d4ed8", plantation_mprvvn="#7e22ce")
    fig, ax = plt.subplots(figsize=(9, max(3.5, .34 * len(q) + 1.2)))
    ax.barh(q.Division.str.replace("_", " "), q.rate_pct, color=q.zone.map(zc))
    for yy, v in enumerate(q.rate_pct):
        ax.text(v + .008, yy, f"{v:.2f}%", va="center", fontsize=8)
    ax.set_xlabel("Mapped loss as % of covered forest (not error-corrected)")
    ax.set_title("Divisions at least 50% covered")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=v, label=k.replace("_", " ")) for k, v in zc.items() if k in set(q.zone)], frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(R / "interim_division_rates.png", dpi=150)
    plt.close(fig)
    k = 10
    h, w = zb.shape[0] // k, zb.shape[1] // k
    cov = (done & (zb > 0))[:h * k, :w * k].reshape(h, k, w, k).any(axis=(1, 3))
    fo = (zb > 0)[:h * k, :w * k].reshape(h, k, w, k).any(axis=(1, 3))
    img = np.ones((h, w, 3))
    img[fo] = (.93, .93, .93)
    img[cov] = (.78, .88, .80)
    ext = [g["x0"], g["x0"] + w * k * RES, g["y1"] - h * k * RES, g["y1"]]
    hs = disp[:h, :w]
    fig, ax = plt.subplots(figsize=(12, 8.2))
    ax.imshow(img, extent=ext, interpolation="nearest")
    bg[["Division", "geometry"]].dissolve("Division").boundary.plot(ax=ax, color="#555", linewidth=.25)
    ys, xs = np.nonzero(hs)
    ax.scatter(ext[0] + (xs + .5) * k * RES, ext[3] - (ys + .5) * k * RES, s=np.clip(hs[ys, xs] * .12, .4, 14), c="#b91c1c", linewidths=0, alpha=.85)
    ax.set_title("Interim mapped loss (red) in finished chunks (green); grey forest is not done yet")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(R / "interim_map.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
