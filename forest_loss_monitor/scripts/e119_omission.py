"""Omission sample for one MP division: random pixels in recorded forest that the new-farmland map (e115) does NOT flag, to measure the new farmland the map misses.
Same blind strips and labels as e116/e118 (F new field, U unclear counted half, A already a field, C cleared no crop, N no field). Missed area = unflagged forest x share of F (+ half U).
Usage: e119_omission.py <Division> sample [n] | fetch | sheets | estimate"""
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
DIV, CMD = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 60
sys.argv = sys.argv[:1]

import numpy as np
import pandas as pd
import rasterio

import e93_cc_strips as st
from common import *

GT = ROOT / "ground_truth"
KEY = GT / f"omit_blind_{DIV}_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
LAB = GT / f"omit_blind_{DIV}_labels.csv"
MPD = OUT / "mp_newfarm"
st.KEY, st.CH, st.SH = KEY, WORK / f"omit_blind_{DIV}_strips", OUT / f"omit_blind_{DIV}_sheets"


def forest():
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == DIV].set_index("zone_id")
    with rasterio.open(MPD / f"newfarm_{DIV}.tif") as s:
        first, tr = s.read(1), s.transform
    with rasterio.open(WORK / "zone_beat.tif") as s:
        z = s.read(1, window=s.window(tr.c, tr.f + tr.e * first.shape[0], tr.c + tr.a * first.shape[1], tr.f), boundless=True, fill_value=0)[:first.shape[0], :first.shape[1]]
    return lk, first, tr, z, np.isin(z, lk.index.values) & (first == 0)


def sample():
    lk, first, tr, z, un = forest()
    rr, cc = np.nonzero(un)
    rng = np.random.default_rng(20261108)
    i = rng.choice(len(rr), N, replace=False)
    k = pd.DataFrame([dict(group=lk.Range[z[rr[j], cc[j]]], beat=lk.Beat[z[rr[j], cc[j]]], x=tr.c + (cc[j] + .5) * tr.a, y_m=tr.f + (rr[j] + .5) * tr.e) for j in i])
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 960000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(len(k), "spots in", round(un.sum() * .09), "ha of unflagged forest")


def estimate():
    lk, first, tr, z, un = forest()
    k = pd.read_csv(KEY).merge(pd.read_csv(LAB), on="code")
    w = (k.label == "F") + .5 * (k.label == "U")
    area = un.sum() * .09
    p, n = w.mean(), len(k)
    se = area * np.sqrt(p * (1 - p) / n) if 0 < p < 1 else area * np.sqrt(.5 / (n + 1) * (1 - .5 / (n + 1)) / n)
    r = pd.Series(dict(unflagged_forest_ha=area, n=n, share_new_field=p, missed_ha=area * p, se_ha=se, **{f"label_{c}": int((k.label == c).sum()) for c in "FUACN"}))
    print(r.round(3).to_string())
    r.round(3).to_csv(MPD / f"{DIV}_omission_estimate.csv")


if __name__ == "__main__":
    dict(sample=sample, fetch=lambda: st.fetch(1), sheets=st.sheets, estimate=estimate)[CMD]()
