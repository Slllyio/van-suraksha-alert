"""MP extension of the e_Netra rule at 10 m. The rule and thresholds match the owner's detector (read from its config, unchanged). Added here:
a later window for 2023-25 loss, a separate shrub-to-crop path, a JRC water mask, change classes, and a year of change from annual leaf-on NBR.
S2 SR only (one processing level), with s2cloudless masking. Usage: e32_enetra10m.py points | score | export <tile,..> | status"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd

from common import *
from e14_accuracy import boot, metrics
from e23_guna_labels import A_H, cluster_ci, wpr
from zones import zone as zone_of

GT = ROOT / "ground_truth"
F = GT / "enetra10m_points.csv"
DW = "GOOGLE/DYNAMICWORLD/V1"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
CL = ["water", "trees", "grass", "shrub_and_scrub", "flooded_vegetation", "crops", "built", "bare"]
A_EARLY, A_LATE, B_EARLY, B_LATE = (2017, 2019), (2022, 2024), (2019, 2021), (2023, 2025)
FOREST_MIN, TREE_DROP, NDVI_DROP, RECENT_DROP, WOODY_MIN, CROP_RISE = 0.30, 0.12, 0.08, 0.17, 0.40, 0.15
ANNUAL = list(range(2017, 2026))


def dw_mean(aoi, y0, y1, m=None):
    c = ee.ImageCollection(DW).filterBounds(aoi).filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01")
    if m:
        c = c.filter(ee.Filter.calendarRange(m[0], m[1], "month"))
    return c.select(CL).mean()


def ndvi_mean(aoi, y0, y1):
    def nd(i):
        s = i.select("SCL")
        bad = s.eq(1).Or(s.eq(3)).Or(s.eq(8)).Or(s.eq(9)).Or(s.eq(10))
        return i.updateMask(bad.Not()).normalizedDifference(["B8", "B4"]).rename("ndvi")
    return ee.ImageCollection(S2).filterBounds(aoi).filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80)).map(nd).mean()


def rule_bands(aoi):
    """Flags as bands: e_cur, e_recent (owner's rule); late, s2c_a, s2c_b (additions); water; plus class inputs."""
    ea, la, eb, lb = dw_mean(aoi, *A_EARLY), dw_mean(aoi, *A_LATE), dw_mean(aoi, *B_EARLY), dw_mean(aoi, *B_LATE)
    nda = ndvi_mean(aoi, *A_EARLY).subtract(ndvi_mean(aoi, *A_LATE))
    ndb = ndvi_mean(aoi, *B_EARLY).subtract(ndvi_mean(aoi, *B_LATE))
    cur = ea.select("trees").gte(FOREST_MIN).And(ea.select("trees").subtract(la.select("trees")).gte(TREE_DROP)).And(nda.gte(NDVI_DROP))
    mon0 = dw_mean(aoi, A_EARLY[0], A_EARLY[1], (8, 10)).select("trees")
    mon24 = dw_mean(aoi, 2024, 2024, (8, 10)).select("trees")
    recent = cur.Or(ea.select("trees").gte(FOREST_MIN).And(nda.gte(NDVI_DROP)).And(mon0.subtract(mon24).gte(RECENT_DROP)))
    late = eb.select("trees").gte(FOREST_MIN).And(eb.select("trees").subtract(lb.select("trees")).gte(TREE_DROP)).And(ndb.gte(NDVI_DROP))

    def s2c(e, l, nd):
        wood = e.select("trees").add(e.select("shrub_and_scrub"))
        return wood.gte(WOODY_MIN).And(e.select("trees").lt(FOREST_MIN)).And(l.select("crops").subtract(e.select("crops")).gte(CROP_RISE)).And(nd.gte(NDVI_DROP))
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gte(5)
    return ee.Image.cat(cur.rename("e_cur"), recent.rename("e_recent"), late.rename("late"), s2c(ea, la, nda).rename("s2c_a"), s2c(eb, lb, ndb).rename("s2c_b"), water.rename("water")), ea, la, lb


def points():
    g = pd.read_csv(GT / "guna_labels.csv")
    rows = [pd.DataFrame(dict(pid=g.gid + 500000, x=g.x, y=g.y))]
    for r, sub in ((100000, "validation"), (200000, "validation2")):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
        rows.append(pd.DataFrame(dict(pid=k.sample_id + r, x=k.x, y=k.y)))
    return pd.concat(rows, ignore_index=True)


def part(p_):
    p = ee.Projection(WKT)
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(pid=int(i))) for x, y, i in zip(p_.x, p_.y, p_.pid)])
    img = rule_bands(pts.geometry().bounds(100, "EPSG:4326"))[0].toByte()
    for _ in range(4):
        try:
            return [f["properties"] for f in img.reduceRegions(pts, ee.Reducer.max(), scale=10, tileScale=8).getInfo()["features"]]
        except Exception as e:
            msg = str(e)[:200]
    print("failed", msg, flush=True)
    return []


def run_points():
    init()
    df = points()
    done = pd.read_csv(F) if F.exists() else pd.DataFrame(columns=["pid"])
    df = df[~df.pid.isin(done.pid)].assign(ry=lambda d: (d.y // 45000).astype(int), rx=lambda d: (d.x // 45000).astype(int)).sort_values(["ry", "rx"])
    rows = []
    with ThreadPoolExecutor(5) as ex:
        for r in ex.map(part, [df.iloc[i:i + 15] for i in range(0, len(df), 15)]):
            rows += r
            pd.concat([done, pd.DataFrame(rows)], ignore_index=True).to_csv(F, index=False)
            print(len(rows), flush=True)
    print("FINISHED")


def variants(t):
    nw = t.water.fillna(0) == 0
    c, r, l = t.e_cur.fillna(0) > 0, t.e_recent.fillna(0) > 0, t.late.fillna(0) > 0
    s = (t.s2c_a.fillna(0) > 0) | (t.s2c_b.fillna(0) > 0)
    return {"owner rule current": c, "owner rule recent_boost": r, "recent + water mask": r & nw, "recent + late": r | l, "recent + late + water": (r | l) & nw,
            "recent + shrub-to-crop": r | s, "recent + late + shrub-to-crop + water": (r | l | s) & nw, "shrub-to-crop alone": s & nw}


def score():
    t = pd.read_csv(F)
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000).merge(t, on="pid")
    ref = g[g.source == "blind_reference"].copy()
    n = ref.stratum.value_counts()
    ref["_w"] = ref.stratum.map(lambda s: A_H[s] / n[s])
    res = []
    for name, m in variants(ref).items():
        ref["m"] = m.astype(int).values
        p, r = wpr(ref.label.values, ref.m.values, ref._w.values)
        ci = cluster_ci(ref, "m")
        print(f"Guna reference | {name:40s} P {p:.2f} {ci[0]} R {r:.2f} {ci[1]} detections {int(ref.m.sum())}", flush=True)
        res.append(dict(test="guna_reference", rule=name, precision=round(p, 3), p_ci=ci[0], recall=round(r, 3), r_ci=ci[1]))
    for src in ("felling_alert_verdict", "bamori_validated"):
        q = g[g.source == src]
        v = variants(q)
        print(src, {k: f"{int((m & (q.label == 1)).sum())}/{int((q.label == 1).sum())} real, {int((m & (q.label == 0)).sum())}/{int((q.label == 0).sum())} false" for k, m in v.items() if k in ("owner rule recent_boost", "recent + late + water", "recent + late + shrub-to-crop + water")})
    q = g[g.source == "bamori_validated"]
    for k in ("recent + late + water", "recent + late + shrub-to-crop + water"):
        print(k, q.groupby("cls").apply(lambda d: f"{int(variants(d)[k].sum())}/{len(d)}").to_dict())
    for rnd, sub, base in ((1, "validation", 100000), (2, "validation2", 200000)):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / sub / "prelabels.csv"), on="sample_id")
        k = k.assign(pid=k.sample_id + base).merge(t, on="pid", how="left")
        area = json.load(open(OUT / sub / "strata_area_ha.json"))
        k["real"] = k.label.isin(list("LD")).astype(int)
        k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
        k["forest_zone"] = k.Division.map(zone_of)
        if rnd != 2:
            continue
        for name, m in variants(k).items():
            k["m"] = m.astype(int).values
            for gn, q in [("ALL", k), ("deciduous", k[k.forest_zone.isin(["teak_belt", "mixed_dry_deciduous"])]), ("sal_belt", k[k.forest_zone == "sal_belt"])]:
                p, r, f = metrics(q.real.values, q.m.values, q._w.values)
                lo, hi = boot(q, area, "real", "m")
                ha = float((q.m * q._w).sum())
                print(f"round 2 | {name:40s} {gn:10s} P {p:.2f} [{lo[0]:.2f},{hi[0]:.2f}] R {r:.2f} [{lo[1]:.2f},{hi[1]:.2f}] ha {ha:7.0f}", flush=True)
                res.append(dict(test=f"round2 {gn}", rule=name, precision=round(p, 3), recall=round(r, 3), flagged_ha=round(ha)))
    pd.DataFrame(res).to_csv(GT / "enetra10m_rule_tests.csv", index=False)


if __name__ == "__main__":
    {"points": run_points, "score": score}[sys.argv[1]]()
