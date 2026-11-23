"""Growth maps for the 146 big fires, on a terrain (hillshade) background.
For each fire: the chosen front-matching map (all VIIRS looks), lines at every look time, the detections, the outline.
Also writes one small GeoTIFF per fire (arrival time in hours after the first look, and the bracket width).
argv[1]: JSON options for blend_map, chosen on photos with seasons held out (c4): '{"p":4,"clock":true}'.
Out: figures/growth_atlas.pdf, figures/examples.png, results/maps/<fire>.tif (to SCRATCH unless argv[2] == 'save')"""
import sys, os, json, pickle
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import Normalize, LightSource
from rasterio import features
from rasterio.transform import Affine
import rasterio
sys.path.insert(0, os.path.dirname(__file__))
from c0_lib import *

BF = f'{ROOT}/research/big-fires/results'; HERE = f'{ROOT}/research/fire-continuity'
OPT = json.loads(sys.argv[1]); SAVE = len(sys.argv) > 2 and sys.argv[2] == 'save'
MAPDIR = f'{HERE}/results/maps' if SAVE else f'{SCRATCH}/maps'; os.makedirs(MAPDIR, exist_ok=True)
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv'); F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
L = pd.read_csv(f'{BF}/big_fires_list.csv')   # same page order as the big-fires atlas
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
IST = pd.Timedelta(hours=5, minutes=30)

def build(fire):
    d = viirs_looks(A[A.fire == fire]); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 800, ys.max() + 800); r1, c1 = rc_of(xs.max() + 800, ys.min() - 800)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    clk = Clock(t0) if OPT.get('clock') else None
    T, lo, hi, idx, dmin = blend_map(box, dom, d, clock=clk, p=OPT.get('p', 4)); vs = []
    Tg = np.full(box.shape, np.nan); W = np.full(box.shape, np.nan)
    rr, cc = np.where(dom); Tg[rr, cc] = np.where(np.isfinite(T), T, np.nan)
    W[rr, cc] = np.where(np.isfinite(hi) & np.isfinite(lo), hi - lo, np.nan)
    Dm = np.full(box.shape, np.nan); Dm[rr, cc] = dmin
    box.dmin = Dm
    return d, t0, box, tr, dom, Tg, W, vs

def save_tif(fire, tr, Tg, W):
    with rasterio.open(f'{MAPDIR}/fire_{fire}.tif', 'w', driver='GTiff', height=Tg.shape[0], width=Tg.shape[1], count=2,
                       dtype='float32', crs='EPSG:32643', transform=tr, nodata=np.nan, compress='deflate') as o:
        o.write(Tg.astype('float32'), 1); o.write(W.astype('float32'), 2)
        o.set_band_description(1, 'arrival_h_after_first_look'); o.set_band_description(2, 'bracket_width_h')

def draw(ax, fire, d, t0, box, dom, Tg, title=True):
    ls = LightSource(azdeg=315, altdeg=40)
    hs = ls.hillshade(box.elev, vert_exag=4, dx=20, dy=20)
    ext = [box.X[0, 0] - 10, box.X[0, -1] + 10, box.Y[-1, 0] - 10, box.Y[0, 0] + 10]
    ax.imshow(hs, cmap='gray', extent=ext, vmin=0, vmax=1)
    tmax = np.nanmax(Tg[np.isfinite(Tg)]) if np.isfinite(Tg).any() else 1
    norm = Normalize(0, max(d.th.max(), 1))
    near = box.dmin <= 600     # within 600 m walk of a detection: timing is informed; beyond: a guess (drawn faint)
    ax.imshow(np.ma.masked_invalid(np.where(near, np.clip(Tg, 0, None), np.nan)), cmap='plasma', norm=norm, extent=ext, alpha=.8, interpolation='nearest')
    ax.imshow(np.ma.masked_invalid(np.where(~near, np.clip(Tg, 0, None), np.nan)), cmap='plasma', norm=norm, extent=ext, alpha=.3, interpolation='nearest')
    lt = d.groupby('lk').th.min().values
    ax.contour(box.X, box.Y, np.nan_to_num(Tg, nan=1e6), levels=sorted(set(lt[1:])), colors='white', linewidths=.7, alpha=.9).set_rasterized(True)
    ax.contour(box.X, box.Y, dom.astype(float), levels=[.5], colors='black', linewidths=1).set_rasterized(True)
    ax.scatter(d.x, d.y, c=d.th, cmap='plasma', norm=norm, s=22, edgecolors='black', linewidths=.6, zorder=5, rasterized=True)
    for k, g in d.groupby('lk'):
        ax.annotate(str(k + 1), (g.x.mean(), g.y.mean()), fontsize=8, color='white', weight='bold', ha='center', va='center', zorder=6,
                    bbox=dict(boxstyle='circle,pad=0.15', fc='black', alpha=.6, lw=0))
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect('equal')
    x0 = ext[0] + 0.05 * (ext[1] - ext[0]); y0 = ext[2] + 0.05 * (ext[3] - ext[2])
    ax.plot([x0, x0 + 1000], [y0, y0], color='white', lw=3); ax.text(x0 + 500, y0 + 60, '1 km', color='white', ha='center', fontsize=8)
    return norm

def legend_text(d, t0):
    rows = []
    for k, g in d.groupby('lk'):
        rows.append(f"{k + 1}: {(g.t.min() + IST).strftime('%d %b %H:%M')} IST, {len(g)} dots")
    return '\n'.join(rows)

if __name__ == '__main__':
    big = L.fire.tolist(); speeds = []
    import io
    from PIL import Image
    pages = []
    if True:
        for page, fire in enumerate(big, 1):
            d, t0, box, tr, dom, Tg, W, vs = build(fire)
            save_tif(fire, tr, Tg, W); speeds += [(fire, v) for v in vs]
            fig = plt.figure(figsize=(11, 7.5))
            ax = fig.add_axes([0.02, 0.05, 0.66, 0.88]); norm = draw(ax, fire, d, t0, box, dom, Tg)
            cax = fig.add_axes([0.70, 0.55, 0.015, 0.35])
            cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap='plasma'), cax=cax)
            cb.set_label('hours after first look')
            fig.text(0.70, 0.93, f"Big fire {page} (fire id {fire})", fontsize=13, weight='bold')
            fig.text(0.70, 0.50, f"{F.area_ha[F.fire == fire].iloc[0]:.0f} ha outline\n\nLooks (numbered on the map):\n" + legend_text(d, t0),
                     fontsize=8.5, va='top', family='monospace')
            fig.text(0.02, 0.945, 'Colour = when the fire reached each 20 m spot (estimated). White lines = where the front was at each look.\n'
                     'Dots = VIIRS detections, same colours. Black line = final burn outline. Grey relief = hills and valleys.\n'
                     'Faint colour = more than 600 m from any detection: timing there is a guess.', fontsize=9)
            buf = io.BytesIO(); fig.savefig(buf, dpi=90, format='png'); plt.close(fig)
            pages.append(Image.open(buf).convert('RGB'))
            if page % 20 == 0: print(page)
    pages[0].save(f'{HERE}/figures/growth_atlas.pdf', save_all=True, append_images=pages[1:], quality=80, resolution=90)
    pages[1].save(f'{HERE}/figures/example_page.png')
