"""Retrain on the owner's Guna labels. Reports separately: held-out Guna beats (owner labels, area-weighted, two-fold by beat) and round-2 points
(my labels, Olofsson weights, never used in training). The operating threshold always comes from the training side."""
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import *
from e14_accuracy import boot, metrics
from e15_stage2 import F as OLD, attach, design
from e23_guna_labels import A_H, wpr
from zones import zone as zone_of

GT = ROOT / "ground_truth"


def model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.03, max_iter=4000, class_weight="balanced"))


def owner_points():
    """Owner labels with embeddings: known year where recorded, else the year of top model score."""
    f = GT / "owner_features.parquet"
    if f.exists():
        return pd.read_parquet(f)
    s = pd.read_csv(GT / "guna_scores_v3.csv")
    keep = s.source.isin(["blind_reference", "felling_alert_verdict"]) | ((s.source == "bamori_validated") & s.cls.isin(["forest_to_crop", "forest_to_bare", "shrub_to_crop"]))
    s = s[keep].reset_index(drop=True)
    b = pd.DataFrame(dict(sample_id=s.gid, x=s.x, y=s.y, map_year=np.where(s.year.between(2018, 2025), s.year, s.yod).astype(int), label=s.label.map({1: "L", 0: "N"}),
                          owner_y=s.label, source=s.source, stratum=s.stratum, beat=s.beat))
    out = attach(b)
    out.to_parquet(f)
    return out


def round2():
    f = GT / "round2_features.parquet"
    if f.exists():
        return pd.read_parquet(f)
    k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id")
    z = pd.read_csv(OUT / "timeseries" / "dw_gate_flags.csv")
    z = z[z["round"] == 2].assign(sample_id=lambda d: d.sample_id - 200000)
    k = k.merge(z[["sample_id", "yr"]], on="sample_id")
    out = attach(k.assign(map_year=k.yr.astype(int))[["sample_id", "x", "y", "map_year", "label", "stratum", "Division"]])
    out.to_parquet(f)
    return out


def threshold(y, s):
    P, R, T = precision_recall_curve(y, s)
    f = 2 * P * R / (P + R + 1e-9)
    return T[min(int(np.argmax(f)), len(T) - 1)]


def ref_score(d, score, thr):
    n = d.stratum.value_counts()
    w = d.stratum.map(lambda s: A_H[s] / n[s]).values
    return wpr(d.owner_y.values, (score >= thr).astype(int), w)


def main():
    bak = OLD.read_bytes()
    try:
        ow, r2 = owner_points(), round2()
    finally:
        OLD.write_bytes(bak)    # attach() rewrites this cache path
    old = pd.read_parquet(OLD)
    old_y = old.label.isin(list("LD")).astype(int).values
    Xold = design(old, "change")
    Xo, yo = design(ow, "change"), ow.owner_y.values
    ref = ow[ow.source == "blind_reference"].reset_index(drop=True)
    print("owner points with embeddings", len(ow), ow.groupby(["source", "owner_y"]).size().to_dict())
    beats = np.sort(ref.beat.unique())
    np.random.default_rng(42).shuffle(beats)
    fold_a = set(beats[: len(beats) // 2])
    sets = {"my labels only": "old", "owner only": "owner", "both": "both"}
    res = []
    for name, which in sets.items():
        ss = np.zeros(len(ref))
        folds = []
        for hold in (fold_a, set(beats) - fold_a):
            tr = ~ow.beat.isin(hold).values       # no owner point from a held-out beat trains the model
            X = {"old": Xold, "owner": Xo[tr], "both": np.vstack([Xo[tr], Xold])}[which]
            y = {"old": old_y, "owner": yo[tr], "both": np.r_[yo[tr], old_y]}[which]
            m = model().fit(X, y)
            t = threshold(y, m.decision_function(X))
            te = ref.beat.isin(hold).values
            sc = m.decision_function(design(ref[te], "change"))
            p, r = ref_score(ref[te], sc, t)
            folds.append((round(p, 2), round(r, 2), int(te.sum()), int(ref[te].owner_y.sum())))
            ss[te] = sc - t
        p, r = ref_score(ref, ss, 0)
        print(f"Guna held-out beats | train: {name:16s} P {p:.2f} R {r:.2f} folds {folds}", flush=True)
        res.append(dict(test="guna_heldout_beats", train=name, precision=round(p, 3), recall=round(r, 3)))
    area = json.load(open(OUT / "validation2" / "strata_area_ha.json"))
    r2["real"] = r2.label.isin(list("LD")).astype(int)
    r2["_w"] = r2.stratum.map(area) / r2.stratum.map(r2.stratum.value_counts())
    r2["forest_zone"] = r2.Division.map(zone_of)
    X2 = design(r2, "change")
    for name, which in sets.items():
        X = {"old": Xold, "owner": Xo, "both": np.vstack([Xo, Xold])}[which]
        y = {"old": old_y, "owner": yo, "both": np.r_[yo, old_y]}[which]
        m = model().fit(X, y)
        t = threshold(y, m.decision_function(X))
        r2["m"] = (m.decision_function(X2) >= t).astype(int)
        for g, q in [("ALL", r2), ("deciduous", r2[r2.forest_zone.isin(["teak_belt", "mixed_dry_deciduous"])])] + list(r2.groupby("forest_zone")):
            p, rc, f = metrics(q.real.values, q.m.values, q._w.values)
            lo, hi = boot(q, area, "real", "m") if q.real.sum() else ((np.nan,) * 3, (np.nan,) * 3)
            ha = float((q.m * q._w).sum())
            print(f"Round 2 | train: {name:16s} {g:22s} n {len(q):3d} real {int(q.real.sum()):2d} P {p:.2f} [{lo[0]:.2f},{hi[0]:.2f}] R {rc:.2f} [{lo[1]:.2f},{hi[1]:.2f}] flagged_ha {ha:9.0f}", flush=True)
            res.append(dict(test=f"round2 {g}", train=name, precision=round(p, 3), recall=round(rc, 3), flagged_ha=round(ha)))
    pd.DataFrame(res).to_csv(GT / "retrain_with_owner_labels.csv", index=False)


if __name__ == "__main__":
    main()
