"""Olofsson et al. 2014 stratified estimators: area-adjusted loss with 95% CI, user's and producer's accuracy.
Reads outputs/accuracy/labels_filled.csv: sample_id + label_change in {clearing, degradation, stable, unusable}.
Run with --selftest to check the estimator on a hand-worked example. Usage: 08_area_estimate.py [--labels file]"""
import json
import sys

import numpy as np
import pandas as pd

from common import OUT

MAP_TO_CLASS = {"clearing": "clearing", "degradation": "degradation", "stable": "stable", "stable_near_loss": "stable"}
CLASSES = ["clearing", "degradation", "stable"]


def estimate(strata_area: dict, sample: pd.DataFrame, classes: list[str]) -> pd.DataFrame:
    """sample has columns stratum, ref. Strata may differ from map classes (stable + stable_near_loss)."""
    A = sum(strata_area.values())
    rows = []
    for c in classes:
        tot, var = 0.0, 0.0
        for h, Ah in strata_area.items():
            s = sample[sample.stratum == h]
            n = len(s)
            if not n:
                raise ValueError(f"no labelled samples in stratum {h}")
            y = (s.ref == c).astype(float)
            tot += Ah * y.mean()
            var += Ah ** 2 * y.var(ddof=1) / n if n > 1 else 0.0
        rows.append(dict(cls=c, area_ha=tot, ci95_ha=1.96 * np.sqrt(var), share=tot / A))
    out = pd.DataFrame(rows)
    # Accuracy from the same design: strata -> map class weights
    ua, pa = [], []
    for c in classes:
        hs = [h for h in strata_area if MAP_TO_CLASS.get(h, h) == c]
        num = sum(strata_area[h] * (sample[sample.stratum == h].ref == c).mean() for h in hs)
        den = sum(strata_area[h] for h in hs)
        ua.append(num / den)
        pa.append(num / out.loc[out.cls == c, "area_ha"].item() if out.loc[out.cls == c, "area_ha"].item() else np.nan)
    out["users_acc"], out["producers_acc"] = ua, pa
    return out


def selftest() -> None:
    area = {"clearing": 100.0, "degradation": 100.0, "stable": 800.0}
    s = pd.DataFrame(dict(stratum=["clearing"] * 10 + ["degradation"] * 10 + ["stable"] * 10,
                          ref=["clearing"] * 8 + ["stable"] * 2 + ["degradation"] * 5 + ["stable"] * 5 + ["stable"] * 9 + ["clearing"]))
    r = estimate(area, s, CLASSES).set_index("cls")
    assert abs(r.area_ha["clearing"] - (100 * .8 + 800 * .1)) < 1e-9        # 160 ha true clearing
    assert abs(r.users_acc["clearing"] - .8) < 1e-9
    assert abs(r.producers_acc["clearing"] - 80 / 160) < 1e-9
    assert abs(r.area_ha.sum() - 1000) < 1e-9
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit()
    d = OUT / "accuracy"
    f = sys.argv[sys.argv.index("--labels") + 1] if "--labels" in sys.argv else d / "labels_filled.csv"
    key = pd.read_csv(d / "sample_key_DO_NOT_OPEN_BEFORE_LABELLING.csv")
    lab = pd.read_csv(f)[["sample_id", "label_change"]].dropna()
    lab = lab[lab.label_change.isin(CLASSES)]
    s = key.merge(lab, on="sample_id").rename(columns=dict(label_change="ref"))
    r = estimate(json.load(open(d / "strata_area_ha.json")), s, CLASSES)
    print("labelled", len(s), "of", len(key))
    print(s.groupby(["stratum", "ref"]).size().unstack(fill_value=0).to_string())
    print(r.round(3).to_string(index=False))
    r.round(3).to_csv(d / "area_estimates.csv", index=False)
