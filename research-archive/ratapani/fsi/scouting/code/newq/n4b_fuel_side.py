"""Q4 follow-up: if wind does not say where a fire leaves a patch, does the ground? For each escape in n4_escapes.csv, the side of
the ignition point with the most often-burnt forest within 3 km outside the patch (nine-season burn count, 120 m), the uphill side
(500 m elevation within 2 km) and the side with the most forest; each against the escape bearing. Out: out/n4b_ground_side.csv"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/'); import cb0 as B
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
E = pd.read_csv(OUT + 'n4_escapes.csv'); S = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet', columns=['cell', 'row', 'col', 'elev'])
EL = np.full((1332, 1829), np.nan); EL[S.row, S.col] = S.elev
from pyproj import Transformer; FW = Transformer.from_crs(4326, 32643, always_xy=True)
def angdiff(a, b): return ((a - b + 180) % 360) - 180
R = 25  # 120 m cells = 3 km
yy, xx = np.mgrid[-R:R + 1, -R:R + 1]; dist = np.hypot(xx, yy); ring = (dist <= R) & (dist >= 2)
rows = []
for key, g in E.groupby('key'):
    L, FOR = B.load_div(key); Z = np.load(B.SC26 + f'patches_{key}.npz'); lab = Z['lab_tr3']; cnt = Z['cnt_all'].astype(float); fb = Z['fb'] > 0
    H2, W2 = lab.shape
    for r in g.itertuples():
        x, y = FW.transform(r.lon, r.lat); pr, pc = int((L['y1'] - y) / 120), int((x - L['x0']) / 120)
        r0, r1, c0, c1 = pr - R, pr + R + 1, pc - R, pc + R + 1
        if r0 < 0 or c0 < 0 or r1 > H2 or c1 > W2: continue
        outp = (lab[r0:r1, c0:c1] != r.patch) & ring & fb[r0:r1, c0:c1]
        def side(wt):
            w = np.where(outp, wt, 0.0)
            if w.sum() <= 0: return np.nan
            return np.degrees(np.arctan2((w * xx).sum(), -(w * yy).sum())) % 360
        fuel = side(cnt[r0:r1, c0:c1]); forest = side(np.ones_like(cnt[r0:r1, c0:c1]))
        # uphill: 500 m grid, 2 km
        gr, gc = int((2996000 - y) / 500), int((x - 399000) / 500); e = EL[gr - 4:gr + 5, gc - 4:gc + 5]
        if e.shape == (9, 9) and np.isfinite(e).sum() > 20:
            ey, ex = np.mgrid[-4:5, -4:5]; d = np.hypot(ex, ey); m = (d >= 1) & (d <= 4) & np.isfinite(e); de = e[m] - np.nanmean(e[(d == 0)]) if np.isfinite(e[4, 4]) else e[m] - np.nanmean(e)
            w = np.clip(de, 0, None); up = np.degrees(np.arctan2((w * ex[m]).sum(), -(w * ey[m]).sum())) % 360 if w.sum() > 0 else np.nan
        else: up = np.nan
        rows.append(dict(fire=r.fire, key=key, out_ha=r.out_ha, esc=r.esc_bear, fuel_side=fuel, forest_side=forest, uphill=up, wind=r.wind_to))
D = pd.DataFrame(rows)
res = []
for c in ('fuel_side', 'forest_side', 'uphill', 'wind'):
    d = D.dropna(subset=[c]); a = np.abs(angdiff(d.esc, d[c]))
    big = d[d.out_ha >= 200]; ab = np.abs(angdiff(big.esc, big[c]))
    res.append(dict(side=c, fires=len(d), within_45=(a <= 45).mean(), within_90=(a <= 90).mean(), mean_cos=np.cos(np.radians(a)).mean(), big_fires=len(big), big_within_90=(ab <= 90).mean()))
Rr = pd.DataFrame(res); Rr.to_csv(OUT + 'n4b_ground_side.csv', index=False); print(Rr.round(3).to_string(index=False))
