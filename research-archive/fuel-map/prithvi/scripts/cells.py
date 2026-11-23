"""Per 500 m cell: centre, forest share, canopy (S2 cover %, v3 work), v3 litter/grass potential means; per cell-season Prithvi/raw features
(mean of 5 bilinear samples: centre and +-125 m).  Out: scratch cells.parquet, cellfeat_{kind}.parquet (season, cell_id, features)."""
import json, numpy as np, pandas as pd, rasterio
import common as C
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
cells = pd.DataFrame([f['properties'] for f in G]).sort_values('cell_id').reset_index(drop=True)
cells['x'] = cells.x0 + 250; cells['y'] = cells.y0 + 250
FM = '/mnt/project-files/fuel-map/ratapani/'
def cellmean(path, scale, nod):
    with rasterio.open(path) as r:
        a = r.read(1).astype(float); t = r.transform
    a[(a == nod) | np.isnan(a)] = np.nan; a *= scale
    out = []
    for c in cells.itertuples():
        c0 = int(round((c.x0 - t.c) / t.a)); r0 = int(round((t.f - (c.y0 + 500)) / -t.e)); n = int(round(500 / t.a))
        w = a[max(r0, 0):r0 + n, max(c0, 0):c0 + n]; out.append(np.nanmean(w) if w.size and np.isfinite(w).any() else np.nan)
    return np.array(out)
cells['canopy'] = cellmean(FM + 'canopy_cover_10m.tif', 0.1, 65535)
cells['litter'] = cellmean(FM + 'v3/litter_potential_central_1ha.tif', 1.0, -1)
cells['grass'] = cellmean(FM + 'v3/grass_potential_central_10m.tif', 0.01, 65535)
cells['teak'] = cellmean(FM + 'teak_probability_10m.tif', 1.0, -9999)
cells.to_parquet(f'{C.SP}/cells.parquet'); print(cells.describe().T[['mean', 'min', 'max']])
off = [(0, 0), (125, 125), (-125, 125), (125, -125), (-125, -125)]
for kind in ('prithvi', 'raw'):
    fr = []
    for Y in range(2017, 2027):
        v = np.nanmean(np.stack([C.sample(Y, kind, cells.x.values + dx, cells.y.values + dy) for dx, dy in off]), 0)
        d = pd.DataFrame(v, columns=C.NAMES[kind]); d.insert(0, 'cell_id', cells.cell_id.values); d.insert(0, 'season', Y); fr.append(d)
    pd.concat(fr).to_parquet(f'{C.SP}/cellfeat_{kind}.parquet'); print(kind, 'done')
