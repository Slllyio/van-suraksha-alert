"""MODIS as-of climatology of the live models (as mp_features.py, MP_FWD=1): per division and cell, the mean of the daily
as-of ndvi / ndmi / lst_k over 2013-12-01 .. 2024-12-31 in each 14-day bin (doy // 14). Bins 3-10 cover the issue days
13 Feb - 30 May. Out: E:/FIRE/mp/pc_models/modis_clim.parquet (cell, division, <var>_b<bin>; dtype as computed)."""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd

MP = Path(r"E:\FIRE\mp")
BINS = range(3, 11)
days = pd.date_range("2013-12-01", "2026-12-31", freq="D")


def asof(path, col, cells):
    m = pd.read_csv(path, parse_dates=["date"]); m["avail"] = m.date + pd.Timedelta(days=9)
    p = m.pivot(index="avail", columns="cell_id", values=col).reindex(columns=cells)
    return p.reindex(p.index.union(days)).sort_index().ffill(limit=40).reindex(days).to_numpy(np.float32)


parts = []
for f in sorted((MP / "results_officer" / "predictions_quiet_fwd").glob("*.parquet")):
    dv = f.stem
    grid = gpd.read_file(MP / dv / "grid_500m.geojson", ignore_geometry=True)
    cells = grid.cell_id.to_numpy()
    out = {"cell": grid.mp_cell.to_numpy(), "division": dv}
    for path, col in ((MP / dv / "ee" / "modis_ndvi_ndmi.csv", "ndvi"), (MP / dv / "ee" / "modis_ndvi_ndmi.csv", "ndmi"),
                      (MP / dv / "ee" / "modis_lst.csv", "lst_k")):
        a = pd.DataFrame(asof(path, col, cells), index=days)
        clim = a[a.index.year <= 2024].groupby(a.index[a.index.year <= 2024].dayofyear // 14).mean()
        for b in BINS:
            out[f"{col}_b{b}"] = clim.loc[b].to_numpy()
    parts.append(pd.DataFrame(out))
    print(dv, flush=True)
C = pd.concat(parts, ignore_index=True)
C.to_parquet(MP / "pc_models" / "modis_clim.parquet", index=False, compression="zstd")
print(C.shape, C.dtypes.value_counts().to_dict(), round((MP / "pc_models" / "modis_clim.parquet").stat().st_size / 1e6, 1), "MB")
