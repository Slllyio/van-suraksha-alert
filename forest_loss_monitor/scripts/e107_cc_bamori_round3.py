"""Tighter Bamori area estimate. The three sampling groups are split into finer strata with layers that use no labels: the 2017-18 cropland mask (already fields, so no forest to lose)
and whether the stage-1 net fired. Earlier blind spots fall into the finer strata by position (each was a random pixel or a random patch pixel of its group, so it stays a valid sample
of its sub-stratum). A third round adds spots by Neyman allocation, most where area x uncertainty is largest. Usage: e107_cc_bamori_round3.py plan | sample | fetch | sheets | estimate"""
import json
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd

import e93_cc_strips as st
from common import *
from e97_cc_map import D
from e106_cc_bamori_round2 import strata as base_strata

GT = ROOT / "ground_truth"
KEY = GT / "bamori_round3_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
SEED, N_NEW = 20261113, 120
st.KEY, st.CH, st.SH = KEY, WORK / "bamori_round3_strips", OUT / "bamori_round3_sheets"


def layers():
    g = json.load(open(D / "grid.json"))
    final, rem, rest = base_strata()
    C = np.full(final.shape, np.nan, "float32")
    for f in (WORK / "cc_map_bamori_crop").glob("*.npy"):
        i, j = map(int, f.stem.split("_"))
        a = np.load(f)
        C[i:i + a.shape[0], j:j + a.shape[1]] = a
    crop = C >= .5
    net = np.load(WORK / "cc_map_bamori_cls.npy") >= 1
    S = {"1 final map": final,
         "2 sieve-removed, not cropland before": rem & ~crop,
         "3 sieve-removed, already cropland": rem & crop,
         "4 unflagged, net fired, not cropland before": rest & net & ~crop,
         "5 unflagged, net fired, already cropland": rest & net & crop,
         "6 unflagged, net quiet, not cropland before": rest & ~net & ~crop,
         "7 unflagged, net quiet, already cropland": rest & ~net & crop}
    return g, S


def labelled(g, S):
    """All earlier blind spots with their fine stratum."""
    a = pd.read_csv(GT / "bamori_map_labelled.csv")[["x", "y_m", "label"]].assign(round=1)
    b = pd.read_csv(GT / "bamori_round2_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(GT / "bamori_round2_labels.csv"), on="code")[["x", "y_m", "label"]].assign(round=2)
    parts = [a, b]
    if (GT / "bamori_round3_labels.csv").exists():
        parts.append(pd.read_csv(KEY).merge(pd.read_csv(GT / "bamori_round3_labels.csv"), on="code")[["x", "y_m", "label"]].assign(round=3))
    s = pd.concat(parts, ignore_index=True)
    r, c = ((g["y1"] - s.y_m) / 10).astype(int), ((s.x - g["x0"]) / 10).astype(int)
    s["stratum"] = ""
    for nm, m in S.items():
        s.loc[m[r, c], "stratum"] = nm
    s["real"] = s.label.isin(["C", "T"])
    return s[s.stratum != ""]


def table(g, S):
    s = labelled(g, S)
    rows = []
    for nm, m in S.items():
        q = s[s.stratum == nm]
        n, x = len(q), int(q.real.sum())
        p = (x + .5) / (n + 1)                      # smoothed, for planning and for the variance when x is 0
        rows.append(dict(stratum=nm, area_ha=m.sum() * .01, n=n, real=x, p=x / n if n else np.nan, p_plan=p))
    return pd.DataFrame(rows)


def plan():
    g, S = layers()
    t = table(g, S)
    t["weight"] = t.area_ha * np.sqrt(t.p_plan * (1 - t.p_plan))
    t["new"] = np.maximum(np.round(N_NEW * t.weight / t.weight.sum()).astype(int), 4)
    print(t.round(3).to_string())
    return g, S, t


def sample():
    g, S, t = plan()
    rng = np.random.default_rng(SEED)
    pts = []
    for nm, n in zip(t.stratum, t.new):
        rr, cc = np.nonzero(S[nm])
        i = rng.choice(len(rr), int(n), replace=False)
        pts += [dict(group=nm, x=g["x0"] + (c + .5) * 10, y_m=g["y1"] - (r + .5) * 10) for r, c in zip(rr[i], cc[i])]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 920000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(len(k), k.group.value_counts().sort_index().to_dict())


def estimate():
    g, S = layers()
    t = table(g, S)
    t["est_ha"] = t.area_ha * t.p
    pv = np.where(t.real.isin([0]) | (t.real == t.n), t.p_plan, t.p)
    t["se_ha"] = t.area_ha * np.sqrt(pv * (1 - pv) / t.n)
    tot, se = t.est_ha.sum(), np.sqrt((t.se_ha ** 2).sum())
    pd.set_option("display.width", 220)
    print(t.round(3).to_string())
    print(f"total {tot:.0f} ha, 95% range {tot - 1.96 * se:.0f} - {tot + 1.96 * se:.0f} ({100 * tot / t.area_ha.sum():.1f}% of recorded forest), spots {int(t.n.sum())}")
    w = t[t.stratum.str.contains("not cropland") | t.stratum.str.startswith("1")]
    print("of which outside land already cropland:", round(w.est_ha.sum()), "ha")
    t.round(3).to_csv(OUT / "guna_bamori_map" / "bamori_area_estimate_fine.csv", index=False)


if __name__ == "__main__":
    dict(plan=plan, sample=sample, fetch=lambda: st.fetch(2), sheets=st.sheets, estimate=estimate)[sys.argv[1]]()
