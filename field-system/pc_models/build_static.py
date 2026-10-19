"""Static per-square inputs of the live models for all 87 divisions, exactly as the models see them in the 2026 season:
cell, division, ae00-ae15 (the division's own PCA-16 of AlphaEarth, fitted on 2017-2024, applied to the 2025 embedding:
season Y uses the embedding of year Y-1), terrain, WorldCover, population, proximity and forest_frac columns.
Read straight from the 2026 feature tables (feats_fwd/season_2026.parquet, first issue day). Out: E:/FIRE/mp/pc_models/static_inputs.parquet"""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd

MP = Path(r"E:\FIRE\mp")
STATIC_CSV = ("terrain.csv", "worldcover.csv", "population.csv", "proximity.csv")
parts = []
for p in sorted((MP / "results_officer" / "predictions_quiet_fwd").glob("*.parquet")):
    dv = p.stem; D = MP / dv
    names = set()
    for f in STATIC_CSV:
        if (D / "ee" / f).exists():
            names |= set(pd.read_csv(D / "ee" / f, nrows=0).columns) - {"cell_id"}
    x = pd.read_parquet(D / "feats_fwd" / "season_2026.parquet")
    x = x[x.date == x.date.min()]
    cols = [f"ae{k:02d}" for k in range(16)] + sorted(c for c in x.columns if c in names) + ["forest_frac"]
    grid = gpd.read_file(D / "grid_500m.geojson", ignore_geometry=True)
    cell = grid.set_index("cell_id").mp_cell.reindex(x.cell_id).to_numpy()
    part = x[cols].assign(cell=cell, division=dv)
    if (D / "ee" / "terrain.csv").exists():          # original float64 slope: the pipeline forms spread_slope with it
        tr = pd.read_csv(D / "ee" / "terrain.csv").set_index("cell_id")
        if "slope_deg_mean" in tr:
            part["slope_deg_mean_f64"] = tr.slope_deg_mean.reindex(x.cell_id).to_numpy(np.float64)
    parts.append(part)
S = pd.concat(parts, ignore_index=True)
S = S[["cell", "division"] + [c for c in S.columns if c not in ("cell", "division")]]
S.to_parquet(MP / "pc_models" / "static_inputs.parquet", index=False, compression="zstd")
print(S.shape, round((MP / "pc_models" / "static_inputs.parquet").stat().st_size / 1e6, 1), "MB")
print(S.isna().mean().round(3)[S.isna().mean() > 0].to_dict())
