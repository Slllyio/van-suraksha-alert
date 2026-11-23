"""Is the ground v2 adds (redraw on a bigger chip) really burned? On Esri Wayback sub-metre images (<= 40 days after
the fire): brightness of the v1 outline, the added ground (v2 minus v1), and a 150 m ring outside v2.
Added ground as dark as v1 and darker than the ring = real burn. Out: v2_work/check_added.csv"""
import json, sys, numpy as np, pandas as pd
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/wayback")
import render as RD, measure_helpers as MH
B = "/mnt/project-files/fire-alert-scars/reference/"
TO = Transformer.from_crs(4326, 32643, always_xy=True); BK = Transformer.from_crs(32643, 4326, always_xy=True)
u = lambda g: transform(lambda x, y, z=None: TO.transform(x, y), g); b = lambda g: transform(lambda x, y, z=None: BK.transform(x, y), g)
F1 = {f["properties"]["event_id"]: f for f in json.load(open(B + "v1_2026-10-15/firms_event_scars.geojson"))["features"]}
F2 = {f["properties"]["event_id"]: f for f in json.load(open(B + "v2_2026-10-16/firms_event_scars.geojson"))["features"]}
C = pd.read_csv(B + "v2_2026-10-16/v2_changes.csv"); C = C[(C.src == "firms") & (C.action == "redrawn_split")]
M = pd.read_csv("/mnt/project-files/fire-alert-scars/wayback/matches.csv"); M = M[(M.src == "firms")].drop_duplicates("event_id")
M = M[M.event_id.isin(C.event_id)]
def one(r):
  try:
    return _one(r)
  except Exception as e:
    return dict(event_id=r.event_id, err=str(e)[:100])
def _one(r):
    from shapely import set_precision
    G1 = set_precision(u(shape(F1[r.event_id]["geometry"])).buffer(0), 1.0); G2 = set_precision(u(shape(F2[r.event_id]["geometry"])).buffer(0), 1.0)
    add = G2.difference(G1.buffer(20)); ring = G2.buffer(150).difference(G2.buffer(20))
    x0, y0, x1, y1 = G2.buffer(200).bounds; half = max(x1 - x0, y1 - y0) / 2
    lo, la = BK.transform((x0 + x1) / 2, (y0 + y1) / 2)
    zz = int(min(r.MaxMapLevel, 18, np.floor(np.log2(156543.03 * np.cos(np.radians(la)) * 2048 / (2 * half)))))
    im, to = RD.img(int(r.release), zz, la, lo, half_m=half)
    a = np.asarray(im, np.float32).mean(2)
    res = dict(event_id=r.event_id, age=r.age, ha_v1=G1.area / 1e4, ha_add=add.area / 1e4)
    for k, g in (("v1", G1), ("add", add), ("ring", ring)):
        m = MH.mask(b(g), to) if not g.is_empty else np.zeros_like(a, bool)
        res["br_" + k] = float(a[m].mean()) if m.sum() >= 50 else np.nan
    return res
with ThreadPoolExecutor(4) as ex:
    R = pd.DataFrame(list(ex.map(one, list(M.itertuples()))))
R.to_csv(B + "v2_work/check_added.csv", index=False)
v = R.dropna(subset=["br_v1", "br_add", "br_ring"])
print(len(R), "fires;", len(v), "measured. added darker than ring:", (v.br_add < v.br_ring).mean().round(3),
      "| v1 darker than ring:", (v.br_v1 < v.br_ring).mean().round(3), "| added within 3 of v1 or darker:", (v.br_add <= v.br_v1 + 3).mean().round(3))
print("median brightness v1/add/ring", v.br_v1.median().round(1), v.br_add.median().round(1), v.br_ring.median().round(1))
f = v[v.age <= 15]; print("images <= 15 d:", len(f), (f.br_add < f.br_ring).mean().round(3))
