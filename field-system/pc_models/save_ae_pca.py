"""Export each division's AlphaEarth PCA-16 exactly as the live models use it (mp_features.py: PCA(16, random_state=0)
fitted on the division's 2017-2024 embeddings, each year's missing cells filled with that year's column means) and check
it: applied to the 2025 embedding it must reproduce ae00-ae15 of static_inputs.parquet (2026 season) exactly.
Out: E:/FIRE/mp/pc_models/ae_pca.npz (per division: <div>__mean, <div>__components)."""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from sklearn.decomposition import PCA

MP = Path(r"E:\FIRE\mp")
static = pd.read_parquet(MP / "pc_models" / "static_inputs.parquet")
store, worst = {}, 0.0
for dv in sorted(static.division.unique()):
    grid = gpd.read_file(MP / dv / "grid_500m.geojson", ignore_geometry=True)
    cells = grid.cell_id.to_numpy()
    ae = {yr: pd.read_csv(MP / dv / "ee" / f"alphaearth_{yr}.csv").set_index("cell_id").reindex(cells) for yr in range(2017, 2026)}
    pca = PCA(16, random_state=0).fit(np.vstack([a.fillna(a.mean()).to_numpy() for yr, a in ae.items() if yr <= 2024]))
    store[f"{dv}__mean"] = pca.mean_; store[f"{dv}__components"] = pca.components_
    a25 = ae[2025]
    X = a25.fillna(a25.mean()).to_numpy()
    mine = ((X - pca.mean_) @ pca.components_.T).astype(np.float32)          # = pca.transform(X), as stored (float32)
    ref = static[static.division == dv].set_index("cell").reindex(grid.mp_cell.to_numpy())[[f"ae{k:02d}" for k in range(16)]].to_numpy()
    d = float(np.nanmax(np.abs(mine - ref))); worst = max(worst, d)
    print(dv, "max abs diff vs static_inputs", d, flush=True)
np.savez_compressed(MP / "pc_models" / "ae_pca.npz", **store)
print("worst", worst)
