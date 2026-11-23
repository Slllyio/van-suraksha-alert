"""Per-division season fire counts (S-NPP, type 0, 15 Feb-31 May, 2014-2026) + NASA POWER monthly weather at each division centroid.
Out: div_season.csv, power_monthly.csv"""
import json, urllib.request, time, pandas as pd, geopandas as gpd, numpy as np
P = '/mnt/project-files/'; O = P + 'research/ceiling/outlook/'
D = gpd.read_file(P + 'fire-alert-scars/mp/out/mp_divisions.geojson'); print(D.columns.tolist(), len(D))
name = [c for c in D.columns if c.lower() in ('division', 'div_name', 'name', 'division_name')][0]
D = D[[name, 'geometry']].rename(columns={name: 'division'}).dissolve('division').reset_index()
rows = []
for y in range(2014, 2027):
    a = pd.read_csv(P + f'fire-alert-scars/alerts_mp/viirs-snpp_{y}.csv', usecols=['latitude', 'longitude', 'acq_date', 'type'])
    a = a[a.type == 0]; d = pd.to_datetime(a.acq_date); md = d.dt.month * 100 + d.dt.day; a = a[(md >= 215) & (md <= 531)]
    g = gpd.GeoDataFrame(a, geometry=gpd.points_from_xy(a.longitude, a.latitude), crs=4326)
    j = gpd.sjoin(g, D.to_crs(4326), predicate='within')
    # fire "square-days": unique ~375 m points per day are close enough; count pixel-days
    c = j.groupby('division').size(); rows += [{'division': k, 'year': y, 'n': int(v)} for k, v in c.items()]
S = pd.DataFrame(rows).pivot(index='division', columns='year', values='n').fillna(0).stack().rename('n').reset_index()
S.to_csv(O + 'div_season.csv', index=False); print(S.groupby('year').n.sum())
cent = D.to_crs(32643).centroid.to_crs(4326)
W = []
for dv, pt in zip(D.division, cent):
    u = f'https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR,T2M_MAX,RH2M,GWETROOT&community=AG&longitude={pt.x:.3f}&latitude={pt.y:.3f}&start=2013&end=2026&format=JSON'
    for k in range(4):
        try: p = json.load(urllib.request.urlopen(u, timeout=60))['properties']['parameter']; break
        except Exception as e: time.sleep(3 * (k + 1)); p = None
    if p is None: print('fail', dv); continue
    for var, ser in p.items():
        for ym, v in ser.items():
            if ym[4:] != '13': W.append({'division': dv, 'var': var, 'year': int(ym[:4]), 'month': int(ym[4:]), 'v': v})
pd.DataFrame(W).to_csv(O + 'power_monthly.csv', index=False); print('power rows', len(W))
