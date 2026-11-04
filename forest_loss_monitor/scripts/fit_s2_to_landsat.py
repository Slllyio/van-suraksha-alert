"""Index-level S2 -> Landsat cross-calibration (reduced major axis) from composite pairs.
Near-same-day pairs showed S2 SR NBR about 0.05 below Landsat C2 in forest, which the published
bandpass coefficients do not remove. Without this, the rising S2 share in 2017-19 looks like loss."""
import ee, numpy as np, pandas as pd
from common import *
init()
div = ee.FeatureCollection(DIVISIONS_ASSET)
W = WINDOW
fr = []
for name in ["Guna", "Lamta_Proj_N_Balaghat", "Sheopur", "South_Betul", "Singrauli", "Khargone"]:
    roi = div.filter(ee.Filter.eq("Division", name)).geometry()
    pts = ee.FeatureCollection.randomPoints(roi, 250, 21)
    b = []
    for y in range(2017, 2026):
        b += [composite(y, roi, W, ("L8", "L9")).rename([f"LN_{y}", f"LV_{y}"]),
              composite(y, roi, W, ("S2",)).rename([f"SN_{y}", f"SV_{y}"])]
    d = ee.Image.cat(b).reduceRegions(pts, ee.Reducer.first(), scale=30, tileScale=4).getInfo()
    df = pd.DataFrame([f["properties"] for f in d["features"]]).apply(pd.to_numeric, errors="coerce")
    for y in range(2017, 2026):
        fr.append(pd.DataFrame(dict(div=name, y=y, LN=df[f"LN_{y}"], SN=df[f"SN_{y}"], LV=df[f"LV_{y}"], SV=df[f"SV_{y}"])))
    print(name, flush=True)
a = pd.concat(fr).dropna(); a.to_csv(OUT / "s2_landsat_pairs.csv", index=False)
def rma(x, y):
    k = np.abs(y - x - np.median(y - x)) < 3 * 1.48 * np.median(np.abs(y - x - np.median(y - x)))  # trim cloud residue
    x, y = x[k], y[k]; b = y.std() / x.std() * np.sign(np.corrcoef(x, y)[0, 1]); return b, y.mean() - b * x.mean(), k.mean(), np.corrcoef(x, y)[0, 1]
for s, l in (("SN", "LN"), ("SV", "LV")):
    b, c, kept, r = rma(a[s].values, a[l].values)
    print(s, "-> Landsat: slope %.4f intercept %.4f kept %.3f r %.3f" % (b, c, kept, r))
    a[s + "c"] = c + b * a[s]
g = a.groupby("y")[["LN", "SN", "SNc", "LV", "SV", "SVc"]].median().round(3); print(g.to_string())
print(a.groupby("div")[["LN", "SNc", "LV", "SVc"]].median().round(3).to_string())
