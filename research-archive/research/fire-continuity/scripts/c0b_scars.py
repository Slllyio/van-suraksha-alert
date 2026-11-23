"""Rebuild each fire's outline (union of its scar outlines v2 events, as in big-fires b1_build_fires.py, using the
event lists in big-fires/results/fires.csv). Out: results/fire_scars.pkl {fire: shapely polygon, UTM 43N}."""
import json, pickle, pandas as pd, pyproj
from shapely.geometry import shape
from shapely.ops import transform, unary_union
ROOT = '/mnt/project-files'; import os; SCRATCH = os.environ.get('FC_SCRATCH', '/tmp')
V2 = f'{ROOT}/fire-alert-scars/reference/v2_2026-10-16'
to_utm = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
d = json.load(open(f'{V2}/firms_event_scars.geojson'))
G = {f['properties']['event_id']: transform(to_utm, shape(f['geometry'])).buffer(0) for f in d['features']}
F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv')
S = {int(r.fire): unary_union([G[e] for e in r.events.split(';')]).buffer(0) for r in F.itertuples()}
chk = F.area_ha.values - [S[f].area / 1e4 for f in F.fire]
print(len(S), 'fires; max area mismatch ha', abs(chk).max())
pickle.dump(S, open(f'{SCRATCH}/fire_scars.pkl', 'wb'))
