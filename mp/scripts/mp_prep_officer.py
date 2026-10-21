"""Prep for the officer-style evaluation:
- E:/FIRE/mp/neighbours.json: for each division folder, the divisions whose boundary lies within 5 km.
- E:/FIRE/mp/<division>/beat_map.csv: cell_id -> range, beat (the beat polygon containing the cell centre;
  cells outside every beat polygon get no beat)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd

MP = Path(r"E:\FIRE\mp")
X0, Y1, S = 399000.0, 2996000.0, 500.0
div = gpd.read_file(r"E:\FIRE\data\aoi\mp_divisions_dissolved.geojson").to_crs(32643)
div["folder"] = div.Division.str.replace(" ", "_")
div["geometry"] = div.geometry.simplify(200).buffer(0)
nb = {}
for _, r in div.iterrows():
    near = div[(div.folder != r.folder) & (div.distance(r.geometry) <= 5000)]
    nb[r.folder] = sorted(near.folder)
(MP / "neighbours.json").write_text(json.dumps(nb, indent=1))
print("neighbours: median", int(np.median([len(v) for v in nb.values()])), "per division")

beats = gpd.read_file(r"E:\FIRE\data\aoi\mp_beats_wgs84.geojson").to_crs(32643)[["Division", "Range", "Beat", "geometry"]]
beats["geometry"] = beats.geometry.buffer(0)
for g in sorted(MP.glob("*/grid_500m.geojson")):
    d = g.parent
    grid = gpd.read_file(g).drop(columns="geometry")
    pts = gpd.GeoDataFrame(grid[["cell_id"]], geometry=gpd.points_from_xy(X0 + (grid.col + 0.5) * S, Y1 - (grid.row + 0.5) * S), crs=32643)
    j = gpd.sjoin(pts, beats, predicate="within", how="left").drop_duplicates("cell_id")
    out = j[["cell_id", "Division", "Range", "Beat"]].rename(columns={"Division": "beat_division"})
    out["beat_id"] = out.beat_division + "|" + out.Range + "|" + out.Beat
    out.to_csv(d / "beat_map.csv", index=False)
    print(f"{d.name:28s} cells={len(out):6d} in a beat={out.beat_id.notna().mean():.1%} beats={out.beat_id.nunique()}")
