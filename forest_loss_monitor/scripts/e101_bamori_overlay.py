"""Our Guna map (default view) against the Bamori thread's range rasters (ground_truth/shared/bamori-polygons/range, read-only), Bamori range only.
Area both / ours only / theirs only with causes, year agreement, our recall by their loss type, and the end state of our patches in their 2022 classes.
Their loss = loss_year > 0 (2019-24 confirmed by DW trees <= 0.10 the next year; 2025 unconfirmed, reported apart). Writes outputs/final/bamori_overlay. Usage: e101_bamori_overlay.py [Bamori|Fatehgarh]"""
import sys

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject
from scipy import ndimage

from common import *
from e97_guna_eval import CODE, GD, grid, rd

RANGE = sys.argv[1] if len(sys.argv) > 1 else "Bamori"
RG = WORK.parent / "ground_truth" / "shared" / {"Bamori": "bamori-polygons/range", "Fatehgarh": "fatehgarh"}[RANGE]
PFX = RANGE.lower()
OD = OUT / "final" / f"{PFX}_overlay"
TYPES = {1: "rabi farm", 2: "kharif / rainfed", 3: "grass / grazing", 4: "shrub regrowth", 5: "bare / open"}
C22 = {0: "outside beats or water", 1: "dense", 2: "forest", 3: "crops", 4: "fallow", 5: "bare"}


def theirs(nm, tr, shp):
    out = np.zeros(shp, "int16")
    with rasterio.open(RG / nm) as s:
        reproject(s.read(1).astype("int16"), out, src_transform=s.transform, src_crs=s.crs, dst_transform=tr, dst_crs=PROJ4, resampling=Resampling.nearest)
    return out


def ha(m):
    return round(float(m.sum()) * .01, 1)


def main():
    OD.mkdir(parents=True, exist_ok=True)
    tr, shp = grid()
    b = pd.read_csv(OUT / "beat_lookup.csv")
    rng = np.isin(np.load(GD / "guna_beat.npy"), b[(b.Division == "Guna") & (b.Range == RANGE)].zone_id.values)
    ly, lt, c22 = theirs(f"{PFX}_loss_year.tif", tr, shp), theirs(f"{PFX}_loss_type.tif", tr, shp), theirs(f"{PFX}_class2022.tif", tr, shp)
    rng &= c22 > 0                                        # their footprint (beats, not water)
    a, yr, mx = rd("guna_default"), rd("guna_year"), rd("guna_max_recall")
    ours = rng & (a > 0) & (a < 9)
    th = rng & (ly > 0) & (ly <= 2024)
    th25 = rng & (ly == 2025)
    rows = [dict(item=f"{RANGE} range forest in both footprints", ha=ha(rng)),
            dict(item="ours (default view, all classes)", ha=ha(ours)), dict(item="theirs, confirmed 2019-24", ha=ha(th)), dict(item="theirs, 2025 unconfirmed", ha=ha(th25)),
            dict(item="both", ha=ha(ours & th)), dict(item="ours only", ha=ha(ours & ~th & ~th25)), dict(item="ours inside their 2025", ha=ha(ours & th25)), dict(item="theirs only", ha=ha(th & ~ours)),
            dict(item="our precision against theirs (any year incl. 2025)", ha=round(float((ours & (th | th25)).sum() / max(ours.sum(), 1)), 3)),
            dict(item="our recall of their confirmed 2019-24", ha=round(float((ours & th).sum() / max(th.sum(), 1)), 3))]
    # within 30 m of theirs counts as touching (edge mismatch, not a different event)
    near = ndimage.binary_dilation(th | th25, iterations=3)
    rows.append(dict(item="ours only but within 30 m of theirs (edge)", ha=ha(ours & ~th & ~th25 & near)))
    pd.DataFrame(rows).to_csv(OD / "areas.csv", index=False)
    # ours-only causes: our class x their 2022 end state
    oo = ours & ~th & ~th25
    t1 = pd.crosstab(pd.Series(a[oo]).map(CODE).rename("our class"), pd.Series(c22[oo]).map(C22).rename("their 2022 class")) * .01
    t1.round(1).to_csv(OD / "ours_only_by_class_and_their_2022.csv")
    # theirs-only causes: did our wide net fire (max-recall view) or not, by their type and abruptness
    to = th & ~ours
    t2 = pd.DataFrame(dict(type=pd.Series(lt[to] % 10).map(TYPES), abrupt=lt[to] >= 10, our_net=np.where(mx[to] > 0, "our max-recall view flags it (filtered out)", "our net did not fire")))
    t2 = t2.groupby(["type", "abrupt", "our_net"]).size().unstack(fill_value=0) * .01
    t2.round(1).to_csv(OD / "theirs_only_by_type_and_our_net.csv")
    # our recall by their type
    t3 = []
    for k, nm in TYPES.items():
        for ab in (False, True):
            m = th & (lt % 10 == k) & ((lt >= 10) == ab)
            t3.append(dict(type=nm, abrupt=ab, their_ha=ha(m), ours_flags_ha=ha(m & ours), recall=round(float((m & ours).sum() / max(m.sum(), 1)), 3), our_class_mix={CODE.get(int(c), c): ha(m & ours & (a == c)) for c in (1, 2, 3)}))
    pd.DataFrame(t3).to_csv(OD / "our_recall_by_their_type.csv", index=False)
    # year agreement on shared pixels
    both = ours & th & (yr > 0)
    dy = (yr[both] - ly[both]).astype(int)
    t4 = pd.Series(dy).value_counts().sort_index() * .01
    yrs = dict(shared_ha=ha(both), exact=round(float((dy == 0).mean()), 3), within1=round(float((np.abs(dy) <= 1).mean()), 3), ours_earlier=round(float((dy < 0).mean()), 3), ours_later=round(float((dy > 0).mean()), 3), median_diff=float(np.median(dy)))
    t4.round(1).to_csv(OD / "year_difference_ours_minus_theirs_ha.csv")
    # end state of our patches (all of Bamori range) in their 2022 classes, by our class and our year (<=2021 only can be judged by 2022)
    t5 = pd.crosstab([pd.Series(a[ours]).map(CODE).rename("our class"), pd.Series(np.where(yr[ours] <= 2021, "loss year <= 2021", "loss year >= 2022")).rename("year")],
                     pd.Series(c22[ours]).map(C22).rename("their 2022 class")) * .01
    t5.round(1).to_csv(OD / "end_state_of_our_patches_class2022.csv")
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string())
    print(t1.round(1).to_string(), "\n", t2.round(1).to_string(), "\n", pd.DataFrame(t3).to_string(), "\n", yrs, "\n", t4.round(1).to_string(), "\n", t5.round(1).to_string())
    pd.Series(yrs).to_csv(OD / "year_agreement.csv")


if __name__ == "__main__":
    main()
