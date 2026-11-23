"""Fire travel direction from a 30 m snapshot: scar edge + hot line (Akkshay 20:14Z), on the Ratapani mid-fire chips.
Data already in the cloud: fuel-map/ratapani/timing/chips/*.npz (20 m grid, burn_2017.tif transform, EPSG:32643):
  S final scar, bym burned by the scene minute (NBR drop), hot 30 m hot pixels in the scene; midscar.parquet (scene time T).
Truth: where the fire went AFTER the scene = centroid of the scar not yet burned (S & ~bym) minus centroid of bym
  (the final scar is ~87% burned within 24 h of first detection, timing README s1, so this is mostly next-day growth).
Predictors, all as directions; score = share within 45 deg of truth (random 25%) and median angle (random 90):
  A scar edge + hot line   = centroid(hot) - centroid(bym)       [burned ground behind, live line in front]
  B dots only              = centroid(latest VIIRS look before T) - centroid(earlier VIIRS looks) (alerts within 1.5 km of S)
  C hot line vs dots       = centroid(hot) - centroid(all VIIRS dots before T)
  N null for A             = a random pixel on the edge of bym - centroid(bym) (expected share over 200 draws per scene),
                             i.e. "knowing the burnt patch but not where on its edge the fire is"
No model is fitted, so nothing is trained on the test scenes.
Output: results/scar_edge_direction.json, results/scar_edge_direction_rows.csv"""
import glob, json, os, numpy as np, pandas as pd, rasterio
from scipy import ndimage
from pyproj import Transformer
T0 = '/mnt/project-files/fuel-map/ratapani/timing'; R = '/mnt/project-files/research/big-fires/results'
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as s: TR = s.transform
M = pd.read_parquet(f'{T0}/midscar.parquet'); M = M[M.status == 'ok']
al = pd.concat([pd.read_csv(f) for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv')], ignore_index=True)
al['t'] = pd.to_datetime(al.acq_date + ' ' + al.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True); al['x'], al['y'] = to43.transform(al.longitude.values, al.latitude.values)
al['look'] = al.satellite.astype(str) + al.t.dt.strftime('%Y%m%d%H')
def ang(a, b):
    return float(np.degrees(np.abs(np.arctan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))))
rng = np.random.default_rng(0); rows = []
for f in sorted(glob.glob(f'{T0}/chips/*.npz')):
    ev = int(os.path.basename(f).split('_')[0]); scene = os.path.basename(f)[len(str(ev)) + 1:-4]
    m = M[(M.event == ev) & (M.scene.str[:40] == scene)]
    if m.empty: continue
    m = m.iloc[0]; z = np.load(f); S, B, H = z['S'], z['bym'] & z['S'], z['hot']
    rem = S & ~B
    if B.sum() < 10 or H.sum() < 3 or rem.sum() < 50: continue      # need burnt ground, a live line, and >=2 ha still to burn
    rr, cc = np.mgrid[0:S.shape[0], 0:S.shape[1]]
    X = TR.c + (z['j0'] + cc + 0.5) * 20; Y = TR.f - (z['i0'] + rr + 0.5) * 20
    c = lambda k: np.array([X[k].mean(), Y[k].mean()])
    cb, ch, cr = c(B), c(H), c(rem); truth = cr - cb
    pA = ch - cb
    edge = B & ~ndimage.binary_erosion(B); ex, ey = X[edge], Y[edge]; k = rng.integers(0, len(ex), 200)
    nullA = np.mean([ang(np.array([ex[i], ey[i]]) - cb, truth) <= 45 for i in k])
    T = pd.Timestamp(m['T']); x0, x1, y0, y1 = X[S].min() - 1500, X[S].max() + 1500, Y[S].min() - 1500, Y[S].max() + 1500
    d = al[(al.x.between(x0, x1)) & (al.y.between(y0, y1)) & (al.t < T) & (al.t >= T - pd.Timedelta(days=3))]
    rec = dict(event=ev, scene=scene, T=T, burned_ha=B.sum() * 0.04, remain_ha=rem.sum() * 0.04, hot_px=int(H.sum()),
               remain_dist_m=float(np.hypot(*truth)), ang_A=ang(pA, truth), null_A_within45=nullA)
    if d.look.nunique() >= 2:
        lk = d.sort_values('t').look.unique(); last = d[d.look == lk[-1]]; prev = d[d.look != lk[-1]]
        rec['ang_B'] = ang(np.array([last.x.mean() - prev.x.mean(), last.y.mean() - prev.y.mean()]), truth)
    if len(d): rec['ang_C'] = ang(ch - np.array([d.x.mean(), d.y.mean()]), truth)
    rows.append(rec)
D = pd.DataFrame(rows); D.to_csv(f'{R}/scar_edge_direction_rows.csv', index=False)
def sc(col, df):
    v = df[col].dropna(); b = [np.mean(rng.choice(v.values, len(v)) <= 45) for _ in range(2000)]
    return dict(n=int(len(v)), within_45=round(float((v <= 45).mean()), 3), ci=[round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)], median_angle=round(float(v.median()), 1))
out = dict(scenes=int(len(D)), fires=int(D.event.nunique()), random_within_45=0.25,
           A_scar_edge_plus_hot_line=sc('ang_A', D), N_random_point_on_burnt_edge_within_45=round(float(D.null_A_within45.mean()), 3),
           B_dots_only=sc('ang_B', D), C_hot_line_vs_dots=sc('ang_C', D))
big = D[D.remain_dist_m >= 300]
out['remaining_burn_300m_plus_away'] = dict(A=sc('ang_A', big), N=round(float(big.null_A_within45.mean()), 3), B=sc('ang_B', big))
both = D.dropna(subset=['ang_B'])
out['same_scenes_A_vs_B'] = dict(n=len(both), A=round(float((both.ang_A <= 45).mean()), 3), B=round(float((both.ang_B <= 45).mean()), 3))
json.dump(out, open(f'{R}/scar_edge_direction.json', 'w'), indent=1, default=str); print(json.dumps(out, indent=1, default=str))
