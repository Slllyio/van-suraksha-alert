"""Which leaf-on window gives the least inter-annual noise, and do the sensors agree?
Samples random forest points in a dry-deciduous and a moist division."""
import json
import ee
import numpy as np
import pandas as pd
from common import *
init()
div = ee.FeatureCollection(DIVISIONS_ASSET)
res = []
for name in ["Guna", "Lamta_Proj_N_Balaghat", "Sheopur"]:
    roi = div.filter(ee.Filter.eq("Division", name)).geometry()
    pts = ee.FeatureCollection.randomPoints(roi, 400, 7)
    for wname, w in {"sep15_dec31": ("09-15", "12-31"), "sep15_nov30": ("09-15", "11-30"), "oct01_nov30": ("10-01", "11-30")}.items():
        for sname, s in {"all": ("L7", "L8", "L9", "S2"), "landsat": ("L7", "L8", "L9")}.items():
            if sname == "landsat" and wname != "sep15_nov30":
                continue
            stack = ee.Image.cat([composite(y, roi, w, s).rename([f"NBR_{y}", f"NDVI_{y}"]) for y in range(2014, 2026)])
            d = stack.reduceRegions(pts, ee.Reducer.first(), scale=30, tileScale=4).getInfo()
            df = pd.DataFrame([f["properties"] for f in d["features"]])
            df["div"], df["win"], df["sens"] = name, wname, sname
            res.append(df)
            nb = df[[f"NBR_{y}" for y in range(2014, 2026)]].astype(float).values
            print(name, wname, sname, "med|dNBR|=%.4f p95|dNBR|=%.4f miss=%.3f" % (
                np.nanmedian(np.abs(np.diff(nb, axis=1))), np.nanpercentile(np.abs(np.diff(nb, axis=1)), 95), np.isnan(nb).mean()),
                "yr mean NBR", np.round(np.nanmean(nb, axis=0), 3).tolist(), flush=True)
pd.concat(res).to_csv(OUT / "composite_window_test.csv", index=False)
