"""Run the owner's e_Netra detector, imported read-only and unchanged, at points: the Guna reference (reproduction check) and my statewide rounds.
Scored the way e_Netra scores: max over a 50 m box. Output: ground_truth/enetra_points.csv, then the comparison table. Usage: e31_enetra_statewide.py run | score"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee
import numpy as np
import pandas as pd

from common import *
from e14_accuracy import boot, metrics
from e23_guna_labels import A_H, cluster_ci, wpr
from zones import zone as zone_of

GT = ROOT / "ground_truth"
F = GT / "enetra_points.csv"
sys.dont_write_bytecode = True
VARIANTS = ["current", "recent_boost"]


def points():
    g = pd.read_csv(GT / "guna_labels.csv")
    g = g[g.source == "blind_reference"]
    rows = [pd.DataFrame(dict(pid=g.gid + 500000, x=g.x, y=g.y))]
    for r, sub in ((100000, "validation"), (200000, "validation2")):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
        rows.append(pd.DataFrame(dict(pid=k.sample_id + r, x=k.x, y=k.y)))
    return pd.concat(rows, ignore_index=True)


def run_part(part, flagged):
    p = ee.Projection(WKT)
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(pid=int(i))) for x, y, i in zip(part.x, part.y, part.pid)])
    aoi = pts.geometry().bounds(100, "EPSG:4326")
    img = ee.Image.cat([flagged(aoi, v).rename(v) for v in VARIANTS])
    for attempt in range(4):
        try:
            return [f["properties"] for f in img.reduceRegions(pts, ee.Reducer.max(), scale=10, tileScale=8).getInfo()["features"]]
        except Exception as e:
            msg = str(e)[:200]
    print("failed", msg, flush=True)
    return []


def run():
    init()
    sys.path.insert(0, str(Path("E:/e_Netra/local_detector")))
    from detector_rules import enetra_flagged
    df = points()
    done = pd.read_csv(F) if F.exists() else pd.DataFrame(columns=["pid"])
    df = df[~df.pid.isin(done.pid)].assign(ry=lambda d: (d.y // 45000).astype(int), rx=lambda d: (d.x // 45000).astype(int)).sort_values(["ry", "rx"])
    parts = [df.iloc[i:i + 15] for i in range(0, len(df), 15)]
    rows = []
    with ThreadPoolExecutor(5) as ex:
        for r in ex.map(lambda p: run_part(p, enetra_flagged), parts):
            rows += r
            pd.concat([done, pd.DataFrame(rows)], ignore_index=True).to_csv(F, index=False)
            print(len(rows), flush=True)
    print("FINISHED")


def score():
    t = pd.read_csv(F)
    g = pd.read_csv(GT / "guna_labels.csv")
    g = g[g.source == "blind_reference"].assign(pid=lambda d: d.gid + 500000).merge(t, on="pid")
    n = g.stratum.value_counts()
    g["_w"] = g.stratum.map(lambda s: A_H[s] / n[s])
    for v in VARIANTS:
        g["m"] = g[v].fillna(0).astype(int)
        p, r = wpr(g.label.values, g.m.values, g._w.values)
        print(f"Guna reference, e_Netra {v:14s} P {p:.2f} {cluster_ci(g, 'm')[0]} R {r:.2f} {cluster_ci(g, 'm')[1]} n {len(g)}; own report: current .68/.37, recent_boost .73/.47", flush=True)
    res = []
    for rnd, sub, base in ((1, "validation", 100000), (2, "validation2", 200000)):
        k = pd.read_csv(OUT / sub / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / sub / "prelabels.csv"), on="sample_id")
        k["pid"] = k.sample_id + base
        k = k.merge(t, on="pid", how="left")
        area = json.load(open(OUT / sub / "strata_area_ha.json"))
        k["real"] = k.label.isin(list("LD")).astype(int)
        k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
        k["forest_zone"] = k.Division.map(zone_of)
        print("round", rnd, "points scored", int(k.current.notna().sum()), "of", len(k))
        k = k.dropna(subset=["current"])
        for v in VARIANTS:
            k["m"] = k[v].astype(int)
            for gn, q in [("ALL", k), ("deciduous", k[k.forest_zone.isin(["teak_belt", "mixed_dry_deciduous"])])] + list(k.groupby("forest_zone")):
                if not q.real.sum():
                    continue
                p, r, f = metrics(q.real.values, q.m.values, q._w.values)
                lo, hi = boot(q, area, "real", "m")
                ha = float((q.m * q._w).sum())
                print(f"round {rnd} {v:13s} {gn:22s} n {len(q):3d} real {int(q.real.sum()):2d} P {p:.2f} [{lo[0]:.2f},{hi[0]:.2f}] R {r:.2f} [{lo[1]:.2f},{hi[1]:.2f}] flagged_ha {ha:9.0f}", flush=True)
                res.append(dict(round=rnd, variant=v, group=gn, n=len(q), real=int(q.real.sum()), precision=round(p, 3), recall=round(r, 3), flagged_ha=round(ha)))
            print(pd.crosstab(k.stratum, k.m).to_string())
            print(k[k.m == 1].label.value_counts().to_dict())
    pd.DataFrame(res).to_csv(GT / "enetra_statewide_results.csv", index=False)


if __name__ == "__main__":
    {"run": run, "score": score}[sys.argv[1]]()
