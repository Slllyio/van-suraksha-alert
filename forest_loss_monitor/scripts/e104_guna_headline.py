"""Guna headline from the blind stratified sample (304 spots, labelled blind from yearly 10 m NDVI strips + annual DW trees).
Tree loss = labelled loss that did not become farmland (clearing, thinning, excavation); farmland conversions belong to new farmland, taken from the Guna thread's
sample-adjusted estimate (5,910 ha on 2015 forest land). No double count: a tree-loss spot inside the new-crop map stays tree loss ("now cropped") and its area
is removed from new farmland. Writes outputs/final/guna_headline/. Usage: e104_guna_headline.py"""
import numpy as np
import pandas as pd
import rasterio

from common import *
from e33_map10m import jobs
from e97_guna_eval import GD, grid, rd
from e98_dw_year import OUTD as DWY
from e102_guna_sample import SD, newcrop

HD = OUT / "final" / "guna_headline"
SHARED = WORK.parent / "ground_truth" / "shared"
Z = 1.96


def strat(pts, fr, col):
    """Stratified total (ha) and 95% range for indicator column col; pts must carry stratum."""
    tot, var = 0., 0.
    for q in fr[fr.n > 0].itertuples():
        y = pts.loc[pts.stratum == q.stratum, col].values.astype(float)
        if not len(y):
            continue
        A = q.ha
        p = y.mean()
        tot += A * p
        var += A ** 2 * (p * (1 - p) / max(len(y) - 1, 1))
    se = var ** .5
    return round(tot), round(max(tot - Z * se, 0)), round(tot + Z * se), round(se)


def domain(pts, fr, col, mask):
    """Domain (range) estimate: indicator x domain membership, same strata."""
    return strat(pts.assign(_v=pts[col] * mask), fr, "_v")


def woody(tr, shp, beat):
    """DW trees >= 0.30 area in 2017 and 2025 inside Guna beats, 30 m sidecar upsampled."""
    t17, t25 = np.zeros(shp, bool), np.zeros(shp, bool)
    for s, r, c, h, w, p in jobs():
        f = DWY / p.name
        if not f.exists():
            continue
        col, row = map(int, ~tr * (s.x0 + c * 10, s.y1 - r * 10))
        if row >= shp[0] or col >= shp[1] or row + h <= 0 or col + w <= 0:
            continue
        t = np.load(f)["t"]
        for i, out in ((0, t17), (8, t25)):
            m = np.repeat(np.repeat((t[i] >= 30) & (t[i] != 255), 3, 0), 3, 1)[:h, :w]
            rs, cs = max(0, -row), max(0, -col)
            re_, ce = min(h, shp[0] - row), min(w, shp[1] - col)
            out[row + rs:row + re_, col + cs:col + ce] |= m[rs:re_, cs:ce]
    return t17 & (beat > 0), t25 & (beat > 0)


def main():
    HD.mkdir(parents=True, exist_ok=True)
    tr, shp = grid()
    beat = np.load(GD / "guna_beat.npy")
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    fr = pd.read_csv(SD / "sample_frame.csv")
    pts = pd.read_csv(SD / "sample_points.csv").merge(pd.read_csv(SD / "labels.csv"), on="sid")
    nc = newcrop(tr, shp)
    pts["in_newcrop"] = nc[pts.row, pts.col]
    pts["Range"] = pts.zone_id.map(lk.Range)
    pts["tree"] = ((pts.loss == 1) & (pts.kind == "clear")).astype(int)
    pts["farm"] = ((pts.loss == 1) & (pts.kind == "crop")).astype(int)
    pts["tree_in_nc"] = (pts.tree & pts.in_newcrop).astype(int)
    pts.to_csv(HD / "sample_labelled.csv", index=False)
    a = rd("guna_default")
    mapped = (a == 1) | (a == 2)
    t17, t25 = woody(tr, shp, beat)
    rs = pd.read_csv(SHARED / "guna_range_summary_all_layers.csv").set_index("Range")
    nf_total = float(rs.loc["Guna", "new_farmland_on_2015_forest_sample_adjusted_ha"])
    nf_se = (6600 - 5200) / (2 * Z)          # Guna thread's 95% range 5,200-6,600 ha
    rows = []
    for nm, col in (("all loss (my labels)", "loss"), ("tree loss, not farmland", "tree"), ("new farmland (my labels, all beat land)", "farm"), ("tree loss inside new-crop map", "tree_in_nc")):
        e = strat(pts, fr, col)
        rows.append(dict(item=nm, est_ha=e[0], lo=e[1], hi=e[2], se=e[3], spots=int(pts[col].sum())))
    tl = rows[1]
    ov = rows[3]["est_ha"]
    forest = float((beat > 0).sum() * .01)
    head = pd.DataFrame(rows + [
        dict(item="mapped tree loss (default view, clearing + tree-to-shrub)", est_ha=round(mapped.sum() * .01)),
        dict(item="new farmland on 2015 forest land, Guna thread sample-adjusted", est_ha=round(nf_total)),
        dict(item="combined: tree loss + new farmland - overlap", est_ha=round(tl["est_ha"] + nf_total - ov), lo=round(tl["est_ha"] + nf_total - ov - Z * (tl["se"] ** 2 + nf_se ** 2) ** .5),
             hi=round(tl["est_ha"] + nf_total - ov + Z * (tl["se"] ** 2 + nf_se ** 2) ** .5), se=round((tl["se"] ** 2 + nf_se ** 2) ** .5)),
        dict(item="woody cover (DW trees >= 0.30) 2017", est_ha=round(t17.sum() * .01)), dict(item="woody cover (DW trees >= 0.30) 2025", est_ha=round(t25.sum() * .01)),
        dict(item="forest (beat area)", est_ha=round(forest))])
    head["pct_of_forest"] = (100 * head.est_ha / forest).round(2)
    head.to_csv(HD / "guna_headline.csv", index=False)
    yr = pts[pts.tree == 1].year.value_counts().sort_index()
    # by range
    out = []
    bz = pd.Series(beat[beat > 0]).map(lk.Range)
    for rg, q in rs.drop(index="Guna").iterrows():
        m = (pts.Range == rg).astype(int)
        e = domain(pts, fr, "tree", m)
        o = domain(pts, fr, "tree_in_nc", m)[0]
        zr = np.isin(beat, lk[(lk.Division == "Guna") & (lk.Range == rg)].index.values)
        nf = float(q.new_farmland_on_2015_forest_sample_adjusted_ha)
        out.append(dict(Range=rg, forest_ha=q.forest_ha, spots=int(m.sum()), tree_loss_sample_ha=e[0], tree_loss_lo=e[1], tree_loss_hi=e[2], tree_loss_mapped_ha=round((mapped & zr).sum() * .01),
                        new_farmland_sample_adjusted_ha=nf, combined_ha=round(e[0] + nf - o), combined_pct_of_forest=round(100 * (e[0] + nf - o) / q.forest_ha, 2), cropland_2023_25_ha=q.cropland_2023_25_ha,
                        woody_2017_ha=round((t17 & zr).sum() * .01), woody_2025_ha=round((t25 & zr).sum() * .01)))
    R = pd.DataFrame(out)
    R.to_csv(HD / "guna_by_range.csv", index=False)
    # by beat: the range sample/mapped ratio applied to each beat's mapped tree loss (too few spots per beat for a direct estimate)
    bs = pd.read_csv(SHARED / "guna_beat_summary_all_layers.csv")
    gl = lk[lk.Division == "Guna"].reset_index()
    mb = pd.Series(beat[mapped & (beat > 0)]).value_counts() * .01
    gl["tree_loss_mapped_ha"] = gl.zone_id.map(mb).fillna(0)
    ratio = (R.set_index("Range").tree_loss_sample_ha / R.set_index("Range").tree_loss_mapped_ha.replace(0, np.nan)).fillna(0)
    gl["tree_loss_est_ha"] = (gl.tree_loss_mapped_ha * gl.Range.map(ratio)).round(1)
    B = bs.merge(gl[["Range", "Beat", "tree_loss_mapped_ha", "tree_loss_est_ha"]], on=["Range", "Beat"], how="left")
    B["combined_ha"] = (B.tree_loss_est_ha.fillna(0) + B.new_farmland_on_2015_forest_sample_adjusted_ha).round(1)
    B["combined_pct_of_forest"] = (100 * B.combined_ha / B.forest_ha).round(2)
    B = B[["Range", "Beat", "forest_ha", "tree_loss_est_ha", "tree_loss_mapped_ha", "new_farmland_on_2015_forest_sample_adjusted_ha", "combined_ha", "combined_pct_of_forest", "cropland_2023_25_ha"]]
    B.to_csv(HD / "guna_by_beat.csv", index=False)
    pd.set_option("display.width", 250)
    print(head.to_string())
    print("tree-loss years (spots)", yr.to_dict())
    print(R.to_string())
    print(pts.groupby("stratum")[["loss", "tree", "farm"]].agg(["size", "sum"]).to_string())
    print("labelled-loss spots inside the new-crop map:", pts[pts.loss == 1].in_newcrop.value_counts().to_dict(), "| confidence:", pts[pts.loss == 1].conf.value_counts().to_dict())


if __name__ == "__main__":
    main()
