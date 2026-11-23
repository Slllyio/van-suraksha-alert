"""Tracking step 8: figures.
  fig_examples_<config>.png : 4 example fires. Per fire: (left) fitted arrival time with isochrones at the flagged pass times,
      each flagged VIIRS footprint (turned rectangle, coloured by its own time) and the looked-and-not-flagged lattice
      nodes of one pass; (middle) arrival-time spread from the pass bootstrap; (right) local spread speed (m/h).
  fig_validation_<config>.png : photo accuracy and hot-pixel placement of the inversion vs baselines (from t6/t7 json).
Usage: python3 t8_figures.py <config> fire1,fire2,fire3,fire4"""
import sys, os, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import *
from t6_photos import load_map
from t9_tracks import raster, speed

def corners(x, y, h, s, t):
    us, ut = axes(h); return np.array([[x, y] + a * s / 2 * us + b * t / 2 * ut for a, b in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])

def example(ax3, name, fire):
    z = load_map(name, fire); t0 = z['t0']; tr = z['tr']; c = tr[0]
    nr, nc = z['shape']; ext = [tr[2], tr[2] + nc * c, tr[5] - nr * c, tr[5]]
    D = data()['D']; d = D[(D.fire == fire) & (D.kind == 'viirs')].copy(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    A = raster(z); A[A > 1e3] = np.nan
    vmin, vmax = np.nanpercentile(A, 2), np.nanpercentile(A, 98)
    ax = ax3[0]; im = ax.imshow(A, extent=ext, cmap='viridis', vmin=vmin, vmax=vmax, origin='upper')
    tks = np.sort(d.th.unique()); X, Y = np.meshgrid(tr[2] + (np.arange(nc) + .5) * c, tr[5] - (np.arange(nr) + .5) * c)
    lv = [t for t in tks if vmin < t < vmax]
    if len(lv) > 1: ax.contour(X, Y, np.nan_to_num(A, nan=1e4), levels=lv[::max(1, len(lv) // 8)], colors='w', linewidths=.6)
    cm = plt.get_cmap('viridis')
    for q in d.itertuples():
        P = corners(q.xc, q.yc, q.heading, q.scan_m, q.track_m)
        ax.add_patch(MPoly(P, closed=True, fill=False, ec=cm((q.th - vmin) / max(vmax - vmin, 1e-6)), lw=1.0))
    # not-flagged nodes of the busiest pass
    fr = Fire(fire); pk = d.pass_key.value_counts().index[0]; k = int(np.where(fr.passes.pass_key.values == pk)[0][0])
    m = fr.node_pass == k
    ax.plot(fr.node_xy[m & ~fr.node_flag, 0], fr.node_xy[m & ~fr.node_flag, 1], '.', ms=2, c='r', label='looked, not flagged (one pass)')
    ax.plot(fr.node_xy[m & fr.node_flag, 0], fr.node_xy[m & fr.node_flag, 1], 'x', ms=4, c='r', label='flagged (same pass)')
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f'fire {fire}: arrival (h after {t0:%d %b %Y %H:%M} UTC)', fontsize=8); plt.colorbar(im, ax=ax, fraction=.046)
    ax.legend(fontsize=6, loc='lower left')
    ax = ax3[1]
    if 'T_boot_sd' in z:
        S = raster(z, 'T_boot_sd'); im = ax.imshow(np.clip(S, 0, 24), extent=ext, cmap='magma', origin='upper'); plt.colorbar(im, ax=ax, fraction=.046)
        ax.set_title('arrival spread, pass bootstrap (h, sd)', fontsize=8)
    else:
        S = raster(z, 'sd_laplace'); im = ax.imshow(np.clip(S, 0, 24), extent=ext, cmap='magma', origin='upper'); plt.colorbar(im, ax=ax, fraction=.046)
        ax.set_title('arrival sd (Laplace, h)', fontsize=8)
    ax.set_xticks([]); ax.set_yticks([])
    ax = ax3[2]; v = np.full((nr, nc), np.nan); v[z['rr'], z['cc']] = speed(z)
    im = ax.imshow(np.log10(np.clip(v, 1, 1000)), extent=ext, cmap='plasma', origin='upper', vmin=0, vmax=3)
    cb = plt.colorbar(im, ax=ax, fraction=.046); cb.set_ticks([0, 1, 2, 3]); cb.set_ticklabels(['1', '10', '100', '1000'])
    ax.set_title('local spread speed (m/h, log scale)', fontsize=8); ax.set_xticks([]); ax.set_yticks([])

if __name__ == '__main__':
    name = sys.argv[1]; fires = [int(f) for f in sys.argv[2].split(',')]
    fig, axs = plt.subplots(len(fires), 3, figsize=(13, 4 * len(fires)))
    for i, f in enumerate(fires): example(axs[i], name, f)
    plt.tight_layout(); plt.savefig(f'{OUT}/fig_examples_{name}.png', dpi=110); print('saved')
