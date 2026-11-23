"""What the 70 m ECOSTRESS temperature shows on active fires (clips from b16).
Per fire-pass: background = median clear LST in a ring 1-2 km outside the scar; anomaly = LST - background; hot = anomaly
above a threshold (10 K main; 6 and 15 K as checks). Fire "visible" = >= 3 hot pixels inside the scar + 100 m and the hot
share inside the scar at least 3x the share outside.
Checks: (1) hot pixels vs the VIIRS detections of the nearest pass within 1 h: distance, share inside a 375 m block, and
        whether each VIIRS block holds a hot pixel; (2) hot pixels vs the final scar edge (front or interior);
        (3) two ECOSTRESS passes on one fire: movement of the hot front against time.
Out: results/ecostress_pass_stats.csv, results/ecostress_summary.json, figures/7_ecostress.png
"""
import os, glob, json, pickle
import numpy as np, pandas as pd
from rasterio.features import rasterize
from rasterio.transform import Affine
from scipy.spatial import cKDTree
from scipy.ndimage import distance_transform_edt
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
R = '/mnt/project-files/research/big-fires/results'; FG = '/mnt/project-files/research/big-fires/figures'
CACHE = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/ecostress'
SP = f'{R}/fire_scars.pkl' if os.path.exists(f'{R}/fire_scars.pkl') else '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/fire_scars.pkl'
S = pickle.load(open(SP, 'rb')); DT = pd.read_csv(f'{R}/detections.csv', parse_dates=['t']); F = pd.read_csv(f'{R}/fires.csv').set_index('fire')
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
M = pd.read_csv(f'{R}/ecostress_matches.csv', parse_dates=['t0']) if 'status' in pd.read_csv(f'{R}/ecostress_matches.csv', nrows=1).columns else None
rows = []; examples = []
FILES = sorted(glob.glob(f"{CACHE}/*.npz"))[:int(os.environ.get("NMAX", "100000"))]
import time; T0 = time.time()
for i_, fp in enumerate(FILES):
    if i_ % 50 == 0: print("clip", i_, round(time.time() - T0), "s", flush=True)
    fid = int(os.path.basename(fp).split('_')[0]); gid = os.path.basename(fp)[len(str(fid)) + 1:-4]
    z = np.load(fp); lst, cloud, vz = z['LST'].astype(float), z['cloud'], z['view_zenith'].astype(float); tr = Affine(*z['transform'])
    t0 = pd.Timestamp(gid.split('_')[6][:15]); night = t0.hour + 5.5 >= 18.5 or t0.hour + 5.5 < 6.5  # pass time UTC in the id
    poly = S[fid]; H, W = lst.shape
    inside = rasterize([(poly, 1)], out_shape=(H, W), transform=tr, fill=0).astype(bool)
    near = rasterize([(poly.buffer(100), 1)], out_shape=(H, W), transform=tr, fill=0).astype(bool)
    ring = rasterize([(poly.buffer(2000).difference(poly.buffer(1000)), 1)], out_shape=(H, W), transform=tr, fill=0).astype(bool)
    clear = np.isfinite(lst) & (lst > 250) & (cloud == 0)
    cover = clear[near].mean() if near.sum() else 0.0
    if cover < 0.5 or clear[ring].sum() < 50: rows.append(dict(fire=fid, granule=gid, t0=t0, night=night, cover=cover, usable=False)); continue
    bg = np.median(lst[ring & clear]); an = lst - bg; an[~clear] = np.nan
    rec = dict(fire=fid, granule=gid, t0=t0, night=night, cover=cover, usable=True, bg_K=bg, vz_deg=np.nanmedian(vz[near]), big=bool(F.loc[fid, 'big']), area_ha=F.loc[fid, 'area_ha'],
               an_p99_in=np.nanpercentile(an[inside], 99) if inside.sum() > 10 else np.nan, an_mean_in=np.nanmean(an[inside]), an_sd_ring=np.nanstd(an[ring]))
    for thr in (6, 10, 15):
        hot = an > thr; rec[f'hot{thr}_in'] = int((hot & near).sum()); rec[f'hot{thr}_out'] = int((hot & ~near & clear).sum())
        shin = (hot & near).sum() / max((clear & near).sum(), 1); shout = (hot & ~near).sum() / max((clear & ~near).sum(), 1)
        rec[f'visible{thr}'] = bool(rec[f'hot{thr}_in'] >= 3 and shin >= 3 * max(shout, 1e-4))
    hot = (an > 10) & near; rec['n_hot'] = int(hot.sum())
    if hot.sum():
        rr, cc = np.where(hot); hx = tr.c + (cc + 0.5) * tr.a; hy = tr.f + (rr + 0.5) * tr.e
        # distance to the scar edge: inside positive
        dist_in = distance_transform_edt(inside) * 70; dist_out = distance_transform_edt(~inside) * 70
        rec['hot_edge_dist_med_m'] = float(np.median(np.where(inside[rr, cc], dist_in[rr, cc], -dist_out[rr, cc])))
        rec['hot_within_150m_of_edge'] = float(np.mean(np.abs(np.where(inside[rr, cc], dist_in[rr, cc], -dist_out[rr, cc])) <= 150))
        rec['hot_cx'], rec['hot_cy'] = float(hx.mean()), float(hy.mean()); rec['hot_spread_m'] = float(np.hypot(hx - hx.mean(), hy - hy.mean()).max())
        # VIIRS within 1 h
        d = DT[(DT.fire == fid) & (DT.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21'])) & ((DT.t - t0).abs() <= pd.Timedelta(hours=1))]
        if len(d):
            rec['viirs_n'] = len(d); rec['viirs_gap_min'] = float((d.t - t0).abs().min().total_seconds() / 60)
            dd, ii = cKDTree(d[['x', 'y']].values).query(np.c_[hx, hy]); rec['hot_to_viirs_med_m'] = float(np.median(dd))
            inblock = (np.abs(hx - d.x.values[ii]) <= d.pix_w_m.values[ii] / 2) & (np.abs(hy - d.y.values[ii]) <= d.pix_h_m.values[ii] / 2)
            rec['hot_share_in_viirs_block'] = float(inblock.mean()); rec['hot_share_within_500m'] = float((dd <= 500).mean())
            blocks_hit = [(np.abs(hx - x) <= w / 2).__and__(np.abs(hy - y) <= h / 2).any() for x, y, w, h in zip(d.x, d.y, d.pix_w_m, d.pix_h_m)]
            rec['viirs_blocks_with_hot'] = float(np.mean(blocks_hit)); rec['offset_hot_minus_viirs_m'] = float(np.hypot(hx.mean() - d.x.mean(), hy.mean() - d.y.mean()))
            if len(examples) < 8 and F.loc[fid, 'big'] and hot.sum() >= 5: examples.append((fid, gid, an, inside, tr, d, hx, hy, t0))
    rows.append(rec)
ST = pd.DataFrame(rows); ST.to_csv(f'{R}/ecostress_pass_stats.csv', index=False)
U = ST[ST.usable == True]; out = dict(clips=len(ST), usable_clear=int(len(U)), fires=int(ST.fire.nunique()), big_fires_usable=int(U[U.big].fire.nunique()))
for thr in (6, 10, 15): out[f'visible_{thr}K'] = dict(all=round(float(U[f'visible{thr}'].mean()), 3), day=round(float(U[~U.night][f'visible{thr}'].mean()), 3), night=round(float(U[U.night][f'visible{thr}'].mean()), 3), big=round(float(U[U.big][f'visible{thr}'].mean()), 3))
V = U[U.visible10]; out['visible_10K_n'] = int(len(V))
out['anomaly_K'] = dict(p99_inside_scar_median=round(float(U.an_p99_in.median()), 1), ring_noise_sd_median=round(float(U.an_sd_ring.median()), 1))
W = V.dropna(subset=['hot_to_viirs_med_m'])
out['vs_viirs_within_1h'] = dict(pairs=int(len(W)), gap_min_median=round(float(W.viirs_gap_min.median()), 0) if len(W) else None,
                                 hot_to_nearest_viirs_centre_m_median=round(float(W.hot_to_viirs_med_m.median()), 0) if len(W) else None,
                                 hot_share_inside_a_viirs_block=round(float(W.hot_share_in_viirs_block.mean()), 3) if len(W) else None,
                                 hot_share_within_500m=round(float(W.hot_share_within_500m.mean()), 3) if len(W) else None,
                                 viirs_blocks_holding_a_hot_pixel=round(float(W.viirs_blocks_with_hot.mean()), 3) if len(W) else None,
                                 centre_offset_m_median=round(float(W.offset_hot_minus_viirs_m.median()), 0) if len(W) else None)
out['vs_scar_edge'] = dict(hot_pixels_median_distance_inside_edge_m=round(float(V.hot_edge_dist_med_m.median()), 0) if len(V) else None, share_within_150m_of_edge=round(float(V.hot_within_150m_of_edge.mean()), 3) if len(V) else None)
# two passes on one fire
mv = []
for fid, g in V.sort_values('t0').groupby('fire'):
    if len(g) < 2: continue
    c = S[fid].centroid
    for a, b in zip(g.iloc[:-1].itertuples(), g.iloc[1:].itertuples()):
        dt = (b.t0 - a.t0).total_seconds() / 3600
        if 0.5 <= dt <= 72: mv.append(dict(fire=fid, dt_h=dt, shift_m=np.hypot(b.hot_cx - a.hot_cx, b.hot_cy - a.hot_cy), speed_m_per_h=np.hypot(b.hot_cx - a.hot_cx, b.hot_cy - a.hot_cy) / dt))
MV = pd.DataFrame(mv); MV.to_csv(f'{R}/ecostress_pairs.csv', index=False)
out['two_passes_same_fire'] = dict(pairs=int(len(MV)), dt_h_median=round(float(MV.dt_h.median()), 1) if len(MV) else None, hot_centre_shift_m_median=round(float(MV.shift_m.median()), 0) if len(MV) else None, implied_m_per_h_median=round(float(MV.speed_m_per_h.median()), 1) if len(MV) else None)
json.dump(out, open(f'{R}/ecostress_summary.json', 'w'), indent=1, default=str); print(json.dumps(out, indent=1, default=str))
# figure: examples + histograms
n = len(examples); fig, axs = plt.subplots(2, 4, figsize=(18, 9)); axs = axs.ravel()
for k, (fid, gid, an, inside, tr, d, hx, hy, t0) in enumerate(examples[:8]):
    ax = axs[k]; H, W = an.shape; ext = [tr.c, tr.c + W * tr.a, tr.f + H * tr.e, tr.f]
    ax.imshow(an, extent=ext, cmap='inferno', vmin=-5, vmax=25); ax.contour(np.linspace(ext[0], ext[1], W), np.linspace(ext[3], ext[2], H), inside, levels=[0.5], colors='cyan', linewidths=1)
    for x, y, w, h in zip(d.x, d.y, d.pix_w_m, d.pix_h_m): ax.add_patch(plt.Rectangle((x - w / 2, y - h / 2), w, h, fill=False, ec='lime', lw=1))
    ax.set_title(f'fire {fid}  {(t0 + pd.Timedelta(hours=5.5)).strftime("%d %b %Y %H:%M")} IST\nVIIRS blocks (green) within 1 h; scar (cyan); colour = K above background', fontsize=8); ax.set_xticks([]); ax.set_yticks([])
for k in range(n, 8): axs[k].axis('off')
plt.suptitle('ECOSTRESS 70 m temperature anomaly on big fires', fontsize=12); plt.tight_layout(); plt.savefig(f'{FG}/7_ecostress.png', dpi=100)
