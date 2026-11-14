"""Second blind sample for the Bamori area estimate: 60 random pixels in the area the sieve removed and 20 in the rest of recorded forest, drawn with equal chance per pixel so they
scale to area directly. Strips and sheets via e93; then a stratified estimate combining both rounds. Usage: e106_cc_bamori_round2.py sample | fetch | sheets | estimate"""
import json
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd
from scipy.ndimage import label

import e93_cc_strips as st
from common import *
from e97_cc_map import D

GT = ROOT / "ground_truth"
KEY = GT / "bamori_round2_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
SEED = 20261112
st.KEY, st.CH, st.SH = KEY, WORK / "bamori_round2_strips", OUT / "bamori_round2_sheets"


def strata():
    final, ok, cls = np.load(WORK / "cc_map_bamori_final.npy"), np.load(WORK / "cc_map_bamori_ok.npy"), np.load(WORK / "cc_map_bamori_cls.npy")
    rem = (cls == 2) & ~final
    lab, _ = label(rem, structure=np.ones((3, 3)))
    size = np.bincount(lab.ravel())
    rem = np.isin(lab, np.flatnonzero(size >= 50)) & (lab > 0)
    return final, rem, ok & ~final & ~rem


def sample():
    g = json.load(open(D / "grid.json"))
    _, rem, rest = strata()
    rng = np.random.default_rng(SEED)
    pts = []
    for nm, m, n in (("removed by sieve", rem, 60), ("not flagged", rest, 20)):
        rr, cc = np.nonzero(m)
        i = rng.choice(len(rr), n, replace=False)
        pts += [dict(group=nm, x=g["x0"] + (c + .5) * 10, y_m=g["y1"] - (r + .5) * 10) for r, c in zip(rr[i], cc[i])]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 910000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(k.group.value_counts().to_dict())


def estimate():
    from statsmodels.stats.proportion import proportion_confint
    final, rem, rest = strata()
    A = {"final map": final.sum() * .01, "removed by sieve": rem.sum() * .01, "not flagged": rest.sum() * .01}
    a = pd.read_csv(GT / "bamori_map_labelled.csv")[["group", "label"]]
    b = pd.read_csv(KEY).merge(pd.read_csv(GT / "bamori_round2_labels.csv"), on="code")[["group", "label"]]
    s = pd.concat([a.assign(round=1), b.assign(round=2)])
    s["real"] = s.label.isin(["C", "T"])
    rows, tot, var = [], 0., 0.
    for grp, area in A.items():
        q = s[s.group == grp]
        n, x = len(q), int(q.real.sum())
        p = x / n
        lo, hi = proportion_confint(x, n, method="wilson")
        tot += area * p
        var += area ** 2 * max(p * (1 - p), 1 / n ** 2) / n
        rows.append(dict(stratum=grp, area_ha=round(area), spots=n, real_loss=x, share=round(p, 3), est_ha=round(area * p), range_ha=f"{round(area * lo)}-{round(area * hi)}"))
    t = pd.DataFrame(rows)
    print(t.to_string())
    se = var ** .5
    print("total", round(tot), "ha, 95% range", round(max(tot - 1.96 * se, 0)), "-", round(tot + 1.96 * se), "| share of recorded forest", round(100 * tot / sum(A.values()), 1), "%")
    print("round 2 labels by group:", pd.crosstab(b.group, b.label).to_dict("index"))
    t.to_csv(OUT / "guna_bamori_map" / "bamori_area_estimate.csv", index=False)


if __name__ == "__main__":
    dict(sample=sample, fetch=lambda: st.fetch(2), sheets=st.sheets, estimate=estimate)[sys.argv[1]]()
