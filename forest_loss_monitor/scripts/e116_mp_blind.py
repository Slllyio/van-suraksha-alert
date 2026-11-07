"""Blind check of the 30 m MP new-farmland map (e115) for one division: random flagged pixels, equal numbers per range, shown as yearly image strips with a code only.
The key (range, first farm year) stays unopened until labels are saved. Labels: F new field, U unclear (field edge, counted half), A already a field in 2017, C cleared but no crop, N no field.
Usage: e116_mp_blind.py <Division> sample [per_range] | fetch | sheets | estimate"""
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
DIV, CMD = sys.argv[1], sys.argv[2]
PER = int(sys.argv[3]) if len(sys.argv) > 3 else 10
sys.argv = sys.argv[:1]

import numpy as np
import pandas as pd
import rasterio

import e93_cc_strips as st
from common import *

GT = ROOT / "ground_truth"
KEY = GT / f"mp_blind_{DIV}_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
LAB = GT / f"mp_blind_{DIV}_labels.csv"
MPD = OUT / "mp_newfarm"
st.KEY, st.CH, st.SH = KEY, WORK / f"mp_blind_{DIV}_strips", OUT / f"mp_blind_{DIV}_sheets"


def sample():
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == DIV].set_index("zone_id")
    with rasterio.open(MPD / f"newfarm_{DIV}.tif") as s:
        first, tr = s.read(1), s.transform
    with rasterio.open(WORK / "zone_beat.tif") as s:
        z = s.read(1, window=s.window(tr.c, tr.f + tr.e * first.shape[0], tr.c + tr.a * first.shape[1], tr.f), boundless=True, fill_value=0)[:first.shape[0], :first.shape[1]]
    rr, cc = np.nonzero(first > 0)
    rng_name = lk.Range.reindex(z[rr, cc]).values
    rng = np.random.default_rng(20261107)
    pts = []
    for r in sorted(pd.unique(rng_name[pd.notna(rng_name)])):
        i = np.flatnonzero(rng_name == r)
        i = rng.choice(i, min(PER, len(i)), replace=False)
        pts += [dict(group=r, x=tr.c + (cc[k] + .5) * tr.a, y_m=tr.f + (rr[k] + .5) * tr.e, first=int(first[rr[k], cc[k]])) for k in i]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 940000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(len(k), "spots,", k.group.nunique(), "ranges")


def estimate():
    k = pd.read_csv(KEY).merge(pd.read_csv(LAB), on="code")
    area = pd.read_csv(MPD / f"{DIV}_newfarm_by_range.csv", index_col=0).new_farmland_ha
    k["w"] = (k.label == "F") + .5 * (k.label == "U")
    t = k.groupby("group").agg(n=("code", "size"), p=("w", "mean"))
    t["map_ha"] = area.reindex(t.index)
    t["est_ha"] = t.map_ha * t.p
    t["se_ha"] = t.map_ha * np.sqrt(t.p * (1 - t.p) / t.n)
    t.loc["ALL"] = [t.n.sum(), t.est_ha.sum() / t.map_ha.sum(), t.map_ha.sum(), t.est_ha.sum(), np.sqrt((t.se_ha ** 2).sum())]
    print(t.round(2).to_string())
    print(k.groupby(["group", "label"]).size().unstack(fill_value=0).to_string())
    t.round(3).to_csv(MPD / f"{DIV}_blind_estimate.csv")


if __name__ == "__main__":
    dict(sample=sample, fetch=lambda: st.fetch(1), sheets=st.sheets, estimate=estimate)[CMD]()
