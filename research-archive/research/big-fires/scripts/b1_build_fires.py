"""Step 1: join same-fire events into fires and attach every satellite alert that sits on each fire's scar.

Truth: scar outlines v2 (2026-10-16), fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson.
An event there is one day's alerts within 1 km, so a fire that burns for 3 days is 3 events whose outlines overlap.
Here: events are joined into one fire when their dates are within 3 days and their outlines overlap by at least 30% of
the smaller one (transitively). The fire's scar is the union of its events' outlines.
Alerts: raw FIRMS files (S-NPP, NOAA-20, NOAA-21 VIIRS; MODIS kept separately) inside the scar buffered by 200 m (the
outline rule's own circle), dated from the day before the first event to 2 days after the last.
A "look" (pass) = alerts within 2 h of each other (the three VIIRS satellites cross within ~50 min).
Out: results/fires.csv (one row per fire), results/fire_alerts.csv (one row per alert on a fire), results/fire_scars.pkl
"""
import glob, json, os, pickle
import numpy as np, pandas as pd
from shapely.geometry import shape, Point
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
import pyproj

ROOT = '/mnt/project-files'
V2 = f'{ROOT}/fire-alert-scars/reference/v2_2026-10-16'
OUT = f'{ROOT}/research/big-fires/results'
to_utm = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform

d = json.load(open(f'{V2}/firms_event_scars.geojson'))
props = pd.DataFrame([f['properties'] for f in d['features']])
geoms = [transform(to_utm, shape(f['geometry'])).buffer(0) for f in d['features']]
props['date'] = pd.to_datetime(props['date'])
n = len(geoms)
tree = STRtree(geoms)
parent = list(range(n))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]; i = parent[i]
    return i
for i, g in enumerate(geoms):
    for j in tree.query(g):
        j = int(j)
        if j <= i: continue
        if abs((props.date[i] - props.date[j]).days) > 3: continue
        inter = g.intersection(geoms[j]).area
        if inter >= 0.3 * min(g.area, geoms[j].area):
            parent[find(i)] = find(j)
props['fire'] = [find(i) for i in range(n)]
props['fire'] = props.fire.astype('category').cat.codes

# raw alerts
rows = []
for f in sorted(glob.glob(f'{ROOT}/fire-alert-scars/alerts/*.csv')):
    sat = os.path.basename(f).rsplit('_', 1)[0]
    a = pd.read_csv(f)
    if len(a) == 0: continue
    a['sat'] = sat
    rows.append(a[['latitude', 'longitude', 'acq_date', 'acq_time', 'frp', 'sat', 'daynight'] +
                  (['scan', 'track'] if 'scan' in a else [])])
al = pd.concat(rows, ignore_index=True)
print('alerts', len(al), 'missing time', al.acq_time.isna().sum())
al = al.dropna(subset=['acq_time', 'latitude', 'longitude']).reset_index(drop=True)
al['t'] = pd.to_datetime(al.acq_date) + pd.to_timedelta(al.acq_time.astype(int) // 100, 'h') + \
          pd.to_timedelta(al.acq_time.astype(int) % 100, 'min')
x, y = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform(al.longitude.values, al.latitude.values)
al['x'], al['y'] = x, y
al['date'] = pd.to_datetime(al.acq_date)
apts = [Point(xx, yy) for xx, yy in zip(x, y)]
atree = STRtree(apts)

fires, falerts, scars = [], [], {}
for fid, grp in props.groupby('fire'):
    poly = unary_union([geoms[i] for i in grp.index]).buffer(0)
    d0, d1 = grp.date.min(), grp.date.max()
    zone = poly.buffer(200)
    idx = [int(k) for k in atree.query(zone, predicate='contains')]
    sub = al.iloc[idx]
    sub = sub[(sub.date >= d0 - pd.Timedelta(days=1)) & (sub.date <= d1 + pd.Timedelta(days=2))].copy()
    sub = sub.sort_values('t')
    v = sub[sub.sat != 'modis'].copy()
    # looks: VIIRS alerts within 2 h of the previous one
    if len(v):
        look = (v.t.diff() > pd.Timedelta(hours=2)).cumsum()
        v['look'] = look.values
        lt = v.groupby('look').t.median()
        v['look_t'] = v.look.map(lt)
    sub = sub.merge(v[['look', 'look_t']], left_index=True, right_index=True, how='left') if len(v) else sub.assign(look=np.nan, look_t=pd.NaT)
    sub['fire'] = fid
    falerts.append(sub)
    scars[fid] = poly
    fires.append(dict(fire=fid, n_events=len(grp), events=';'.join(grp.event_id), date0=d0.date(), date1=d1.date(),
                      month=d0.month, season=d0.year, area_ha=poly.area / 1e4,
                      n_viirs=len(v), n_modis=int((sub.sat == 'modis').sum()),
                      n_looks=int(v.look.nunique()) if len(v) else 0,
                      hours=(v.t.max() - v.t.min()).total_seconds() / 3600 if len(v) else 0,
                      sats=','.join(sorted(v.sat.unique())) if len(v) else '',
                      still_at_edge=bool(grp.still_at_edge.fillna(False).astype(bool).any()),
                      faint=bool((grp.status == 'scar_faint').all()),
                      cx=poly.centroid.x, cy=poly.centroid.y))
F = pd.DataFrame(fires)
A = pd.concat(falerts, ignore_index=True)
F.to_csv(f'{OUT}/fires.csv', index=False)
A.to_csv(f'{OUT}/fire_alerts.csv', index=False)
pickle.dump(scars, open(f'{OUT}/fire_scars.pkl', 'wb'))
print(len(props), 'events ->', len(F), 'fires')
print(F[['area_ha', 'n_viirs', 'n_looks', 'hours', 'n_events']].describe(percentiles=[.5, .75, .9, .95, .99]).round(1))
for amin, lmin in [(100, 3), (200, 3), (200, 4), (300, 4), (500, 4)]:
    s = F[(F.area_ha >= amin) & (F.n_looks >= lmin) & ~F.still_at_edge]
    print(f'area>={amin} looks>={lmin}: {len(s)} fires, median alerts {s.n_viirs.median()}')
