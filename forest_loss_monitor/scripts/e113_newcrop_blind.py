"""Blind check of the Guna new-cropland map (e110) in the six ranges not yet sampled: 40 random flagged pixels per range, as yearly image strips with a random code only.
The key (range, 2015 survey class, first crop year) stays unopened until labels are saved. Usage: e113_newcrop_blind.py sample | fetch | sheets | estimate"""
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")

import numpy as np
import pandas as pd
import rasterio

import e93_cc_strips as st
from common import *

GT = ROOT / "ground_truth"
KEY = GT / "newcrop_blind_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
LAB = GT / "newcrop_blind_labels.csv"
RANGES = ["Aron", "Binaganj", "Maksudangarh", "North_Guna", "Raghogarh", "South_Guna"]
SEED, N = 20261107, 40
st.KEY, st.CH, st.SH = KEY, WORK / "newcrop_blind_strips", OUT / "newcrop_blind_sheets"


def sample():
    rng = np.random.default_rng(SEED)
    pts = []
    for r in RANGES:
        with rasterio.open(OUT / "guna_newcrop" / f"newcrop_{r}.tif") as s:
            first, s15, tr = s.read(1), s.read(2), s.transform
        rr, cc = np.nonzero(first > 0)
        i = rng.choice(len(rr), N, replace=False)
        pts += [dict(group=r, x=tr.c + (c + .5) * 10, y_m=tr.f - (q + .5) * 10, first=int(first[q, c]), s15=int(s15[q, c])) for q, c in zip(rr[i], cc[i])]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 930000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(len(k), "spots written")


def estimate():
    k = pd.read_csv(KEY).merge(pd.read_csv(LAB), on="code")
    area = pd.read_csv(OUT / "guna_newcrop" / "guna_newcrop_by_range.csv", index_col=0)
    k["new_field"] = k.label == "F"
    k["unclear"] = k.label == "U"
    t = k.groupby("group").agg(n=("code", "size"), new_field=("new_field", "sum"), unclear=("unclear", "sum"))
    t["p"] = (t.new_field + .5 * t.unclear) / t.n          # unclear spots (field edges) count half
    t["map_ha"] = area.new_crop_ha.reindex(t.index)
    t["est_ha"] = t.map_ha * t.p
    t["se_ha"] = t.map_ha * np.sqrt(t.p * (1 - t.p) / t.n)
    print(t.round(2).to_string())
    print(k.groupby(["group", "label"]).size().unstack(fill_value=0).to_string())
    t.round(3).to_csv(OUT / "guna_newcrop" / "newcrop_blind_estimate.csv")


if __name__ == "__main__":
    dict(sample=sample, fetch=lambda: st.fetch(2), sheets=st.sheets, estimate=estimate)[sys.argv[1]]()
