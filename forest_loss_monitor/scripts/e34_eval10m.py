"""Measure the 10 m map on points from the fetched chunks: the owner's Guna reference, felling years, round-2 points where chunks exist, Parivesh polygons.
Also area per division and class, and map area by year. Usage: e34_eval10m.py"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from common import *
from e14_accuracy import boot, metrics
from e23_guna_labels import A_H, cluster_ci, wpr
from e33_map10m import CHUNK, D, TEST_DIVS
from zones import zone as zone_of

GT = ROOT / "ground_truth"
TILES = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
CACHE = {}


def chunk(tile, r, c):
    k = (tile, r, c)
    if k not in CACHE:
        f = D / f"{tile}_{r:05d}_{c:05d}.npz"
        CACHE[k] = dict(np.load(f)) if f.exists() else None
    return CACHE[k]


def sample(x, y, box=2):
    """Max class flag and modal year in a 50 m box around (x, y). Returns (seen, cls, yr)."""
    hits, seen, ys = [], False, []
    for dx in range(-box, box + 1):
        for dy in range(-box, box + 1):
            X, Y = x + dx * 10, y + dy * 10
            for s in TILES.itertuples():
                if s.x0 <= X < s.x0 + s.w * RES and s.y1 - s.h * RES < Y <= s.y1:
                    col, row = int((X - s.x0) / 10), int((s.y1 - Y) / 10)
                    a = chunk(s.tile, row // CHUNK * CHUNK, col // CHUNK * CHUNK)
                    if a is not None:
                        seen = True
                        v = a["cls"][row % CHUNK, col % CHUNK]
                        if v:
                            hits.append(int(v))
                            ys.append(int(a["yr"][row % CHUNK, col % CHUNK]))
                    break
    if not hits:
        return seen, 0, 0
    order = {1: 0, 2: 1, 3: 2}
    return seen, min(hits, key=lambda v: order[v]), max(set(ys), key=ys.count) + 2000


def main():
    g = pd.read_csv(GT / "guna_labels.csv")
    r = [sample(a, b) for a, b in zip(g.x, g.y)]
    g["seen"], g["c"], g["yr"] = [a[0] for a in r], [a[1] for a in r], [a[2] for a in r]
    ref = g[(g.source == "blind_reference") & g.seen].copy()
    n = ref.stratum.value_counts()
    ref["_w"] = ref.stratum.map(lambda s: A_H[s] / n[s])
    for name, m in (("all classes", ref.c > 0), ("clearing + tree-to-shrub (no shrub-to-crop path)", ref.c.isin([1, 2])), ("clearing only", ref.c == 1)):
        ref["m"] = m.astype(int).values
        p, rc = wpr(ref.label.values, ref.m.values, ref._w.values)
        ci = cluster_ci(ref, "m")
        print(f"Guna reference, 10 m map, {name:50s} n {len(ref)} P {p:.2f} {ci[0]} R {rc:.2f} {ci[1]}", flush=True)
    print("flagged", pd.crosstab(ref.label, ref.c).to_string())
    f = g[(g.source == "felling_alert_verdict") & g.seen]
    print("felling judged real, flagged:", int((f[f.label == 1].c > 0).sum()), "of", int((f.label == 1).sum()), "; judged false, flagged:", int((f[f.label == 0].c > 0).sum()), "of", int((f.label == 0).sum()))
    y = f[(f.label == 1) & (f.c > 0) & f.year.notna()]
    print("felling year within 1 of the recorded year:", int((np.abs(y.yr - y.year) <= 1).sum()), "of", len(y), "; exact", int((y.yr == y.year).sum()))
    bm = g[(g.source == "bamori_validated") & g.seen]
    print("Bamori polygons:", bm.groupby("cls").c.agg(lambda s: f"{int((s > 0).sum())}/{len(s)}").to_dict())
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id")
    r = [sample(a, b) for a, b in zip(k.x, k.y)]
    k["seen"], k["c"] = [a[0] for a in r], [a[1] for a in r]
    k["forest_zone"] = k.Division.map(zone_of)
    print("round-2 points inside fetched chunks", int(k.seen.sum()), "of", len(k), k[k.seen].forest_zone.value_counts().to_dict(), "; real", int(k[k.seen].label.isin(list("LD")).sum()))
    if k.seen.sum() == len(k):
        area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
        k["real"] = k.label.isin(list("LD")).astype(int)
        k["_w"] = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
        k["m"] = (k.c > 0).astype(int)
        for gn, q in [("ALL", k), ("deciduous", k[k.forest_zone.isin(["teak_belt", "mixed_dry_deciduous"])])] + list(k.groupby("forest_zone")):
            p, rc, _ = metrics(q.real.values, q.m.values, q._w.values)
            lo, hi = boot(q, area, "real", "m")
            print(f"round 2 {gn:24s} P {p:.2f} [{lo[0]:.2f},{hi[0]:.2f}] R {rc:.2f} [{lo[1]:.2f},{hi[1]:.2f}] ha {float((q.m * q._w).sum()):8.0f}", flush=True)
    else:
        q = k[k.seen & (k.c > 0)]
        print("round-2 flagged in fetched area, labels (not area-weighted):", q.label.value_counts().to_dict())


if __name__ == "__main__":
    main()
