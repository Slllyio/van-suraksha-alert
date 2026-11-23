"""Join FSI Fire Point Search alerts (tagged with FSI's own Division/Range/Beat/Compartment) to the 500 m grid and to our
MP beat polygons, to build an official cell -> beat -> compartment key and check cell_beat.csv against it."""
import json, re, numpy as np, pandas as pd
from pyproj import Transformer
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
P = '/mnt/project-files/ratapani/'; FP = P + 'fsi/fsi_portal/'
pts = pd.concat([pd.read_csv(FP + f) for f in ('fsi_pts_obedullaganj.csv', 'obd_2026.csv', 'fsi_pts_raisen.csv', 'fsi_pts_sehore.csv', 'fsi_pts_bhopal.csv')]).drop_duplicates()
print('FSI points (unique rows)', len(pts))
fwd = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
x, y = fwd(pts.Lon.values, pts.Lat.values)
G = json.load(open(P + 'grid_500m.geojson'))['features']
cells = {(round(f['properties']['x0']), round(f['properties']['y0'])): f['properties']['cell_id'] for f in G}
x0 = (np.floor(x / 500) * 500).round().astype(int); y0 = (np.floor(y / 500) * 500).round().astype(int)
pts['cell_id'] = [cells.get((a, b), -1) for a, b in zip(x0, y0)]
inn = pts[pts.cell_id >= 0].copy(); print('points inside the grid', len(inn), 'cells hit', inn.cell_id.nunique())
B = json.load(open(P + 'beats/beats_ratapani.geojson'))['features']
geoms = [shape(f['geometry']) for f in B]; props = [f['properties'] for f in B]; tree = STRtree(geoms)
def norm(s): return re.sub(r'[^a-z]', '', re.sub(r'(?i)\b(beat|range|division|block|project|east|west|north|south)\b', '', str(s)).lower())
own = []
for lon, lat in zip(inn.Lon.values, inn.Lat.values):
    p = Point(lon, lat); hit = [i for i in tree.query(p) if geoms[i].contains(p)]
    own.append(props[hit[0]] if hit else {})
print('beat props keys', list(props[0].keys()))
inn['our_beat'] = [o.get('Beat') or o.get('BEAT') or o.get('Beat_Name') for o in own]
inn['our_uid'] = [o.get('beat_uid') for o in own]
inn['fsi_b'] = inn.Beat.map(norm); inn['our_b'] = inn.our_beat.map(norm)
inn['match'] = [(a != '' and b != '' and (a in b or b in a)) for a, b in zip(inn.fsi_b, inn.our_b)]
print('point-level: FSI beat name matches the MP beat polygon containing the point:', round(inn.match.mean() * 100, 1), '%', 'of', len(inn))
cb = pd.read_csv(P + 'beats/cell_beat.csv'); bt = pd.read_csv(P + 'beats/beats_table.csv')
inn = inn.merge(cb.rename(columns={'beat_uid': 'cell_uid'}), on='cell_id', how='left').merge(bt[['beat_uid', 'Beat']].rename(columns={'beat_uid': 'cell_uid', 'Beat': 'cell_beat'}), on='cell_uid', how='left')
inn['cell_match'] = [(a != '' and (a in norm(b) or norm(b) in a)) for a, b in zip(inn.fsi_b, inn.cell_beat)]
print('cell-level: FSI beat matches cell_beat.csv beat:', round(inn.cell_match.mean() * 100, 1), '%')
# official key: majority FSI beat + compartment per cell
key = inn.groupby('cell_id').agg(fsi_division=('Division', lambda s: s.mode()[0]), fsi_range=('Range', lambda s: s.mode()[0]),
                                 fsi_beat=('Beat', lambda s: s.mode()[0]), fsi_compartment=('Compartment_No', lambda s: s.astype(str).mode()[0]),
                                 n_alerts=('Beat', 'size'), n_fsi_beats=('Beat', 'nunique'), n_compartments=('Compartment_No', 'nunique')).reset_index()
key = key.merge(cb, on='cell_id', how='left').merge(bt[['beat_uid', 'Division', 'Range', 'Beat']].rename(columns={'Division': 'our_division', 'Range': 'our_range', 'Beat': 'our_beat'}), on='beat_uid', how='left')
key['agree'] = [norm(a) != '' and (norm(a) in norm(b) or norm(b) in norm(a)) for a, b in zip(key.fsi_beat, key.our_beat)]
key.to_csv(P + 'beats/cell_fsi_key.csv', index=False)
print('cells with FSI alerts', len(key), 'of 3614; cells where FSI majority beat agrees with cell_beat.csv:', round(key.agree.mean() * 100, 1), '%')
print('cells whose alerts carry >1 FSI beat:', int((key.n_fsi_beats > 1).sum()), '; >1 compartment:', int((key.n_compartments > 1).sum()))
print('FSI beats seen', inn.Beat.nunique(), 'compartments', inn.Compartment_No.nunique())
dis = key[~key.agree]; print('disagreeing pairs (top 15):'); print(dis.groupby(['fsi_beat', 'our_beat']).size().sort_values(ascending=False).head(15).to_string())
json.dump(dict(points=len(pts), inside=len(inn), point_match=float(inn.match.mean()), cell_match=float(inn.cell_match.mean()), cells=len(key), cell_agree=float(key.agree.mean()),
               fsi_beats=int(inn.Beat.nunique()), compartments=int(inn.Compartment_No.nunique())), open(P + 'beats/fsi_key_check.json', 'w'), indent=1)
