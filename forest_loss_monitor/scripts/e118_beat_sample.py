"""Beat-level blind sample of the MP new-farmland map (e115), three tiers: beats with >= 20 ha mapped get 25 spots, 5-20 ha get 6, under 5 ha none (range precision only).
Spots are random flagged pixels of the beat, coded only; the key stays unopened until labels are saved. Estimates: beat precision shrunk toward its range (empirical Bayes), area = map x precision.
Usage: e118_beat_sample.py <Division> sample | fetch | sheets | estimate"""
import sys

sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
DIV, CMD = sys.argv[1], sys.argv[2]
sys.argv = sys.argv[:1]

import numpy as np
import pandas as pd
import rasterio

import e93_cc_strips as st
from common import *

GT = ROOT / "ground_truth"
KEY = GT / f"beat_blind_{DIV}_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
LAB = GT / f"beat_blind_{DIV}_labels.csv"
MPD = OUT / "mp_newfarm"
TIERS = ((20, 25), (5, 6))            # (min mapped ha, spots per beat)
SEED = 20261108
st.KEY, st.CH, st.SH = KEY, WORK / f"beat_blind_{DIV}_strips", OUT / f"beat_blind_{DIV}_sheets"


def beat_raster():
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    lk = lk[lk.Division == DIV].set_index("zone_id")
    with rasterio.open(MPD / f"newfarm_{DIV}.tif") as s:
        first, tr = s.read(1), s.transform
    with rasterio.open(WORK / "zone_beat.tif") as s:
        z = s.read(1, window=s.window(tr.c, tr.f + tr.e * first.shape[0], tr.c + tr.a * first.shape[1], tr.f), boundless=True, fill_value=0)[:first.shape[0], :first.shape[1]]
    return lk, first, tr, z


def sample():
    lk, first, tr, z = beat_raster()
    rr, cc = np.nonzero(first > 0)
    zz = z[rr, cc]
    ha = pd.Series(zz).value_counts() * .09
    rng = np.random.default_rng(SEED)
    pts = []
    for zid, h in ha.items():
        if zid not in lk.index:
            continue
        n = next((k for lo, k in TIERS if h >= lo), 0)
        if not n:
            continue
        i = rng.choice(np.flatnonzero(zz == zid), min(n, int((zz == zid).sum())), replace=False)
        pts += [dict(group=lk.Range[zid], zone_id=int(zid), beat=lk.Beat[zid], x=tr.c + (cc[k] + .5) * tr.a, y_m=tr.f + (rr[k] + .5) * tr.e, first=int(first[rr[k], cc[k]])) for k in i]
    k = pd.DataFrame(pts)
    k["code"] = rng.permutation(len(k)) + 1
    k["cid"] = 950000 + k.code
    k.sort_values("code").to_csv(KEY, index=False)
    print(len(k), "spots,", k.zone_id.nunique(), "beats,", k.group.nunique(), "ranges")


def estimate():
    k = pd.read_csv(KEY).merge(pd.read_csv(LAB), on="code")
    k["w"] = (k.label == "F") + .5 * (k.label == "U")
    lk, first, tr, z = beat_raster()
    ha = (pd.Series(z[first > 0]).value_counts() * .09).rename("map_ha")
    b = k.groupby(["group", "zone_id", "beat"]).agg(n=("w", "size"), x=("w", "sum")).reset_index()
    r = b.groupby("group").agg(n=("n", "sum"), x=("x", "sum"))
    r["p"] = r.x / r.n
    # between-beat spread within range, method of moments, floored at 0.10 (what the range checks showed)
    b["p_raw"] = b.x / b.n
    tau2 = max(0.10 ** 2, float(np.nanmean(b.groupby("group").apply(lambda g: g.p_raw.var() - (g.p_raw * (1 - g.p_raw) / g.n).mean() if len(g) > 1 else np.nan))))
    pr = b.group.map(r.p)
    v = (pr * (1 - pr) / b.n).clip(lower=.004)
    shrink = tau2 / (tau2 + v)
    b["p"] = pr + shrink * (b.p_raw - pr)
    b["se"] = np.sqrt(shrink * v)
    b["grade"] = np.where(b.n >= 25, "A", "B")
    allb = pd.DataFrame(dict(zone_id=ha.index)).merge(lk[["Range", "Beat"]], left_on="zone_id", right_index=True).rename(columns={"Range": "group", "Beat": "beat"})
    t = allb.merge(b[["zone_id", "n", "p", "se", "grade"]], on="zone_id", how="left")
    t["map_ha"] = t.zone_id.map(ha)
    miss = t.p.isna()
    t.loc[miss, "p"] = t.loc[miss, "group"].map(r.p)
    t.loc[miss, "se"] = t.loc[miss, "group"].map(lambda g: np.sqrt(r.p[g] * (1 - r.p[g]) / r.n[g]) if g in r.index else np.nan)
    t.loc[miss, "grade"] = "C"
    t["n"] = t.n.fillna(0).astype(int)
    t["est_ha"] = t.map_ha * t.p
    t["se_ha"] = t.map_ha * t.se
    t["lo_ha"], t["hi_ha"] = (t.est_ha - 1.96 * t.se_ha).clip(lower=0), t.est_ha + 1.96 * t.se_ha
    t = t.sort_values("est_ha", ascending=False)
    t.round(3).to_csv(MPD / f"{DIV}_beat_estimate.csv", index=False)
    rt = t.groupby("group").agg(beats=("zone_id", "size"), sampled=("n", lambda s: (s > 0).sum()), spots=("n", "sum"), map_ha=("map_ha", "sum"), est_ha=("est_ha", "sum"), se_ha=("se_ha", lambda s: np.sqrt((s ** 2).sum())))
    rt.loc["ALL"] = [rt.beats.sum(), rt.sampled.sum(), rt.spots.sum(), rt.map_ha.sum(), rt.est_ha.sum(), np.sqrt((rt.se_ha ** 2).sum())]
    rt.round(1).to_csv(MPD / f"{DIV}_beat_estimate_by_range.csv")
    pd.set_option("display.width", 200)
    print("between-beat sd used:", round(np.sqrt(tau2), 2))
    print(rt.round(0).to_string())
    print(t.head(12)[["group", "beat", "map_ha", "n", "p", "est_ha", "lo_ha", "hi_ha", "grade"]].round(1).to_string(index=False))


if __name__ == "__main__":
    dict(sample=sample, fetch=lambda: st.fetch(1), sheets=st.sheets, estimate=estimate)[CMD]()
