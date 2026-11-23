"""Statewide regions: per 500 m cell and season 2022-25, share of the cell inside burn-scar outlines of fires seen on/after 15 Feb
('scar' status; rest-of-MP history run + tiger-reserve run), and whether any scar from a fire before 15 Feb touched the cell (dropped later).
Rasterised at 25 m in EPSG:32643.  Out: mp/labels.parquet (region, season, cell, share, early)"""
import json, numpy as np, pandas as pd, geopandas as gpd, shapely, rasterio.features as rf
from rasterio.transform import from_origin
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
O = '/mnt/project-files/fire-alert-scars/mp/out/'
REGS = json.load(open(f'{SP}/mp/regions.json'))
cols = ['event_id', 'acq_date', 'x', 'y']
ev = pd.concat([pd.read_csv(O + 'set_rest_of_mp.csv', usecols=cols), pd.read_csv(O + 'set_tiger_reserves.csv', usecols=cols)]).drop_duplicates('event_id')
ev['d'] = pd.to_datetime(ev.acq_date); ev = ev[(ev.d.dt.year >= 2022) & (ev.d.dt.year <= 2025)]
keep = np.zeros(len(ev), bool)
for g in REGS.values():
    keep |= (ev.x > g['X0'] - 5000) & (ev.x < g['X0'] + 40320 + 5000) & (ev.y > g['Y1'] - 40320 - 5000) & (ev.y < g['Y1'] + 5000)
ev = ev[keep]
h = pd.read_csv(O + 'scars_mp_hist.csv', usecols=['event_id', 'status']); h = h[h.status == 'scar']
import sys; sys.path.insert(0, '/mnt/project-files/fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom; gh = read_hist_geom(); gh = gh[gh.event_id.isin(set(h.event_id) & set(ev.event_id))].drop_duplicates('event_id', keep='last')
print('hist scars in boxes', int(h.event_id.isin(ev.event_id).sum()), 'with outline', len(gh), flush=True)
gh = gpd.GeoDataFrame(gh[['event_id']], geometry=shapely.from_wkt(gh.geometry.values), crs=4326)
gt = gpd.read_file(O + 'tiger_reserve_scars.geojson'); gt = gt[(gt.status == 'scar') & gt.event_id.isin(ev.event_id)][['event_id', 'geometry']]
G = pd.concat([gh, gt.to_crs(4326)]).drop_duplicates('event_id').merge(ev[['event_id', 'd']], on='event_id').to_crs(32643)
print('scars', len(G), 'of events', len(ev), flush=True)
rows = []
for reg, g in REGS.items():
    n = 80; X0, Y1 = g['X0'], g['Y1']; tr = from_origin(X0, Y1, 25, 25); px = n * 20
    c0 = int((X0 - 399000) / 500); r0 = int((2996000 - Y1) / 500)
    rr, cc = np.meshgrid(np.arange(r0, r0 + n), np.arange(c0, c0 + n), indexing='ij'); cid = (rr * 1829 + cc).ravel()
    for Y in range(2022, 2026):
        s = G[G.d.dt.year == Y]; late = s[s.d.dt.dayofyear >= 46]; early = s[s.d.dt.dayofyear < 46]
        def ras(gs):
            if len(gs) == 0: return np.zeros((px, px), np.uint8)
            return rf.rasterize(((geom, 1) for geom in gs.geometry), out_shape=(px, px), transform=tr, fill=0, dtype='uint8')
        L = ras(late).reshape(n, 20, n, 20).mean((1, 3)).ravel(); E = ras(early).reshape(n, 20, n, 20).max((1, 3)).ravel()
        rows.append(pd.DataFrame(dict(region=reg, season=Y, cell=cid, share=L.astype(np.float32), early=E.astype(bool))))
        print(reg, Y, 'late scars', len(late), 'mean share', round(float(L.mean()), 4), flush=True)
pd.concat(rows).to_parquet(f'{SP}/mp/labels.parquet')
