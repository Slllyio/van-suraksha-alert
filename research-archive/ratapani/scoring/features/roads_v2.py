"""Road features v2: OSM (old roads_features.parquet) union Microsoft Road Detections 2025-04-28 (Southern_Asia, IND, box 77.25-78.15E 22.75-23.25N).
dist_road_km = min(OSM distance, MS distance) from cell centre; road_km_in_cell = max(OSM, MS) length inside the cell (avoids double counting shared roads)."""
import json, numpy as np, pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
fwd = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
pts = []
for line in open('/tmp/claude-0/msroads/ms_roads_rata_full.tsv'):
    c = np.array(json.loads(line.split('\t', 1)[1])['geometry']['coordinates'])
    x, y = fwd(c[:, 0], c[:, 1]); xy = np.c_[x, y]
    for a, b in zip(xy[:-1], xy[1:]):
        n = max(1, int(np.hypot(*(b - a)) // 10)); t = (np.arange(n) + 0.5) / n; pts.append(a + t[:, None] * (b - a))   # one point per ~10 m
P = np.concatenate(pts); seg_len = 10.0
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
cid = np.array([f['properties']['cell_id'] for f in G]); x0 = np.array([f['properties']['x0'] for f in G]); y0 = np.array([f['properties']['y0'] for f in G])
d, _ = cKDTree(P).query(np.c_[x0 + 250, y0 + 250])
key = {(a, b): c for a, b, c in zip(x0, y0, cid)}
ci = [key.get((float(np.floor(px / 500) * 500), float(np.floor(py / 500) * 500)), -1) for px, py in P]
ln = pd.Series(ci).value_counts(); ms_len = np.zeros(3614); idx = ln.index.values[ln.index.values >= 0]; ms_len[idx] = ln.loc[idx].values * seg_len / 1000
old = pd.read_parquet('roads_features.parquet').set_index('cell_id').sort_index()
new = old.copy(); new['dist_road_km'] = np.minimum(old.dist_road_km.values, d[np.argsort(cid)] / 1000) if (np.sort(cid) == np.arange(3614)).all() else None
dd = pd.Series(d / 1000, index=cid).sort_index(); new['dist_road_km'] = np.minimum(old.dist_road_km, dd)
new['road_km_in_cell'] = np.maximum(old.road_km_in_cell, ms_len)
new.reset_index().to_parquet('roads_features_v2.parquet')
print('MS points', len(P), 'MS km', round(len(P) * seg_len / 1000, 1))
print(pd.DataFrame({'osm_dist_km': old.dist_road_km.describe(), 'ms_dist_km': dd.describe(), 'union_dist_km': new.dist_road_km.describe(),
                    'osm_len_km': old.road_km_in_cell.describe(), 'union_len_km': new.road_km_in_cell.describe()}).round(2))
