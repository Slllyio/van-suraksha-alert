"""Scar detectability and scar size by Roy-2015 forest type, from the existing all-MP scar runs (15 Oct, v1 method, 3 km chips).
Inputs: /mnt/project-files/fire-alert-scars/mp/out/{set_sample,scars_sample,set_tiger_reserves,scars_tiger_reserves}.csv
Output: out/scar_by_type.csv, out/scar_by_type_month.csv"""
import pandas as pd, numpy as np, rasterio
from pyproj import Transformer
D = '/mnt/project-files/fire-alert-scars/mp/out/'
VTM = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r14_types_data/vtm.tif'
GROUPS = {'sal': [24, 27, 36], 'teak': [25, 28, 37], 'dry_mixed': [26], 'moist_mixed': [23], 'degraded': [106],
          'bamboo': [30, 40], 'north_dry': [29, 46, 49, 53, 54, 55, 116, 120, 121, 123, 124, 132, 135], 'agri_settl': [170, 200, 150, 180]}
c2g = {c: g for g, cs in GROUPS.items() for c in cs}
tr = Transformer.from_crs(4326, 32643, always_xy=True)
def vtm(lon, lat):
    x, y = tr.transform(lon, lat)
    with rasterio.open(VTM) as r:
        return np.array([v[0] for v in r.sample(zip(x, y))])
cols = ['event_id', 'status', 'gap_days', 'scar_ha', 'rdnbr_median', 'severity', 'touches_chip_edge']
out = []
for setf, scf, lab in (('set_sample.csv', 'scars_sample.csv', 'sample'), ('set_tiger_reserves.csv', 'scars_tiger_reserves.csv', 'tiger')):
    s = pd.read_csv(D + setf, usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'Division'] + (['kind'] if lab == 'sample' else []))
    if 'kind' not in s: s['kind'] = 'fire'
    c = pd.read_csv(D + scf, usecols=cols)
    m = s.merge(c, on='event_id', how='inner')
    m['vtm'] = vtm(m.longitude.values, m.latitude.values)
    m['grp'] = m.vtm.map(c2g).fillna('other')
    m['month'] = pd.to_datetime(m.acq_date).dt.month
    m['found'] = m.status.eq('scar')
    m['set'] = lab
    out.append(m)
A = pd.concat(out)
A.drop(columns=[]).to_csv('out/scar_events_with_type.csv', index=False)
g = A.groupby(['set', 'kind', 'grp']).agg(n=('found', 'size'), found=('found', 'mean'), scar_ha_med=('scar_ha', 'median'),
                                           rdnbr_med=('rdnbr_median', 'median'), gap_med=('gap_days', 'median')).reset_index()
g.to_csv('out/scar_by_type.csv', index=False, float_format='%.3g')
print(g.to_string())
f = A[A.kind == 'fire']
gm = f.groupby(['grp', 'month']).found.agg(['size', 'mean']).unstack()
gm.to_csv('out/scar_by_type_month.csv', float_format='%.3g'); print(gm.round(2).to_string())
print(A.status.value_counts())
