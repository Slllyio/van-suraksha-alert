"""Day-dated first burns per 500 m cell, for the cleaner-labels thread (ratapani/labels_v3/).

One row per (season, cell_id, fire_day, source) for every dated day inside the cell's first-burn window
(ws, we] from the research labels (burned >= 0.5 ha), plus one row with empty fire_day for each first burn
nothing dates. Sources:
  s2_af / landsat_af  active-fire pixels from af_scan.py inside the cell that day (~10:30-10:45 IST)  conf high
  viirs               S-NPP or NOAA-20 point (nominal/high) within 750 m of the cell centre on [ws, we+1],
                      clipped into (ws, we]; conf high <= 400 m, med 400-750 m
  modis               MODIS point (conf >= 30) within 750 m, same window rule; conf low
Columns: season, cell_id, fire_day, source, n_fire_px, dist_m, scar_ha_in_cell, conf, viirs_within_750m,
         window_start, window_end
Out: out/af/dated_first_burns.csv
"""
import glob, os
import numpy as np, pandas as pd, geopandas as gpd
from scipy.spatial import cKDTree
from pyproj import Transformer

P = "/mnt/project-files/"
AF = P + "fire-alert-scars/out/af/"
TO = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)

bw = pd.read_csv(P + "research/ratapani-burn-labels/burn_windows.csv", parse_dates=["window_start", "window_end"])
bw = bw[bw.burned == 1].sort_values(["season", "cell_id", "window_end"]).drop_duplicates(["season", "cell_id"])
bw = bw.rename(columns={"burned_ha": "scar_ha_in_cell"})[["season", "cell_id", "window_start", "window_end", "scar_ha_in_cell"]]
grid = gpd.read_file(P + "ratapani/grid_500m.geojson").to_crs(32643)
cen = np.c_[grid.geometry.centroid.x, grid.geometry.centroid.y]
cid = grid.cell_id.values
tree = cKDTree(cen)

# FIRMS points
A = pd.concat([pd.read_csv(f, dtype={"acq_time": str, "confidence": str}).assign(sensor=os.path.basename(f).split("_")[0])
               for f in glob.glob(P + "fire-alert-scars/alerts/*.csv")], ignore_index=True)
# Earth Engine 2026 files repeat Dec 2025, which the FIRMS 2025 files already hold
A = A[~(A.acq_date.str.startswith("2025-12") & A.version.astype(str).str.contains("EE"))]
A = A.drop_duplicates(["latitude", "longitude", "acq_date", "acq_time", "sensor"])
c = A.confidence.astype(str).str.lower()
A = A[np.where(A.sensor == "modis", pd.to_numeric(c, errors="coerce") >= 30, c != "l")].copy()
A["date"] = pd.to_datetime(A.acq_date)
A["x"], A["y"] = TO.transform(A.longitude.values, A.latitude.values)
rows = []
for i, nb in enumerate(tree.query_ball_point(A[["x", "y"]].values, 750)):
    for k in nb:
        rows.append((cid[k], A.date.iloc[i], A.sensor.iloc[i], float(np.hypot(*(A[["x", "y"]].values[i] - cen[k])))))
F = pd.DataFrame(rows, columns=["cell_id", "d", "sensor", "dist_m"])
F = F.merge(bw, on="cell_id")
F = F[(F.d >= F.window_start) & (F.d <= F.window_end + pd.Timedelta("1D"))].copy()
F["fire_day"] = F.d.clip(lower=F.window_start + pd.Timedelta("1D"), upper=F.window_end)
F["source"] = np.where(F.sensor == "modis", "modis", "viirs")
F = F.sort_values("dist_m").groupby(["season", "cell_id", "fire_day", "source"], as_index=False).agg(
    dist_m=("dist_m", "min"), n_fire_px=("d", "size"), window_start=("window_start", "first"),
    window_end=("window_end", "first"), scar_ha_in_cell=("scar_ha_in_cell", "first"))
F["conf"] = np.where(F.source == "modis", "low", np.where(F.dist_m <= 400, "high", "med"))

# S2 / Landsat active fire pixels inside the cell
D = pd.read_csv(AF + "af_pixels_clean.csv", parse_dates=["date"]).dropna(subset=["cell_id"])
D["cell_id"] = D.cell_id.astype(int)
D = D.merge(bw, on=["season", "cell_id"])
D = D[(D.date > D.window_start) & (D.date <= D.window_end)]
S = D.groupby(["season", "cell_id", "date", "sensor"], as_index=False).agg(
    n_fire_px=("row", "size"), window_start=("window_start", "first"), window_end=("window_end", "first"),
    scar_ha_in_cell=("scar_ha_in_cell", "first")).rename(columns={"date": "fire_day"})
S["source"] = S.sensor.map({"s2": "s2_af", "ls": "landsat_af"})
S["conf"], S["dist_m"] = "high", 0.0

out = pd.concat([F, S.drop(columns="sensor")], ignore_index=True)
v750 = set(map(tuple, F[F.source == "viirs"][["season", "cell_id"]].values))
undated = bw.merge(out[["season", "cell_id"]].drop_duplicates(), how="left", indicator=True)
undated = undated[undated._merge == "left_only"].drop(columns="_merge").assign(source="none", conf=None)
out = pd.concat([out, undated], ignore_index=True)
out["viirs_within_750m"] = [(s, c) in v750 for s, c in zip(out.season, out.cell_id)]
out["fire_day"] = pd.to_datetime(out.fire_day).dt.strftime("%Y-%m-%d")
cols = ["season", "cell_id", "fire_day", "source", "n_fire_px", "dist_m", "scar_ha_in_cell", "conf",
        "viirs_within_750m", "window_start", "window_end"]
out = out[cols].sort_values(["season", "cell_id", "fire_day"])
out["window_start"] = pd.to_datetime(out.window_start).dt.strftime("%Y-%m-%d")
out["window_end"] = pd.to_datetime(out.window_end).dt.strftime("%Y-%m-%d")
out.to_csv(AF + "dated_first_burns.csv", index=False)
fb = out.groupby(["season", "cell_id"]).agg(any_=("source", lambda s: (s != "none").any()),
                                             af=("source", lambda s: s.isin(["s2_af", "landsat_af"]).any()),
                                             v=("viirs_within_750m", "first"))
print("first burns", len(fb), "dated", round(fb.any_.mean(), 3), "AF-dated", round(fb.af.mean(), 3),
      "AF-dated with no VIIRS within 750 m", int((fb.af & ~fb.v).sum()))
print(out.source.value_counts().to_dict())
