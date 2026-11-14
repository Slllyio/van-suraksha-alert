"""Check of the final Bamori map (strict net + sieve + 0.5 ha patches). 1) Overlap with the owner's Bamori polygons: validated changes and rejected candidates.
2) Blind sample under random codes: 60 final patches, 20 patches the sieve removed from the strict net, 20 unflagged forest pixels; strips via e93. Usage: e104_cc_mapcheck.py overlap | sample | fetch | sheets"""
import json
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from scipy.ndimage import label
from shapely.geometry import shape

import e93_cc_strips as st
from common import *
from e97_cc_map import D

GT = ROOT / "ground_truth"
KEY = GT / "bamori_map_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
BV = "E:/e_Netra/outputs/bamori_alphaearth_v2"
SEED = 20261111
st.KEY, st.CH, st.SH = KEY, WORK / "bamori_map_strips", OUT / "bamori_map_strip_sheets"


def layers():
    g = json.load(open(D / "grid.json"))
    tr = from_origin(g["x0"], g["y1"], 10, 10)
    final, ok, cls = np.load(WORK / "cc_map_bamori_final.npy"), np.load(WORK / "cc_map_bamori_ok.npy"), np.load(WORK / "cc_map_bamori_cls.npy")
    return g, tr, final, ok, cls


def overlap():
    g, tr, final, ok, cls = layers()
    rows = []
    v = pd.read_csv(f"{BV}/validation/bamori_change_validation.csv")
    tp = gpd.read_file(f"{BV}/FINAL_LABELS/bamori_validated_change_2017_2024.geojson").to_crs(PROJ4)
    fp = gpd.read_file(f"{BV}/validation/bamori_change_polygons.geojson").to_crs(PROJ4).merge(v[v.my_verdict == 0][["poly_id", "my_notes"]], on="poly_id")
    for nm, gdf in [(f"validated change: {c}", tp[tp.change_type == c]) for c in ("forest_to_crop", "shrub_to_crop", "bare_to_crop")] + [("rejected candidates", fp)]:
        hit_poly, area, area_hit = 0, 0., 0.
        for geom in gdf.geometry:
            m = rasterize([(geom, 1)], out_shape=final.shape, transform=tr, fill=0, dtype="uint8").astype(bool)
            if not m.any():
                continue
            area += m.sum() * .01
            area_hit += (m & final).sum() * .01
            hit_poly += int((m & final).sum() * .01 >= .1)
        rows.append(dict(owner_polygons=nm, polygons=len(gdf), area_ha=round(area, 1), polygons_with_flag_0_1ha_plus=hit_poly, area_flagged_ha=round(area_hit, 1), area_flagged_pct=round(100 * area_hit / max(area, 1e-9), 1)))
    allp = rasterize([(gg, 1) for gg in pd.concat([tp.geometry, fp.geometry])], out_shape=final.shape, transform=tr, fill=0, dtype="uint8").astype(bool)
    r = pd.DataFrame(rows)
    print(r.to_string())
    print("final map", round(final.sum() * .01), "ha, of which inside any owner polygon", round((final & allp).sum() * .01), "ha")
    r.to_csv(OUT / "guna_bamori_map" / "bamori_map_vs_owner_polygons.csv", index=False)


def sample():
    g, tr, final, ok, cls = layers()
    rng = np.random.default_rng(SEED)

    def patch_points(mask, n):
        lab, k = label(mask, structure=np.ones((3, 3)))
        ids = rng.choice(np.arange(1, k + 1), min(n, k), replace=False)
        out = []
        for i in ids:
            rr, cc = np.nonzero(lab == i)
            j = rng.integers(len(rr))
            out.append((g["x0"] + (cc[j] + .5) * 10, g["y1"] - (rr[j] + .5) * 10, len(rr) * .01))
        return out

    removed = (cls == 2) & ~final
    lab, _ = label(removed, structure=np.ones((3, 3)))
    size = np.bincount(lab.ravel())
    removed = np.isin(lab, np.flatnonzero(size >= 50)) & (lab > 0)
    pts = [dict(group="final map", x=x, y_m=y, ha=h) for x, y, h in patch_points(final, 60)]
    pts += [dict(group="removed by sieve", x=x, y_m=y, ha=h) for x, y, h in patch_points(removed, 20)]
    rr, cc = np.nonzero(ok & ~final & (cls == 0))
    i = rng.choice(len(rr), 20, replace=False)
    pts += [dict(group="not flagged", x=g["x0"] + (c + .5) * 10, y_m=g["y1"] - (r + .5) * 10, ha=np.nan) for r, c in zip(rr[i], cc[i])]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 900000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(k.group.value_counts().to_dict())


if __name__ == "__main__":
    dict(overlap=overlap, sample=sample, fetch=lambda: st.fetch(2), sheets=st.sheets)[sys.argv[1]]()
