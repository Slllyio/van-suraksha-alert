"""Step 3: truth sizes per fire.
 (A) scar truth: union of the burn-scar outlines of the fire's scar events (all-MP scar runs: tiger reserves 2017-25, rest of MP
     2023-25 so far, the check sample; Ratapani outlines v2 2017-26 replace them inside Ratapani). A fire is scar-measured only
     if every forest event it touches within 7 days of its first look has a finished scar check.
 (B) VIIRS footprint truth: number of distinct 375 m cells with a VIIRS dot within 7 days of the first look (computed in b4).
Out (scratch): fire_scar.parquet"""
import json
import numpy as np, pandas as pd, geopandas as gpd, shapely
from shapely.geometry import shape
ROOT = '/mnt/project-files'; MP = f'{ROOT}/fire-alert-scars/mp/out'; RV = f'{ROOT}/fire-alert-scars/reference/v2_2026-10-16'
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
AEA = '+proj=aea +lat_1=22 +lat_2=25 +lat_0=23.5 +lon_0=78.5 +datum=WGS84 +units=m'
P = pd.read_parquet(f'{SC}/pts_f.parquet')
t0 = P.groupby('fire').t.transform('min'); P = P[(P.t - t0) <= pd.Timedelta('7D')]
SEN = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'}
def key(d, sen):
    return (d.latitude.round(4).astype(str) + '_' + d.longitude.round(4).astype(str) + '_' + d.acq_date.astype(str) + '_'
            + d.acq_time.astype(float).astype(int).astype(str) + '_' + sen)
P['k'] = key(P, P.sensor)
# all-MP events
AE = pd.read_csv(f'{MP}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'sensor', 'event_id'])
AE = AE[AE.sensor.isin(SEN)]; AE['k'] = key(AE, AE.sensor.map(SEN)); AE = AE.drop_duplicates('k')
EV = pd.read_csv(f'{MP}/mp_events.csv', usecols=['event_id', 'forest'])
forest_ev = set(EV.event_id[EV.forest])
# Ratapani v2 lookup
RL = pd.read_csv(f'{RV}/firms_alert_scar_lookup.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'sensor', 'event_id'])
RL = RL[RL.sensor.isin(SEN)].dropna(subset=['acq_time']); RL['k'] = key(RL, RL.sensor.map(SEN)); RL = RL.drop_duplicates('k')
P = P.merge(AE[['k', 'event_id']], on='k', how='left').merge(RL[['k', 'event_id']].rename(columns={'event_id': 'rev'}), on='k', how='left')
print('points matched to an MP event', round(P.event_id.notna().mean(), 3), 'to a Ratapani v2 event', round(P.rev.notna().mean(), 3))
# scar status per event
st = []
for f in ('scars_mp_hist.csv', 'scars_tiger_reserves.csv', 'scars_sample.csv'):
    r = pd.read_csv(f'{SC}/{f}' if f == 'scars_mp_hist.csv' else f'{MP}/{f}', usecols=['event_id', 'status', 'scar_ha', 'touches_chip_edge'], low_memory=False); r['src'] = f
    st.append(r)
ST = pd.concat(st).drop_duplicates('event_id')
ST = ST[ST.status.isin(['scar', 'scar_faint', 'no_scar_seen'])]
RS = gpd.read_file(f'{RV}/firms_event_scars.geojson')[['event_id', 'status', 'scar_ha', 'still_at_edge', 'geometry']]
RS = RS[RS.status.isin(['scar', 'scar_faint', 'no_scar_seen'])]
# per fire: which events, are all measured?
rat_fire = set(P.fire[P.rev.notna()])
P['in_rat'] = P.fire.isin(rat_fire)
E1 = P[~P.in_rat & P.event_id.isin(forest_ev)].groupby('fire').event_id.unique()
E2 = P[P.in_rat & P.rev.notna()].groupby('fire').rev.unique()
done_mp = set(ST.event_id); done_r = set(RS.event_id)
ok1 = E1[E1.apply(lambda e: all(x in done_mp for x in e))]
ok2 = E2[E2.apply(lambda e: all(x in done_r for x in e))]
print('fires with forest MP events', len(E1), 'all measured', len(ok1), '| Ratapani fires', len(E2), 'all measured', len(ok2))
# geometries for events with a scar
need1 = set(np.concatenate(ok1.values)) if len(ok1) else set()
G = {}
import sys; sys.path.insert(0, f'{ROOT}/fire-alert-scars/mp/scripts'); from read_geom import read_geom
g = read_geom(f'{SC}/scars_mp_hist_geom.csv.gz')  # snapshot copied to scratch 17 Oct (the run is still appending)
g = g[g.event_id.isin(need1)]
for e, w in zip(g.event_id, g.geometry): G[e] = shapely.from_wkt(w)
t = gpd.read_file(f'{MP}/tiger_reserve_scars.geojson'); t = t[t.event_id.isin(need1)]
for e, w in zip(t.event_id, t.geometry): G.setdefault(e, w)
s = pd.read_csv(f'{MP}/scars_sample.csv', usecols=['event_id', 'geometry']).dropna(); s = s[s.event_id.isin(need1)]
for e, w in zip(s.event_id, s.geometry): G.setdefault(e, shape(json.loads(w)))
GR = dict(zip(RS.event_id, RS.geometry))
ha1 = ST.set_index('event_id').scar_ha.fillna(0).to_dict(); edge1 = ST.set_index('event_id').touches_chip_edge.fillna(False).astype(bool).to_dict()
ha2 = RS.set_index('event_id').scar_ha.fillna(0).to_dict(); edge2 = RS.set_index('event_id').still_at_edge.fillna(False).astype(bool).to_dict()
def to_aea(geoms):
    return gpd.GeoSeries(geoms, crs=4326).to_crs(AEA)
rows = []
for src, ok, GG, HA, ED in (('mp', ok1, G, ha1, edge1), ('ratapani_v2', ok2, GR, ha2, edge2)):
    for f, evs in ok.items():
        gs = [GG[e] for e in evs if e in GG and GG[e] is not None and HA.get(e, 0) > 0]
        mx = max([HA.get(e, 0) for e in evs] + [0])
        if len(gs) == 0: area = 0.0
        elif len(gs) == 1: area = HA[[e for e in evs if e in GG and HA.get(e, 0) > 0][0]]
        else: area = None
        rows.append(dict(fire=f, src=src, n_events=len(evs), n_scar_events=len(gs), max_event_ha=mx, edge=any(ED.get(e, False) for e in evs),
                         scar_ha=area, _g=gs if area is None else None))
R = pd.DataFrame(rows)
mult = R.scar_ha.isna()
print('fires needing a union', mult.sum())
for i in R.index[mult]:
    u = shapely.union_all(to_aea(R.at[i, '_g']).values)
    R.at[i, 'scar_ha'] = u.area / 1e4
R = R.drop(columns='_g')
R.to_parquet(f'{SC}/fire_scar.parquet')
print(R.groupby('src').agg(fires=('fire', 'size'), big200=('scar_ha', lambda s: (s >= 200).mean()), med=('scar_ha', 'median'), edge=('edge', 'mean')))
