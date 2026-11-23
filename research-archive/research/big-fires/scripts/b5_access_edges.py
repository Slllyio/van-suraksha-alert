"""Step 5: the firefighting bias (Akkshay 16 Oct 17:57Z: crews put out fires soon after an alert, sometimes before any alert).

(a) Are the big many-alert fires the remote ones crews could not reach early? Compare scar centroid distance to road,
    to the nearest building (Open Buildings), to the forest edge, for big fires against all other fires.
(b) Where do big-fire scars stop? Walk each big outline every 30 m and ask if the edge point is within 60 m of a road
    (OSM, TomTom, Microsoft >= 7 m wide), a stream (>= 1 km2 catchment), or within 1 km of a building. Baseline: the
    same questions for a ring 300 m outside the outline (if the edge ignored roads, the edge and the ring would touch
    roads equally often).
(c) Straight edges: stretches of outline where 600 m of edge stays within 25 m of a straight line. Listed per fire with
    what they sit on, so they can be looked at. A straight edge on a road can be a fire line, a crew stop or just the
    road as a fuel break; satellite data cannot tell these apart.
Out: results/access.csv, results/edges.csv, results/straight_edges.csv
"""
import json, pickle
import numpy as np, pandas as pd
from shapely.geometry import shape, LineString
from shapely.ops import transform, unary_union
from scipy.spatial import cKDTree
import pyproj
ROOT = '/mnt/project-files'
R = f'{ROOT}/research/big-fires/results'
F = pd.read_csv(f'{R}/fires.csv'); S = pickle.load(open(f'{R}/fire_scars.pkl', 'rb'))
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
bar = json.load(open(f'{ROOT}/ratapani/fsi/scouting/data/barriers_ratapani.geojson'))
def pts_of(classes, step=30):
    out = []
    for f in bar['features']:
        if f['properties']['cls'] not in classes: continue
        g = transform(tp, shape(f['geometry']))
        for line in getattr(g, 'geoms', [g]):
            if line.geom_type != 'LineString' or line.length == 0: continue
            n = max(int(line.length / step), 1)
            out += [line.interpolate(i * line.length / n).coords[0] for i in range(n + 1)]
    return cKDTree(np.array(out))
roads = pts_of({'road_osm', 'road_tomtom', 'road_ms_ge10m', 'road_ms_7_10m'})
streams = pts_of({'stream_dem_1_5km2', 'stream_dem_5_25km2', 'stream_dem_ge25km2'})
# buildings and forest edge via the 500 m grid
grid = json.load(open(f'{ROOT}/ratapani/grid_500m.geojson'))
gc = pd.DataFrame([dict(cell_id=g['properties']['cell_id'], x=g['properties']['x0'] + 250, y=g['properties']['y0'] + 250) for g in grid['features']])
ob = pd.read_csv(f'{ROOT}/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')
px = pd.read_csv(f'{ROOT}/ratapani/ee/proximity.csv')
gc = gc.merge(ob[['cell_id', 'd_ob']], on='cell_id', how='left').merge(px, on='cell_id', how='left')
gtree = cKDTree(gc[['x', 'y']].values)
def cell_val(x, y, col):
    d, i = gtree.query(np.c_[x, y]); v = gc[col].values[i].astype(float); v[d > 400] = np.nan; return v

# (a) access
F['d_road'] = roads.query(np.c_[F.cx, F.cy])[0]
F['d_bld'] = cell_val(F.cx.values, F.cy.values, 'd_ob')
F['depth'] = cell_val(F.cx.values, F.cy.values, 'depth_in_forest')
F['grp'] = np.where(F.big, 'big (200 ha+, 4+ looks)', np.where(F.n_looks >= 2, 'other multi-look', 'single-look'))
acc = F.groupby('grp')[['d_road', 'd_bld', 'depth', 'area_ha']].median().round(0)
acc['fires'] = F.groupby('grp').size()
print(acc); acc.to_csv(f'{R}/access.csv')

# (b, c) edges
def walk(geom, step=30):
    out = []
    for ring in ([geom.exterior] if geom.geom_type == 'Polygon' else [p.exterior for p in geom.geoms]):
        n = max(int(ring.length / step), 3)
        out.append(np.array([ring.interpolate(i * ring.length / n).coords[0] for i in range(n)]))
    return out
rows, straight = [], []
for _, f in F[F.big].iterrows():
    poly = S[f.fire]
    poly_s = poly.buffer(60).buffer(-60)          # drop pixel-scale wiggles
    big_parts = poly_s if poly_s.geom_type == 'Polygon' else unary_union([p for p in poly_s.geoms if p.area > 5e4])
    if big_parts.is_empty: continue
    edge = np.vstack(walk(big_parts)); ring = np.vstack(walk(big_parts.buffer(300)))
    for name, P in [('edge', edge), ('ring300', ring)]:
        rows.append(dict(fire=f.fire, where=name, road60=(roads.query(P)[0] < 60).mean(), stream60=(streams.query(P)[0] < 60).mean(),
                         bld1km=(cell_val(P[:, 0], P[:, 1], 'd_ob') < 1000).mean()))
    # straight stretches: 20 points = 600 m
    for E in walk(big_parts):
        n = len(E); k = 20
        if n < k + 1: continue
        flag = np.zeros(n, bool)
        for i in range(n):
            seg = E[[(i + j) % n for j in range(k + 1)]]
            a, b = seg[0], seg[-1]; L = np.hypot(*(b - a))
            if L < 500: continue
            dev = np.abs((b[0] - a[0]) * (a[1] - seg[:, 1]) - (a[0] - seg[:, 0]) * (b[1] - a[1])) / L
            if dev.max() < 25: flag[[(i + j) % n for j in range(k + 1)]] = True
        if not flag.any(): continue
        # group consecutive flagged points
        idx = np.where(flag)[0]
        groups = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
        for gidx in groups:
            seg = E[gidx]
            if len(seg) < k: continue
            az = np.degrees(np.arctan2(seg[-1, 0] - seg[0, 0], seg[-1, 1] - seg[0, 1])) % 180
            straight.append(dict(fire=f.fire, season=f.season, length_m=len(seg) * 30, azimuth=round(az),
                                 on_road=(roads.query(seg)[0] < 60).mean(), on_stream=(streams.query(seg)[0] < 60).mean(),
                                 bld_within1km=(np.nan_to_num(cell_val(seg[:, 0], seg[:, 1], 'd_ob'), nan=9e9) < 1000).mean(),
                                 grid_aligned=min(az % 90, 90 - az % 90) < 3,
                                 x_mid=seg[len(seg) // 2, 0], y_mid=seg[len(seg) // 2, 1]))
E = pd.DataFrame(rows); E.to_csv(f'{R}/edges.csv', index=False)
print(E.groupby('where')[['road60', 'stream60', 'bld1km']].mean().round(3))
Sd = pd.DataFrame(straight)
lon, lat = pyproj.Transformer.from_crs(32643, 4326, always_xy=True).transform(Sd.x_mid.values, Sd.y_mid.values)
Sd['lon'], Sd['lat'] = np.round(lon, 5), np.round(lat, 5)
Sd.to_csv(f'{R}/straight_edges.csv', index=False)
print(len(Sd), 'straight stretches in', Sd.fire.nunique(), 'fires; on road', (Sd.on_road > .5).mean().round(2),
      'on stream', (Sd.on_stream > .5).mean().round(2), 'grid aligned (N-S/E-W, possible image edge)', Sd.grid_aligned.mean().round(2))
