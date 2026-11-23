"""Akkshay 17 Oct 10:54Z: "when multiple detections come from the same satellite, the fire is somewhere in the middle of those
blocks". Verify with the 70 m ECOSTRESS hot pixels (within 1 h of a VIIRS pass) and, as a larger independent sample, with the
30 m Sentinel-2 / Landsat hot pixels (within 3 h of a VIIRS pass). For each VIIRS pass: single block vs cluster of 2+ blocks
from the same satellite. Where do the fine-scale hot pixels sit: at a block centre, at the shared edge, or in between?
Out: results/between_blocks.json, figures/8_between_blocks.png"""
import os, glob, json, pickle
import numpy as np, pandas as pd
from rasterio.transform import Affine
from scipy.spatial import cKDTree
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
R = '/mnt/project-files/research/big-fires/results'; FG = '/mnt/project-files/research/big-fires/figures'
CACHE = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/ecostress'
DT = pd.read_csv(f'{R}/detections.csv', parse_dates=['t']); ST = pd.read_csv(f'{R}/ecostress_pass_stats.csv', parse_dates=['t0'])
VI = DT[DT.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21'])]; HP = DT[DT.sensor.isin(['Sentinel-2', 'Landsat'])]
def hot_pixels_eco(fid, gid):
    z = np.load(f'{CACHE}/{fid}_{gid}.npz'); lst = z['LST'].astype(float); cloud = z['cloud']; tr = Affine(*z['transform'])
    from rasterio.features import rasterize; S = SC[fid]; H, W = lst.shape
    ring = rasterize([(S.buffer(2000).difference(S.buffer(1000)), 1)], out_shape=(H, W), transform=tr, fill=0).astype(bool)
    near = rasterize([(S.buffer(100), 1)], out_shape=(H, W), transform=tr, fill=0).astype(bool)
    clear = np.isfinite(lst) & (lst > 250) & (cloud == 0); bg = np.median(lst[ring & clear]); hot = (lst - bg > 10) & clear & near
    rr, cc = np.where(hot); return tr.c + (cc + 0.5) * tr.a, tr.f + (rr + 0.5) * tr.e
SC = pickle.load(open('/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/fire_scars.pkl', 'rb'))
def place(hx, hy, blocks):
    """for fine hot pixels and the blocks (x, y, w, h) of ONE satellite pass: relative position measures"""
    bx, by, bw, bh = blocks.x.values, blocks.y.values, blocks.pix_w_m.values, blocks.pix_h_m.values
    cx, cy = bx.mean(), by.mean()   # cluster centre
    d_centre = np.hypot(hx[:, None] - bx[None], hy[:, None] - by[None]); nearest = d_centre.min(1)
    # normalised position inside its nearest block: 0 = at the block centre, 1 = at the block edge (max of |dx|/half-w, |dy|/half-h)
    i = d_centre.argmin(1); u = np.maximum(np.abs(hx - bx[i]) / (bw[i] / 2), np.abs(hy - by[i]) / (bh[i] / 2))
    d_cluster = np.hypot(hx - cx, hy - cy)
    # inside the convex region between block centres? use distance to the segment set (2 blocks) / hull (3+): approximate by: closer to the cluster centre than to any block centre
    return dict(n_hot=len(hx), d_nearest_centre_med=float(np.median(nearest)), d_cluster_centre_med=float(np.median(d_cluster)), u_med=float(np.median(u)),
                share_u_gt_0_5=float((u > 0.5).mean()), share_closer_to_cluster_centre=float((d_cluster < nearest).mean()), hot_cx=float(hx.mean()), hot_cy=float(hy.mean()),
                hot_offset_from_cluster_centre=float(np.hypot(hx.mean() - cx, hy.mean() - cy)), hot_offset_from_nearest_block=float(np.hypot(hx.mean() - bx, hy.mean() - by).min()),
                block_sep=float(np.hypot(bx[:, None] - bx[None], by[:, None] - by[None]).max()) if len(bx) > 1 else 0.0)
rows = []
# ECOSTRESS vs VIIRS within 1 h
for _, r in ST[(ST.usable == True) & (ST.visible10 == True)].iterrows():
    hx, hy = hot_pixels_eco(r.fire, r.granule)
    if len(hx) < 3: continue
    v = VI[(VI.fire == r.fire) & ((VI.t - r.t0).abs() <= pd.Timedelta(hours=1))]
    for (sen, pid), g in v.groupby(['sensor', 'pass_id']):
        rows.append(dict(source='ECOSTRESS 70 m (1 h)', fire=r.fire, sensor=sen, n_blocks=len(g), **place(hx, hy, g)))
# S2/Landsat hot pixels vs VIIRS within 3 h
for fid, h in HP.groupby('fire'):
    for (sen, pid), g in VI[VI.fire == fid].groupby(['sensor', 'pass_id']):
        hh = h[(h.t - g.t.min()).abs() <= pd.Timedelta(hours=3)]
        if len(hh) < 3: continue
        rows.append(dict(source='Sentinel-2/Landsat 30 m (3 h)', fire=fid, sensor=sen, n_blocks=len(g), **place(hh.x.values, hh.y.values, g)))
D = pd.DataFrame(rows); D['kind'] = np.where(D.n_blocks == 1, 'single block', np.where(D.n_blocks == 2, '2 blocks', '3+ blocks')); D.to_csv(f'{R}/between_blocks.csv', index=False)
out = {}
for src, g in D.groupby('source'):
    out[src] = {}
    for k, gg in g.groupby('kind'):
        out[src][k] = dict(passes=int(len(gg)), hot_pixels_median=float(gg.n_hot.median()), hot_to_nearest_block_centre_m=round(float(gg.d_nearest_centre_med.median())), hot_to_cluster_centre_m=round(float(gg.d_cluster_centre_med.median())),
                           position_in_block_0centre_1edge=round(float(gg.u_med.median()), 2), share_in_outer_half_of_block=round(float(gg.share_u_gt_0_5.mean()), 2),
                           share_closer_to_cluster_centre_than_any_block_centre=round(float(gg.share_closer_to_cluster_centre.mean()), 2),
                           hot_centre_offset_from_cluster_centre_m=round(float(gg.hot_offset_from_cluster_centre.median())), hot_centre_offset_from_nearest_block_m=round(float(gg.hot_offset_from_nearest_block.median())),
                           block_separation_m=round(float(gg.block_sep.median())))
# null: if hot pixels were anywhere inside the blocks at random, u would be uniform in area -> median u = 0.71, share u>0.5 = 0.75
out['random_inside_block_reference'] = dict(position_in_block_0centre_1edge=0.71, share_in_outer_half_of_block=0.75)
json.dump(out, open(f'{R}/between_blocks.json', 'w'), indent=1); print(json.dumps(out, indent=1))
fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
for ax, src in zip(axs, D.source.unique()):
    g = D[D.source == src]
    for k, c in [('single block', 'C0'), ('2 blocks', 'C1'), ('3+ blocks', 'C3')]:
        gg = g[g.kind == k]
        if len(gg): ax.hist(gg.u_med, bins=np.linspace(0, 1.5, 16), alpha=0.5, color=c, label=f'{k} ({len(gg)} passes)')
    ax.axvline(0.71, color='k', ls=':', label='random inside block'); ax.set_xlabel('where the fine hot pixels sit in their block (0 = centre, 1 = edge, >1 = outside)'); ax.set_ylabel('VIIRS passes'); ax.set_title(src, fontsize=10); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig(f'{FG}/8_between_blocks.png', dpi=110)
