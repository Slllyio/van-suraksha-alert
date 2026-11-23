"""Q4 follow-up: per tr3 patch, the two sides that the escape test says matter (n4b): the uphill side (500 m elevation within 2 km
of the patch centre) and the side with the most often-burnt forest within 3 km outside the patch (nine-season count, 120 m).
Adds uphill_side and repeat_fuel_side to out/n4_patches.csv and to joint_plan/out/j1_patches.csv/.geojson."""
import os, sys, numpy as np, pandas as pd, geopandas as gpd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/'); import cb0 as B
from pyproj import Transformer
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'; JP = '/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/'
OCT = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
def octant(b): return OCT[int(((b + 22.5) % 360) // 45)] if np.isfinite(b) else ''
S = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet', columns=['row', 'col', 'elev']); EL = np.full((1332, 1829), np.nan); EL[S.row, S.col] = S.elev
FW = Transformer.from_crs(4326, 32643, always_xy=True)
P = pd.read_csv(OUT + 'n4_patches.csv'); R = 25; yy, xx = np.mgrid[-R:R + 1, -R:R + 1]; dist = np.hypot(xx, yy); ring = (dist <= R) & (dist >= 2)
ey, ex = np.mgrid[-4:5, -4:5]; de_d = np.hypot(ex, ey); em = (de_d >= 1) & (de_d <= 4)
up, fuel = {}, {}
for key, g in P.groupby('key'):
    L, FOR = B.load_div(key); Z = np.load(B.SC26 + f'patches_{key}.npz'); lab = Z['lab_tr3']; cnt = Z['cnt_all'].astype(float); fb = Z['fb'] > 0; H2, W2 = lab.shape
    for r in g.itertuples():
        x, y = FW.transform(r.lon, r.lat); pr, pc = int((L['y1'] - y) / 120), int((x - L['x0']) / 120)
        r0, r1, c0, c1 = max(pr - R, 0), min(pr + R + 1, H2), max(pc - R, 0), min(pc + R + 1, W2)
        if r1 - r0 == 2 * R + 1 and c1 - c0 == 2 * R + 1:
            w = np.where((lab[r0:r1, c0:c1] != r.pid) & ring & fb[r0:r1, c0:c1], cnt[r0:r1, c0:c1], 0.0)
            fuel[r.Index] = np.degrees(np.arctan2((w * xx).sum(), -(w * yy).sum())) % 360 if w.sum() > 0 else np.nan
        gr, gc = int((2996000 - y) / 500), int((x - 399000) / 500); e = EL[gr - 4:gr + 5, gc - 4:gc + 5]
        if e.shape == (9, 9) and np.isfinite(e).sum() > 20:
            ref = e[4, 4] if np.isfinite(e[4, 4]) else np.nanmean(e); m = em & np.isfinite(e); wv = np.clip(e[m] - ref, 0, None)
            up[r.Index] = np.degrees(np.arctan2((wv * ex[m]).sum(), -(wv * ey[m]).sum())) % 360 if wv.sum() > 0 else np.nan
P['uphill_bearing'] = pd.Series(up); P['repeat_fuel_bearing'] = pd.Series(fuel)
P['uphill_side'] = P.uphill_bearing.map(octant); P['repeat_fuel_side'] = P.repeat_fuel_bearing.map(octant)
P.to_csv(OUT + 'n4_patches.csv', index=False)
for f in ('j1_patches.csv',):
    J = pd.read_csv(JP + f); J = J.drop(columns=[c for c in ('uphill_side', 'repeat_fuel_side', 'feb_downwind_side') if c in J]).merge(P[['key', 'patch', 'uphill_side', 'repeat_fuel_side', 'feb_downwind_side']], on=['key', 'patch'], how='left'); J.to_csv(JP + f, index=False)
G = gpd.read_file(JP + 'j1_patches.geojson'); G = G.drop(columns=[c for c in ('uphill_side', 'repeat_fuel_side', 'feb_downwind_side') if c in G]).merge(P[['key', 'patch', 'uphill_side', 'repeat_fuel_side', 'feb_downwind_side']], on=['key', 'patch'], how='left'); G.to_file(JP + 'j1_patches.geojson', driver='GeoJSON')
b = P[P.role_S3 == 'burn']; print('first programme: uphill side', b.uphill_side.value_counts().to_dict()); print('repeat-fuel side', b.repeat_fuel_side.value_counts().to_dict()); print('uphill == fuel side', (b.uphill_side == b.repeat_fuel_side).mean().round(2))
