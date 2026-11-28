"""Time-series sweep of pixels mapped as stable: is loss hiding in there? Strata: forest edge (within ~300 m of low tree cover, covering
farm edges, roads, settlements), near mapped change (within ~1 km, covering mine and coupe fringes), and interior forest as a control.
Water and all mapped pixels excluded. Usage: e20_sweep.py sample | review"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy import ndimage

from calibrate_sample import sheets
from chips import make_chips
from common import *
from e19_ts_eval import breaks

D = OUT / "timeseries"
SEED = 20261105
PER = 150
T = 0.20               # CCDC-alone threshold from round 1, unchanged
LOW_TREE = 3000


def sample():
    c = np.load(WORK / "classified.npz")
    cls = c["cls"]
    water = np.load(WORK / "water.npy")
    g = json.load(open(WORK / "grid.json"))
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zone = s.read(1)
    tree = np.zeros(zone.shape, "int16")
    for s in pd.read_csv(WORK / "tiles.csv", keep_default_na=False).itertuples():
        with rasterio.open(WORK / "emb_v3" / f"{s.tile}.tif") as src:
            tree[s.row:s.row + s.h, s.col:s.col + s.w] = src.read(list(src.descriptions).index("tree2017") + 1)
    ok = (zone > 0) & ~water & (cls == 0) & (tree >= LOW_TREE)
    # distance in pixels; a coarse EDT would do, but the state grid fits in memory
    low = (tree < LOW_TREE)
    edge = ok & ndimage.binary_dilation(low, iterations=10)
    near = ok & ndimage.binary_dilation((cls == 1) | (cls == 2), iterations=33) & ~edge
    inner = ok & ~edge & ~near
    rng = np.random.default_rng(SEED)
    rows, area = [], {}
    for name, m in (("edge_300m", edge), ("near_mapped_1km", near), ("interior", inner)):
        ii = np.flatnonzero(m.ravel())
        area[name] = float(len(ii) * PX_HA)
        for p in rng.choice(ii, PER, replace=False):
            r, col = np.unravel_index(p, zone.shape)
            rows.append(dict(stratum=name, row=int(r), col=int(col), x=g["x0"] + (col + .5) * RES, y=g["y1"] - (r + .5) * RES, zone_id=int(zone[r, col])))
    d = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    d.insert(0, "sample_id", np.arange(300001, 300001 + len(d)))
    d.to_csv(D / "sweep_points.csv", index=False)
    json.dump(area, open(D / "sweep_strata_area_ha.json", "w"), indent=1)
    print(area, len(d))


def review():
    d = pd.read_csv(D / "sweep_points.csv")
    rows = []
    for line in open(D / "ccdc_sweep.jsonl"):
        p = json.loads(line)
        ok = [x for x in breaks(p) if x["dur"] >= 1]
        best = max(ok, key=lambda x: min(x["leaf"], x["mean"]), default=None)
        rows.append(dict(sample_id=p["sample_id"], size=min(best["leaf"], best["mean"]) if best else 0.0, year=best["year"] if best else 0))
    d = d.merge(pd.DataFrame(rows), on="sample_id", how="left")
    d["flag"] = d["size"] >= T
    print(d.groupby("stratum").flag.agg(["size", "sum", "mean"]).round(3).to_string())
    rng = np.random.default_rng(SEED)
    picks = [d[d.flag]]
    for st, g in d[~d.flag].groupby("stratum"):
        picks.append(g.iloc[rng.choice(len(g), 15, replace=False)])
    k = pd.concat(picks).sample(frac=1, random_state=SEED).reset_index(drop=True)
    k["chip_id"] = np.arange(1, len(k) + 1)
    out = D / "sweep_review"
    out.mkdir(exist_ok=True)
    k.to_csv(out / "key.csv", index=False)
    chips = k.assign(sample_id=k.chip_id, map_year=-1)
    init()
    make_chips(chips, out / "chips")
    sheets(chips, out)
    print("to view", len(k))


if __name__ == "__main__":
    {"sample": sample, "review": review}[sys.argv[1]]()
