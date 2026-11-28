"""Stratified random validation sample with before/after chips and a CSV to label.
Strata: clearing, degradation, stable forest, plus a buffer of stable forest next to detections (where omissions hide).
Usage: 07_sample_accuracy.py [--per 100] [--buffer 100] [--stable 200] [--chips]"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage

from common import *
from chips import make_chips

SEED = 20261103


def arg(name, default):
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def draw_strata():
    c = np.load(WORK / "classified.npz")
    yod, cls = c["yod"], c["cls"]
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zone = s.read(1)
    near = ndimage.binary_dilation(cls > 0, iterations=3) & (cls == 0) & (zone > 0)
    strata = np.zeros(yod.shape, "uint8")
    strata[zone > 0] = 3                # stable forest
    strata[near] = 4                    # stable within ~90 m of a detection
    strata[cls == 1] = 1
    strata[cls == 2] = 2
    strata[cls == 3] = 5
    np.save(WORK / "strata.npy", strata)
    return strata, yod, zone


def main():
    per, buf, stable, small = arg("--per", 100), arg("--buffer", 100), arg("--stable", 200), arg("--small", 50)
    strata, yod, zone = draw_strata()
    g = json.load(open(WORK / "grid.json"))
    rng = np.random.default_rng(SEED)
    want = {1: per, 2: per, 3: stable, 4: buf, 5: small}
    names = {1: "clearing", 2: "degradation", 3: "stable", 4: "stable_near_loss", 5: "small_lowconf"}
    b = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    rows, area = [], {}
    for k, n in want.items():
        ii = np.flatnonzero(strata.ravel() == k)
        area[names[k]] = float(len(ii) * PX_HA)
        pick = rng.choice(ii, min(n, len(ii)), replace=False)
        for p in pick:
            r, c = np.unravel_index(p, strata.shape)
            rows.append(dict(stratum=names[k], row=int(r), col=int(c), x=g["x0"] + (c + .5) * RES, y=g["y1"] - (r + .5) * RES,
                             map_year=int(yod[r, c]), zone_id=int(zone[r, c])))
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)   # blind order
    df.insert(0, "sample_id", np.arange(1, len(df) + 1))
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(PROJ4, "EPSG:4326", always_xy=True).transform(df.x.values, df.y.values)
    df["lon"], df["lat"] = np.round(lon, 6), np.round(lat, 6)
    df["Division"] = df.zone_id.map(b.Division)
    df["Range"] = df.zone_id.map(b.Range)
    df["Beat"] = df.zone_id.map(b.Beat)
    d = OUT / "accuracy"
    d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / "sample_key_DO_NOT_OPEN_BEFORE_LABELLING.csv", index=False)
    json.dump(area, open(d / "strata_area_ha.json", "w"), indent=1)
    blind = df[["sample_id", "lon", "lat", "Division", "Range", "Beat"]].copy()
    blind["gee_or_maps_link"] = [f"https://www.google.com/maps/@{a},{o},1500m/data=!3m1!1e3" for a, o in zip(df.lat, df.lon)]
    for c in ("label_change", "label_year", "label_confidence", "notes"):
        blind[c] = ""
    blind.to_csv(d / "labels_to_fill.csv", index=False)
    print(df.stratum.value_counts().to_string(), "\n", area)
    if "--chips" in sys.argv:
        make_chips(df, d / "chips")


if __name__ == "__main__":
    main()
