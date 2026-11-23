"""Ratapani fires (big-fires thread: v2 events joined into 3,557 fires, research/big-fires/results/fires.csv) with the new
all-MP MODIS SP points attached: a MODIS point belongs to a fire if it lies inside the fire's scar + 500 m (MODIS 1 km pixel;
big-fires used +200 m) and falls between the day before the first event and 2 days after the last (the big-fires window).
VIIRS = big-fires fire_alerts.csv (non-MODIS). Slots = MP-wide VIIRS schedule (m1).
Out (scratch): rat_viirs.parquet, rat_modis.parquet. Needs fire_scars.pkl from continuity c0b_scars.py in ML_SCRATCH."""
import os, pickle, numpy as np, pandas as pd
from shapely import STRtree, points
S = os.environ['ML_SCRATCH']; BF = '/mnt/project-files/research/big-fires/results'
SC = pickle.load(open(f'{S}/fire_scars.pkl', 'rb'))
F = pd.read_csv(f'{BF}/fires.csv', parse_dates=['date0', 'date1'])
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
SCH = pd.read_parquet(f'{S}/schedule.parquet')
k = np.searchsorted(SCH.t.values, A.t.values, side='right') - 1
A['slot'] = SCH.slot.values[k]; A = A[(A.t - SCH.t.values[k]) <= pd.Timedelta(hours=2.5)]
M = pd.read_parquet(f'{S}/modis_mp.parquet')
M = M[(M.x > 700000) & (M.x < 860000) & (M.y > 2480000) & (M.y < 2600000)].reset_index(drop=True)
fids = F.fire.values; polys = [SC[f].buffer(500) for f in fids]
tree = STRtree(polys); qi, qp = tree.query(points(M.x.values, M.y.values), predicate='intersects')
pair = pd.DataFrame({'m': qi, 'fire': fids[qp]})
pair = pair.merge(F[['fire', 'date0', 'date1']], on='fire')
tl = (M.t + pd.Timedelta(hours=5.5)).dt.normalize().values[pair.m.values]
pair = pair[(tl >= pair.date0.values - np.timedelta64(1, 'D')) & (tl <= pair.date1.values + np.timedelta64(2, 'D'))]
# a MODIS point inside two fires' windows goes to the fire whose VIIRS alerts are nearest in time
At = A.groupby('fire').t.agg(['min', 'max'])
mt = M.t.values[pair.m.values]
Ar = At.reindex(pair.fire.values); Ar = Ar.fillna(Ar.min().min())
gap = np.maximum((Ar['min'].values - mt) / np.timedelta64(1, 'h'), 0) + np.maximum((mt - Ar['max'].values) / np.timedelta64(1, 'h'), 0)
pair['g'] = gap; pair = pair.sort_values('g').drop_duplicates('m')
RM = M.loc[pair.m.values].copy(); RM['fire'] = pair.fire.values; RM['kind'] = RM.sensor + '_' + RM.daynight
A.to_parquet(f'{S}/rat_viirs.parquet'); RM.to_parquet(f'{S}/rat_modis.parquet'); F.to_parquet(f'{S}/rat_fires.parquet')
old = pd.read_csv(f'{BF}/detections.csv'); old = old[old.sensor.str.contains('MODIS')]
print('MODIS SP points on Ratapani fires:', len(RM), RM.kind.value_counts().to_dict(), '| big-fires detections.csv MODIS:', len(old))
print('fires with any MODIS: new', RM.fire.nunique(), 'old', old.fire.nunique(), '| big fires with MODIS new', RM[RM.fire.isin(F.fire[F.big])].fire.nunique())
