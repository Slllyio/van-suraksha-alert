"""Tiger-reserve scar run: summary by reserve, a polygon file, and a check against FSI's Large Forest Fire archive
(lff_mp.csv: box of each large fire's detections). For each LFF fire in a reserve division (2017-25, 15 Feb-15 Jun),
did any of our scars from events inside its box (+500 m) and its dates (+1 day) exist, and how much of the box do they cover?
Out: mp/out/tiger_reserve_scars.geojson, mp/out/tr_lff_check.csv"""
import json, numpy as np, pandas as pd
from shapely.geometry import shape, box
from shapely.ops import unary_union, transform
from pyproj import Transformer
M = "/mnt/project-files/fire-alert-scars/mp/out/"
TO = Transformer.from_crs(4326, 32643, always_xy=True)
S = pd.read_csv(M + "set_tiger_reserves.csv"); R = pd.read_csv(M + "scars_tiger_reserves.csv").drop_duplicates("event_id", keep="last")
D = S.merge(R, on="event_id")
D["yes"] = D.status == "scar"
print("events", len(D), D.status.value_counts().to_dict())
T = D[~D.status.isin(["waiting", "no_pre", "error"])].groupby("Division").agg(events=("yes", "size"), scar_rate=("yes", "mean"),
      median_ha=("scar_ha", "median"), total_ha=("scar_ha", "sum"))
print(T.round(2))
feats = [{"type": "Feature", "geometry": json.loads(r.geometry), "properties": {k: (None if pd.isna(v) else v) for k, v in r._asdict().items()
          if k in ("event_id", "acq_date", "sensors", "n_alerts", "Division", "Range", "Beat", "beat_uid", "status", "scar_ha", "scar_ha_post",
                   "pre_date", "post_date", "check_date", "severity", "dist_m")}} for r in D[D.geometry.notna()].itertuples()]
json.dump({"type": "FeatureCollection", "features": feats}, open(M + "tiger_reserve_scars.geojson", "w"))
E = D[D.geometry.notna()].copy()
E["x"], E["y"] = TO.transform(E.longitude.values, E.latitude.values); E["d"] = pd.to_datetime(E.acq_date)
F = pd.read_csv("/mnt/project-files/ratapani/fsi/fsi_portal/lff_mp.csv")
F["d0"] = pd.to_datetime(F.F_T_D.str[:8]); F["d1"] = pd.to_datetime(F.L_T_D.str[:8])
md = F.d0.dt.strftime("%m-%d")
F = F[(md >= "02-15") & (md <= "06-15") & (F.d0.dt.year <= 2025)]
x0, y0 = TO.transform(F.EXT_MIN_X.values, F.EXT_MIN_Y.values); x1, y1 = TO.transform(F.EXT_MAX_X.values, F.EXT_MAX_Y.values)
F["b"] = [box(*v) for v in zip(x0, y0, x1, y1)]
F["cx"], F["cy"] = TO.transform(F.INSIDE_X.values, F.INSIDE_Y.values)
# keep LFF fires whose inside point is near one of our reserve events at all (same reserve area)
from scipy.spatial import cKDTree
allev = S.copy(); allev["x"], allev["y"] = TO.transform(allev.longitude.values, allev.latitude.values)
t = cKDTree(allev[["x", "y"]].values)
F = F[[len(t.query_ball_point([a, b], 2000)) > 0 for a, b in zip(F.cx, F.cy)]]
rows = []
for f in F.itertuples():
    bb = f.b.buffer(500)
    m = E[(E.d >= f.d0) & (E.d <= f.d1 + pd.Timedelta("1D")) & E.x.between(bb.bounds[0], bb.bounds[2]) & E.y.between(bb.bounds[1], bb.bounds[3])]
    g = unary_union([transform(lambda x, y, z=None: TO.transform(x, y), shape(json.loads(v))) for v in m.geometry]).buffer(0) if len(m) else None
    rows.append(dict(lff=f.Index, division=f.DIVISION, d0=f.d0.date(), box_ha=f.b.area / 1e4, matched=len(m) > 0,
                     box_cover=(g.intersection(f.b.buffer(30)).area / max(f.b.buffer(30).area, 1)) if g is not None else 0,
                     scar_ha=g.area / 1e4 if g is not None else 0))
L = pd.DataFrame(rows); L.to_csv(M + "tr_lff_check.csv", index=False)
print("LFF fires in reserves", len(L), "with a scar", L.matched.mean().round(3), "| box covered median", L[L.matched].box_cover.median().round(2))
print(L.groupby("division").matched.agg(["mean", "size"]).round(2))
