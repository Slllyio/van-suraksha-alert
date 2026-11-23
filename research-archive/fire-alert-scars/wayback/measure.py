"""Automatic version of the eye check: on the post-fire Wayback image, is the ground inside our scar
outline darker / greyer than a 150 m ring just outside it? Real outlines vs decoys (same shape moved
3 km to unburned forest), by days between fire and image. Out: measure.csv"""
import json, numpy as np, pandas as pd
from PIL import Image, ImageDraw
from shapely.geometry import shape
from pyproj import Transformer
import render as RD
D = RD.D
TO = Transformer.from_crs(4326, 32643, always_xy=True); BK = Transformer.from_crs(32643, 4326, always_xy=True)
from shapely.ops import transform
X = pd.read_csv(D + "sample.csv"); K = pd.read_csv(D + "key.csv")
def mask(poly, to, size=420):
    m = Image.new("L", (size, size), 0); d = ImageDraw.Draw(m)
    for p in (getattr(poly, "geoms", None) or [poly]):
        if p.is_empty: continue
        d.polygon([to(*c[:2]) for c in p.exterior.coords], fill=1)
        for h in p.interiors: d.polygon([to(*c[:2]) for c in h.coords], fill=0)
    return np.asarray(m, bool)
rows = []
for i, r in X.iterrows():
    if not isinstance(r.scar_geom, str): continue
    im, to = RD.img(int(r.release), int(min(r.MaxMapLevel, 18)), r.lat, r.lon)
    a = np.asarray(im, np.float32)
    g = shape(json.loads(r.scar_geom))
    gu = transform(lambda x, y, z=None: TO.transform(x, y), g)
    ring = transform(lambda x, y, z=None: BK.transform(x, y), gu.buffer(150).difference(gu.buffer(20)))
    mi, mr = mask(g, to), mask(ring, to)
    if mi.sum() < 200 or mr.sum() < 200: continue
    br = a.mean(2); grey = a.max(2) - a.min(2); green = a[..., 1] - (a[..., 0] + a[..., 2]) / 2
    rows.append(dict(chip=i, d_bright=br[mr].mean() - br[mi].mean(), d_sat=grey[mr].mean() - grey[mi].mean(),
                     d_green=green[mr].mean() - green[mi].mean(), px_in=int(mi.sum())))
M = pd.DataFrame(rows).merge(K, on="chip")
M.to_csv(D + "measure.csv", index=False)
from sklearn.metrics import roc_auc_score
M["agebin"] = pd.cut(M.age, [0, 3, 7, 15, 40])
for c in ("d_bright", "d_sat", "d_green"):
    print(c, "real vs decoy AUC", round(roc_auc_score(M.kind == "real", M[c]), 3),
          "| by age:", {str(b): round(roc_auc_score(g.kind == "real", g[c]), 2) for b, g in
                        pd.concat([M[M.kind == "real"], M[M.kind == "decoy"]]).groupby("agebin") if g.kind.nunique() == 2})
print(M.groupby(["kind", "agebin"]).size().unstack(fill_value=0))
