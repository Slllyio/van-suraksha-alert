"""Conversion test for open land turning to farms, which the tree-based rule cannot see. Signal: rabi (Jan-Mar) greenness well above the dry-season
(Apr-May) floor appears after the baseline. Thresholds set on half the beats, tested on the other half, then on round-2 points.
Usage: e39_conversion.py points | score"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from common import *
from e14_accuracy import metrics
from e23_guna_labels import A_H, wpr
from e32_enetra10m import S2
from zones import zone as zone_of

GT = ROOT / "ground_truth"
F = GT / "conversion_points.csv"
YS = list(range(2018, 2026))


def ndvi(aoi, y, m0, m1):
    def nd(i):
        s = i.select("SCL")
        bad = s.eq(1).Or(s.eq(3)).Or(s.eq(8)).Or(s.eq(9)).Or(s.eq(10))
        return i.updateMask(bad.Not()).normalizedDifference(["B8", "B4"]).rename("n").toFloat()
    return ee.ImageCollection(S2).filterBounds(aoi).filterDate(ee.Date.fromYMD(y, m0, 1), ee.Date.fromYMD(y, m1, 1).advance(1, "month")).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(nd).median()


def run(part):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y], p), dict(pid=int(i))) for x, y, i in zip(part.x, part.y, part.pid)])
    a = fc.geometry().bounds(100, "EPSG:4326")
    bands = []
    for y in YS:
        bands += [ndvi(a, y, 1, 3).rename(f"r{y}"), ndvi(a, y, 4, 5).rename(f"d{y}")]
    for _ in range(4):
        try:
            return [f["properties"] for f in ee.Image.cat(bands).reduceRegions(fc, ee.Reducer.first(), crs=WKT, scale=10, tileScale=8).getInfo()["features"]]
        except Exception as e:
            msg = str(e)[:160]
    print("failed", msg, flush=True)
    return []


def points():
    init()
    g = pd.read_csv(GT / "guna_labels.csv")
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
    d = pd.concat([pd.DataFrame(dict(pid=g.gid + 500000, x=g.x, y=g.y)), pd.DataFrame(dict(pid=k.sample_id + 200000, x=k.x, y=k.y))], ignore_index=True)
    d = d.assign(ry=(d.y // 45000).astype(int), rx=(d.x // 45000).astype(int)).sort_values(["ry", "rx"])
    rows = []
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(run, [d.iloc[i:i + 15] for i in range(0, len(d), 15)]):
            rows += r
            pd.DataFrame(rows).to_csv(F, index=False)
            print(len(rows), flush=True)
    print("FINISHED")


def feats(t):
    """Rise in the rabi cycle: (rabi - dry floor), later years against early years."""
    amp = pd.DataFrame({y: t[f"r{y}"] - t[f"d{y}"] for y in YS if f"r{y}" in t})
    early, late = amp[[2018, 2019]].mean(axis=1), amp[[2022, 2023, 2024]].mean(axis=1)
    r_e = t[["r2018", "r2019"]].mean(axis=1)
    r_l = t[["r2022", "r2023", "r2024"]].mean(axis=1)
    return pd.DataFrame(dict(amp_rise=late - early, amp_late=late, rabi_rise=r_l - r_e, rabi_late=r_l, rabi_early=r_e))


def score():
    t = pd.read_csv(F)
    x = pd.concat([t[["pid"]], feats(t)], axis=1)
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000).merge(x, on="pid")
    pos = g[(g.source == "bamori_validated") & g.cls.isin(["forest_to_crop", "shrub_to_crop", "bare_to_crop", "forest_to_bare"])]
    neg = g[(g.source == "blind_reference") & (g.label == 0)]
    d = pd.concat([pos.assign(y_=1), neg.assign(y_=0)]).dropna(subset=["amp_rise", "rabi_rise"])
    print("positives", int(d.y_.sum()), "negatives", int((1 - d.y_).sum()))
    for c in ("amp_rise", "amp_late", "rabi_rise", "rabi_late", "rabi_early"):
        print(c, "AUC", round(roc_auc_score(d.y_, d[c]), 3), "AP", round(average_precision_score(d.y_, d[c]), 3), "median pos/neg", round(d[d.y_ == 1][c].median(), 3), round(d[d.y_ == 0][c].median(), 3))
    # note: positives and negatives are not in natural proportion, so AP depends on the mix; thresholds are picked on half the beats
    rng = np.random.default_rng(3)
    beats = d.beat.dropna().unique()
    rng.shuffle(beats)
    a, b = d[d.beat.isin(beats[: len(beats) // 2])], d[d.beat.isin(beats[len(beats) // 2:])]
    best = None
    for rr in (.05, .08, .1, .12, .15, .2, .25):
        for rl in (.3, .35, .4, .45, .5):
            m = (a.rabi_rise >= rr) & (a.rabi_late >= rl)
            tp = (m & (a.y_ == 1)).sum()
            p, r = tp / max(m.sum(), 1), tp / max(a.y_.sum(), 1)
            f = 2 * p * r / (p + r + 1e-9)
            if best is None or f > best[0]:
                best = (f, rr, rl)
    _, rr, rl = best
    m = (b.rabi_rise >= rr) & (b.rabi_late >= rl)
    print("rule from half the beats: rabi rise >=", rr, "and late rabi >=", rl, "| other half: polygons caught", int((m & (b.y_ == 1)).sum()), "of", int(b.y_.sum()), "; no-loss points flagged", int((m & (b.y_ == 0)).sum()), "of", int((b.y_ == 0).sum()))
    r = g[g.source == "blind_reference"].dropna(subset=["rabi_rise"]).copy()
    n = r.stratum.value_counts()
    r["_w"] = r.stratum.map(lambda s: A_H[s] / n[s])
    r["m"] = ((r.rabi_rise >= rr) & (r.rabi_late >= rl)).astype(int)
    p_, r_ = wpr(r.label.values, r.m.values, r._w.values)
    print("on the owner's reference, this signal alone: precision", round(p_, 2), "recall", round(r_, 2), "flagged", int(r.m.sum()), "of", len(r), "real among flagged", int((r.m & r.label).sum()))
    print("share of no-loss reference points flagged", round(float(r[r.label == 0].m.mean()), 3), "; these weigh", round(float((r._w * (r.label == 0) * r.m).sum())), "of", round(float(r._w.sum())), "weighted ha")
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id")
    k = k.assign(pid=k.sample_id + 200000).merge(x, on="pid").dropna(subset=["rabi_rise"])
    k["m"] = ((k.rabi_rise >= rr) & (k.rabi_late >= rl)).astype(int)
    print("round 2 flagged by stratum", pd.crosstab(k.stratum, k.m).to_string())
    print("labels of flagged", k[k.m == 1].label.value_counts().to_dict())
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    w = k.stratum.map(area) / k.stratum.map(k.stratum.value_counts())
    print("round-2 area flagged if used statewide, ha", round(float((k.m * w).sum())))


if __name__ == "__main__":
    {"points": points, "score": score}[sys.argv[1]]()
