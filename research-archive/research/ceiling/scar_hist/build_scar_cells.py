"""Every MP scar outline 2017-25 (scar thread) burned onto the 500 m mp_grid: one row per (year, row, col) with
the share of the square under any scar that season. Out: scar_cells.parquet (year,row,col,frac)."""
import sys, json, numpy as np, pandas as pd, geopandas as gpd, shapely
from shapely import wkt
from shapely.geometry import shape
sys.path.insert(0, '/mnt/project-files/ratapani/scoring/mp_check'); import mp_simple_rules as M
sys.path.insert(0, '/mnt/project-files/fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom
O = '/mnt/project-files/fire-alert-scars/mp/out/'; OUT = '/mnt/project-files/research/ceiling/scar_hist/'
G = pd.concat([read_hist_geom()[['event_id', 'geometry']],
               pd.read_csv(O + 'scars_tiger_reserves.csv', usecols=['event_id', 'geometry']).dropna()]).drop_duplicates('event_id', keep='last')
G = G[G.geometry.notna()]; G['year'] = G.event_id.str[1:5].astype(int)
print('outlines', len(G), G.year.value_counts().sort_index().to_dict(), flush=True)
def parse(t):
    t = str(t).strip()
    try: return shape(json.loads(t)) if t.startswith('{') else wkt.loads(t)
    except Exception: return None
out = []
for y, g in G.groupby('year'):
    geoms = gpd.GeoSeries([parse(t) for t in g.geometry.values], crs=4326).to_crs(32643)
    geoms = geoms[geoms.notna() & ~geoms.is_empty]
    u = shapely.union_all(shapely.make_valid(geoms.values))   # merge overlaps so a square isn't counted twice
    parts = list(getattr(u, 'geoms', [u]))
    for p in parts:
        x0, y0, x1, y1 = p.bounds
        c0, c1 = int(np.floor((x0 - M.X0) / M.S)), int(np.floor((x1 - M.X0) / M.S)); r0, r1 = int(np.floor((M.Y1 - y1) / M.S)), int(np.floor((M.Y1 - y0) / M.S))
        rr, cc = np.mgrid[r0:r1 + 1, c0:c1 + 1]; rr, cc = rr.ravel(), cc.ravel()
        boxes = shapely.box(M.X0 + cc * M.S, M.Y1 - (rr + 1) * M.S, M.X0 + (cc + 1) * M.S, M.Y1 - rr * M.S)
        a = shapely.area(shapely.intersection(boxes, p)) / (M.S * M.S); k = a > 0
        out.append(pd.DataFrame({'year': y, 'row': rr[k], 'col': cc[k], 'frac': a[k].astype(np.float32)}))
    print(y, len(parts), flush=True)
C = pd.concat(out).groupby(['year', 'row', 'col'], as_index=False).frac.sum(); C['frac'] = C.frac.clip(upper=1)
C.to_parquet(OUT + 'scar_cells.parquet', index=False)
print(C.groupby('year').agg(n=('frac', 'size'), ge10=('frac', lambda s: int((s >= .1).sum()))).to_string())
