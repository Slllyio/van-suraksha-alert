"""Original vs split scars against FSI's Large Forest Fire archive (lff_mp.csv, bounding box of each fire's
VIIRS detections). For each LFF fire inside Ratapani, union our scars of events dated within its detection
days whose point lies in its box (+500 m). Report: share of the box covered, scar extent, and spill
(share of our scar area more than 500 m outside the box)."""
import json, numpy as np, pandas as pd
from shapely.geometry import shape, box
from shapely.ops import unary_union, transform
from pyproj import Transformer
R = "/mnt/project-files/fire-alert-scars/"
TO = Transformer.from_crs(4326, 32643, always_xy=True)
u = lambda g: transform(lambda x, y, z=None: TO.transform(x, y), shape(json.loads(g)))
E = pd.read_csv(R + "out/event_scars.csv").merge(pd.read_csv(R + "out/event_scars_split.csv")[["event_id", "geometry_split"]], on="event_id")
E = E[E.geometry_split.notna()]
E["x"], E["y"] = TO.transform(E.lon.values, E.lat.values); E["d"] = pd.to_datetime(E.date)
F = pd.read_csv("/mnt/project-files/ratapani/fsi/fsi_portal/lff_mp.csv")
F["d0"] = pd.to_datetime(F.F_T_D.str[:8]); F["d1"] = pd.to_datetime(F.L_T_D.str[:8])
x0, y0 = TO.transform(F.EXT_MIN_X.values, F.EXT_MIN_Y.values); x1, y1 = TO.transform(F.EXT_MAX_X.values, F.EXT_MAX_Y.values)
F["b"] = [box(*v) for v in zip(x0, y0, x1, y1)]
F = F[F.d0.dt.year >= 2017]
rows = []
for f in F.itertuples():
    bb = f.b.buffer(500)
    m = E[(E.d >= f.d0) & (E.d <= f.d1 + pd.Timedelta("1D")) & E.x.between(bb.bounds[0], bb.bounds[2]) & E.y.between(bb.bounds[1], bb.bounds[3])]
    if not len(m):
        continue
    for k, col in (("orig", "geometry"), ("split", "geometry_split")):
        g = unary_union([u(v) for v in m[col]]).buffer(0)
        bx = g.bounds
        rows.append(dict(fire=f.Index, kind=k, box_cover=g.intersection(f.b.buffer(30)).area / max(f.b.buffer(30).area, 1),
                         extent_km=max(bx[2] - bx[0], bx[3] - bx[1]) / 1000, box_km=max(f.b.bounds[2] - f.b.bounds[0], f.b.bounds[3] - f.b.bounds[1]) / 1000,
                         spill=1 - g.intersection(bb).area / g.area, ha=g.area / 1e4))
D = pd.DataFrame(rows)
print(D.fire.nunique(), "LFF fires matched")
print(D.groupby("kind")[["box_cover", "extent_km", "box_km", "spill", "ha"]].median().round(3))
D.to_csv(R + "out/eval_split_lff.csv", index=False)
