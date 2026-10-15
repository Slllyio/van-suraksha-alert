"""MP step 1: 500 m grids for the selected divisions -> E:/FIRE/mp/<Division>/{grid_500m.geojson, aoi.geojson}.
Cells are a subset of the shared all-MP grid (EPSG:32643, X0=399000, Y1=2996000, 1829 cols; mp_cell = row*1829+col),
the same grid used by mp_dry_pull.py and aligned with the Ratapani grid. A cell is kept if >= 25% lies inside the
division. Per-division columns: cell_id (0..n-1), i (col offset), j (row offset), mp_cell, row, col."""
from pathlib import Path
import numpy as np
import geopandas as gpd
from shapely.geometry import box

X0, Y1, S, NCOL = 399000.0, 2996000.0, 500.0, 1829
MP = Path(r"E:\FIRE\mp")
d = gpd.read_file(r"E:\FIRE\data\aoi\mp_divisions_dissolved.geojson").to_crs(32643)
DIVS = sorted(d.Division)  # all 87 divisions; folders that already have a grid are left untouched
for name in DIVS:
    row = d[d.Division == name]
    assert len(row) == 1, name
    poly = row.geometry.iloc[0].buffer(0)
    x0, y0, x1, y1 = poly.bounds
    c0, c1 = int(np.floor((x0 - X0) / S)), int(np.ceil((x1 - X0) / S))
    r0, r1 = int(np.floor((Y1 - y1) / S)), int(np.ceil((Y1 - y0) / S))
    cols, rows = np.meshgrid(np.arange(c0, c1), np.arange(r0, r1))
    cols, rows = cols.ravel(), rows.ravel()
    geom = [box(X0 + c * S, Y1 - (r + 1) * S, X0 + (c + 1) * S, Y1 - r * S) for c, r in zip(cols, rows)]
    cells = gpd.GeoDataFrame({"col": cols, "row": rows}, geometry=geom, crs=32643)
    keep = cells.intersects(poly)
    cells = cells[keep]
    cells = cells[cells.intersection(poly).area >= 0.25 * S * S].reset_index(drop=True)
    cells["mp_cell"] = cells.row * NCOL + cells.col
    cells["i"] = cells.col - cells.col.min()          # x offset (as in the Ratapani grid)
    cells["j"] = cells.row.max() - cells.row          # y offset, increasing northwards
    cells.insert(0, "cell_id", np.arange(len(cells)))
    out = MP / name.replace(" ", "_")
    if (out / "grid_500m.geojson").exists():
        continue
    out.mkdir(parents=True, exist_ok=True)
    for f in (out / "ee").glob("*.csv"):
        f.unlink()
    cells.to_crs(4326).to_file(out / "grid_500m.geojson", driver="GeoJSON")
    row.to_crs(4326).to_file(out / "aoi.geojson", driver="GeoJSON")
    print(f"{name:22s} cells={len(cells):6d} raster={cells.i.max() + 1}x{cells.j.max() + 1} mp_cell {cells.mp_cell.min()}..{cells.mp_cell.max()}")
