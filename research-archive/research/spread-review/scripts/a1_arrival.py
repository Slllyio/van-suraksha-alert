"""Item 2: per-fire arrival-time map ("when did the fire reach this 20 m pixel"), validated on the fuel thread's
mid-fire Sentinel-2/Landsat snapshots (fuel-map/ratapani/timing/chips: S = scar, bym = burned by scene minute).
Arrival model: T(x) = min over detections j of [ t_j - lead*(j in first look) + dist(x, footprint_j) / v ],
footprint_j = the VIIRS pixel (scan x track km) around point j, dist = 0 inside it. v and lead chosen leave-one-season-out.
Baselines: 'step' (whole scar burned once first detected), 'footprints' (burned = inside a footprint seen by then).
Out: arrival/validation.json, arrival/scene_scores.parquet"""
import pandas as pd, numpy as np, glob, sys, json, rasterio, os
from scipy.spatial import cKDTree
S = sys.argv[1]; OUT = sys.argv[2]
TD = '/mnt/project-files/fuel-map/ratapani/timing/'
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as r: TR = r.transform
A = pd.read_parquet(S + '/tracks.parquet')
A['scan'] = A.scan.fillna(0.375).clip(lower=0.3); A['track'] = A.track.fillna(0.375).clip(lower=0.3)
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
V = [5, 10, 15, 20, 30, 45, 60, 90]; LEAD = [0, 2, 4, 8, 12]
tree = cKDTree(A[['x', 'y']].values)
rows, maps = [], []
for f in sorted(glob.glob(TD + 'chips/*.npz')):
    b = os.path.basename(f); ev = int(b.split('_')[0]); sc = b[len(str(ev)) + 1:-4]
    m = ms[(ms.event == ev) & (ms.scene.str[:40] == sc)]
    if not len(m): continue
    m = m.iloc[0]; z = np.load(f)
    Sm, bym, ok = z['S'], z['bym'], z['ok']; i0, j0 = int(z['i0']), int(z['j0'])
    rr, cc = np.where(Sm & ok)
    if len(rr) < 20: continue
    xs, ys = rasterio.transform.xy(TR, rr + i0, cc + j0); px, py = np.array(xs), np.array(ys)
    # the fire: detections within 1 km of the scar pixels, between t_first-1 d and t_last+1 d of the snapshot table
    near = np.unique(np.concatenate(tree.query_ball_point(np.c_[px[::5], py[::5]], 1000)))
    if not len(near): continue
    d = A.iloc[near]; d = d[(d.t >= m.t_first - pd.Timedelta(hours=26)) & (d.t <= m.t_last + pd.Timedelta(hours=26))]
    if not len(d): continue
    fire = d.fire.value_counts().index[0]; d = A[A.fire == fire]
    T = m['T']; first_t = d.t.min()
    th = ((d.t - T).dt.total_seconds() / 3600).values          # detection time relative to scene, hours
    isfirst = (d.look == d.sort_values('t').look.iloc[0]).values
    # distance of every scar pixel to every footprint rectangle
    hx, hy = d.scan.values * 500, d.track.values * 500        # half sizes (m); track ~ along-track (north-south approx)
    dx = np.maximum(np.abs(px[:, None] - d.x.values[None]) - hx[None], 0); dy = np.maximum(np.abs(py[:, None] - d.y.values[None]) - hy[None], 0)
    dist = np.hypot(dx, dy)
    obs = bym[rr, cc]
    res = dict(event=ev, scene=sc, season=int(m.season), fire=int(fire), n_px=len(rr), obs_frac=float(obs.mean()),
               h_after_first=float((T - first_t).total_seconds() / 3600))
    res['step'] = float(((T > first_t) == obs).mean()); res['step_frac'] = float(T > first_t)
    inside_seen = ((dist == 0) & (th[None] <= 0)).any(1); res['footprints'] = float((inside_seen == obs).mean()); res['footprints_frac'] = float(inside_seen.mean())
    for v in V:
        for L in LEAD:
            Tx = (th[None] - L * isfirst[None] + dist / v).min(1)
            pred = Tx <= 0
            res[f'acc_{v}_{L}'] = float((pred == obs).mean()); res[f'frac_{v}_{L}'] = float(pred.mean())
    rows.append(res)
X = pd.DataFrame(rows); X.to_parquet(OUT + '/scene_scores.parquet')
grid = [f'{v}_{L}' for v in V for L in LEAD]
lo = []
for s in sorted(X.season.unique()):
    tr, te = X[X.season != s], X[X.season == s]
    best = max(grid, key=lambda k: tr['acc_' + k].mean())
    lo.append(te.assign(acc=te['acc_' + best], frac=te['frac_' + best], best=best))
lo = pd.concat(lo)
R = dict(n_scenes=len(X), n_fires=int(X.fire.nunique()),
         pixel_accuracy=dict(arrival_LOSO=round(lo.acc.mean(), 3), step=round(X.step.mean(), 3), footprints=round(X.footprints.mean(), 3)),
         burned_fraction_abs_error_median=dict(arrival_LOSO=round((lo.frac - lo.obs_frac).abs().median(), 3),
                                               step=round((X.step_frac - X.obs_frac).abs().median(), 3),
                                               footprints=round((X.footprints_frac - X.obs_frac).abs().median(), 3)),
         burned_fraction_corr=dict(arrival_LOSO=round(np.corrcoef(lo.frac, lo.obs_frac)[0, 1], 3), footprints=round(np.corrcoef(X.footprints_frac, X.obs_frac)[0, 1], 3)),
         chosen=lo.groupby('season').best.first().to_dict(),
         best_all=max(grid, key=lambda k: X['acc_' + k].mean()))
json.dump(R, open(OUT + '/validation.json', 'w'), indent=1, default=str); print(json.dumps(R, indent=1, default=str))
