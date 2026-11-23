"""Which outline is the burn? For one fire: the first clear Sentinel-2 look after the last VIIRS detection (SWIR false
colour, burnt ground dark) and the NBR drop from the last clear look before the fire, with the research thread's raster
label (cyan) and the scar thread's grown polygon (orange). Usage: grown_examples.py event out.png"""
import numpy as np, pandas as pd, sys, os, json
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from pyproj import Transformer
import sim, score, grown
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2")
e, out = int(sys.argv[1]), sys.argv[2]
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
TO_LL = Transformer.from_crs(32643, 4326, always_xy=True)
pad = 2000.0; x0, x1 = ev.x.min() - pad, ev.x.max() + pad; y0, y1 = ev.y.min() - pad, ev.y.max() + pad
res = 10.0; W, H = int((x1 - x0) / res), int((y1 - y0) / res); TR = from_origin(x0, y1, res, res); extent = (x0, x1, y0, y1)
lon0, lat0 = TO_LL.transform(x0, y0); lon1, lat1 = TO_LL.transform(x1, y1)
CAT = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')
t_first, t_last = ev.t.min(), ev.t.max()
def best(items):
    return sorted(items, key=lambda it: float(it.properties.get('eo:cloud_cover', 100)))[0] if items else None
post_items = list(CAT.search(collections=['sentinel-2-l2a'], bbox=[lon0, lat0, lon1, lat1], datetime=f'{(t_last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")}/{(t_last + pd.Timedelta(days=30)).strftime("%Y-%m-%d")}').items())
pre_items = list(CAT.search(collections=['sentinel-2-l2a'], bbox=[lon0, lat0, lon1, lat1], datetime=f'{(t_first - pd.Timedelta(days=30)).strftime("%Y-%m-%d")}/{(t_first - pd.Timedelta(days=1)).strftime("%Y-%m-%d")}').items())
def read(it, b):
    with rasterio.open(it.assets[b].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=TR, width=W, height=H, resampling=Resampling.bilinear) as vv:
        return vv.read(1).astype(np.float32)
def chip(items):
    """earliest post scene with < 40% cloud, else least cloudy"""
    cand = sorted([it for it in items if float(it.properties.get('eo:cloud_cover', 100)) < 40], key=lambda it: it.datetime) or ([best(items)] if items else [])
    for it in cand:
        it = pc.sign(it); off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
        b = {k: (read(it, k) - off) / 10000 for k in ['B04', 'B08', 'B12']}
        scl = read(it, 'SCL'); ok = ~np.isin(np.round(scl), [0, 1, 3, 8, 9, 10]) & (b['B04'] > -0.05)
        if ok.mean() > 0.6:
            return b, ok, it.datetime
    return None, None, None
post, okp, tpost = chip(post_items)
pre_items_sorted = sorted(pre_items, key=lambda it: it.datetime, reverse=True)
pre, okq, tpre = chip(pre_items_sorted)
print('post', tpost, 'pre', tpre)
r, c = sim.rc(ev.x.values, ev.y.values); i0, i1 = max(r.min() - 120, 0), min(r.max() + 120, sim.NY); j0, j1 = max(c.min() - 120, 0), min(c.max() + 120, sim.NX)
S, _ = score.scar_footprint(dict(win=(i0, i1, j0, j1), season=s), ev); G, _ = grown.scar_footprint(dict(win=(i0, i1, j0, j1)), ev)
sx0, sx1 = sim.X0 + j0 * sim.RES, sim.X0 + j1 * sim.RES; sy1, sy0 = sim.Y0 - i0 * sim.RES, sim.Y0 - i1 * sim.RES; sext = (sx0, sx1, sy0, sy1)
nbr = lambda b: (b['B08'] - b['B12']) / (b['B08'] + b['B12'] + 1e-6)
fig, axs = plt.subplots(1, 3 if pre is not None else 2, figsize=(21 if pre is not None else 14, 7.5))
def swir(b):
    rgb = np.stack([b['B12'], b['B08'], b['B04']], -1); lo, hi = np.nanpercentile(rgb, 1, axis=(0, 1)), np.nanpercentile(rgb, 99, axis=(0, 1)); return np.clip((rgb - lo) / (hi - lo + 1e-6), 0, 1)
def outlines(ax):
    ax.contour(S.astype(float), levels=[0.5], colors=['cyan'], linewidths=1.6, extent=sext, origin='upper'); ax.contour(G.astype(float), levels=[0.5], colors=['orange'], linewidths=1.6, extent=sext, origin='upper')
    ax.plot([], [], color='cyan', lw=1.6, label=f'raster label, research thread ({S.sum() * .04:.0f} ha)'); ax.plot([], [], color='orange', lw=1.6, label=f'grown polygon, scar thread ({G.sum() * .04:.0f} ha)')
    for k, p in enumerate(sorted(ev.overpass.unique())):
        g = ev[ev.overpass == p]; ax.scatter(g.x, g.y, s=70, marker='*' if k == 0 else 'o', color='lime' if k == 0 else 'yellow', edgecolor='k', zorder=5, label=f'VIIRS pass {k + 1} ({g.t.min().strftime("%d %b %H:%M")} UTC)')
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc='lower left', fontsize=7.5)
ax = axs[0]
if post is not None:
    ax.imshow(swir(post), extent=extent, origin='upper'); ax.set_title(f'Fire {e} ({s}): first clear Sentinel-2 look after the last detection, {tpost.strftime("%d %b %Y")} (SWIR false colour, burnt = dark)', fontsize=9)
outlines(ax)
if pre is not None and post is not None:
    ax = axs[1]; ax.imshow(swir(pre), extent=extent, origin='upper'); ax.set_title(f'last clear look before the fire, {tpre.strftime("%d %b %Y")}', fontsize=9); outlines(ax)
    ax = axs[2]; d = nbr(pre) - nbr(post); d[~(okp & okq)] = np.nan
    im = ax.imshow(d, extent=extent, origin='upper', cmap='RdYlGn_r', vmin=-0.1, vmax=0.4); plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label='NBR drop, before minus after (burnt > ~0.1)'); ax.set_title('NBR drop between the two looks', fontsize=9); outlines(ax)
    # mean NBR drop inside each outline and in the ring the polygon adds
    import scipy.ndimage as ndi
    from rasterio import features
    yy, xx = np.mgrid[0:H, 0:W]; px = x0 + xx * res + res / 2; py = y1 - yy * res - res / 2
    rr = np.clip(((sim.Y0 - py) / sim.RES).astype(int) - i0, 0, S.shape[0] - 1); cc = np.clip(((px - sim.X0) / sim.RES).astype(int) - j0, 0, S.shape[1] - 1)
    Sm, Gm = S[rr, cc], G[rr, cc]
    stats = {k: float(np.nanmedian(d[m])) for k, m in [('raster label', Sm), ('polygon only', Gm & ~Sm), ('outside both, within 500 m', ndi.binary_dilation(Gm, iterations=50) & ~Gm)]}
    ax.text(0.02, 0.98, '\n'.join(f'median NBR drop, {k}: {val:.3f}' for k, val in stats.items()), transform=ax.transAxes, va='top', fontsize=8, bbox=dict(facecolor='white', alpha=0.8))
    print(stats)
fig.tight_layout(); fig.savefig(out, dpi=100); plt.close(fig); print('saved', out)
