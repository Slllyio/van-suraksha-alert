"""Sentinel-2 look at a fire on a given scene date: true colour (smoke plume visible) and SWIR false colour
(fire front visible through smoke), with the S2 hot pixels (af scan), VIIRS detections of the passes before and after
the scene, the mapped scar and the ERA5 wind at the scene hour. Usage: smoke_chip.py event YYYY-MM-DD out.png"""
import numpy as np, pandas as pd, sys, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from pyproj import Transformer
import sim, score
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2")
e, date, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
TO_LL = Transformer.from_crs(32643, 4326, always_xy=True); TO_XY = Transformer.from_crs(4326, 32643, always_xy=True)
pad = 2500.0
x0, x1 = ev.x.min() - pad, ev.x.max() + pad; y0, y1 = ev.y.min() - pad, ev.y.max() + pad
res = 10.0; W, H = int((x1 - x0) / res), int((y1 - y0) / res); TR = from_origin(x0, y1, res, res); extent = (x0, x1, y0, y1)
lon0, lat0 = TO_LL.transform(x0, y0); lon1, lat1 = TO_LL.transform(x1, y1)
CAT = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')
items = list(CAT.search(collections=['sentinel-2-l2a'], bbox=[lon0, lat0, lon1, lat1], datetime=f'{date}T00:00:00Z/{date}T23:59:59Z').items())
print('scenes', [(it.id, it.datetime) for it in items])
def read(it, b, rs=Resampling.bilinear):
    with rasterio.open(it.assets[b].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=TR, width=W, height=H, resampling=rs) as vv:
        return vv.read(1).astype(np.float32)
bands = {}
for it in items:
    it = pc.sign(it); off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
    for b in ['B02', 'B03', 'B04', 'B08', 'B11', 'B12']:
        a = (read(it, b) - off) / 10000; a[a <= -0.09] = np.nan
        if b not in bands: bands[b] = a
        else: bands[b] = np.where(np.isnan(bands[b]), a, bands[b])
    tscene = it.datetime
def stretch(chs, pct=(1, 99)):
    rgb = np.stack([bands[c] for c in chs], -1); lo, hi = np.nanpercentile(rgb, pct[0], axis=(0, 1)), np.nanpercentile(rgb, pct[1], axis=(0, 1))
    return np.clip((rgb - lo) / (hi - lo + 1e-6), 0, 1)
# scar for this event
r, c = sim.rc(ev.x.values, ev.y.values); i0, i1 = max(r.min() - 150, 0), min(r.max() + 150, sim.NY); j0, j1 = max(c.min() - 150, 0), min(c.max() + 150, sim.NX)
S, _ = score.scar_footprint(dict(win=(i0, i1, j0, j1), season=s), ev)
sx0, sx1 = sim.X0 + j0 * sim.RES, sim.X0 + j1 * sim.RES; sy1, sy0 = sim.Y0 - i0 * sim.RES, sim.Y0 - i1 * sim.RES
# hot pixels on that date
af = pd.read_csv(f'/mnt/project-files/fire-alert-scars/out/af/af_{s}.csv'); af = af[af.date == date]
ax_, ay_ = TO_XY.transform(af.lon.values, af.lat.values); af = af.assign(x=ax_, y=ay_); af = af[(af.x > x0) & (af.x < x1) & (af.y > y0) & (af.y < y1)]
print('hot pixels in chip', len(af), af.time_utc.unique() if len(af) else '')
# wind at the scene hour
Wd, P = sim.load_weather(s); pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]
th = pd.Timestamp(tscene).tz_localize(None).floor('h'); w = Wd[pid].loc[th]
print('ERA5 wind at', th, 'UTC: toward', round(float(w.waz)), 'deg,', round(float(w.ws), 1), 'm/s')
wu, wv = np.sin(np.radians(w.waz)), np.cos(np.radians(w.waz))
passes = sorted(ev.overpass.unique()); tsn = pd.Timestamp(tscene).tz_localize(None)
fig, axs = plt.subplots(1, 2, figsize=(16, 8))
for ax, chs, lab in zip(axs, [('B04', 'B03', 'B02'), ('B12', 'B08', 'B04')], ['true colour (smoke = pale haze)', 'SWIR false colour (orange = flames, dark = burnt)']):
    ax.imshow(stretch(chs), extent=extent, origin='upper')
    ax.contour(S.astype(float), levels=[0.5], colors=['white'], linewidths=1.2, linestyles='--', extent=(sx0, sx1, sy0, sy1), origin='upper')
    if len(af): ax.scatter(af.x, af.y, s=6, color='lime', label=f'Sentinel-2 hot pixels at {af.time_utc.iloc[0]} UTC ({len(af)})')
    cols = plt.cm.cool(np.linspace(0, 1, len(passes)))
    for k, p in enumerate(passes):
        g = ev[ev.overpass == p]; dt = (g.t.min() - tsn).total_seconds() / 3600
        if abs(dt) > 30: continue
        ax.scatter(g.x, g.y, s=110, marker='o', facecolor='none', edgecolor=cols[k], linewidth=2, zorder=5,
                   label=f'VIIRS {g.t.min() + pd.Timedelta(hours=5.5):%d %b %H:%M} IST ({dt:+.0f} h from scene)')
    L = 0.1 * (x1 - x0)
    ax.annotate('', xy=(x0 + 0.85 * (x1 - x0) + L * wu, y0 + 0.9 * (y1 - y0) + L * wv), xytext=(x0 + 0.85 * (x1 - x0), y0 + 0.9 * (y1 - y0)), arrowprops=dict(arrowstyle='->', lw=3, color='yellow'))
    ax.text(x0 + 0.85 * (x1 - x0), y0 + 0.93 * (y1 - y0), f'ERA5 wind {w.ws:.1f} m/s', color='yellow', fontsize=9)
    ax.plot([], [], 'w--', label='mapped scar (whole event)'); ax.legend(loc='lower left', fontsize=8, framealpha=0.8)
    ax.set_title(f'Sentinel-2 {tsn + pd.Timedelta(hours=5.5):%d %b %Y %H:%M} IST: {lab}', fontsize=10); ax.set_xticks([]); ax.set_yticks([])
fig.suptitle(f'Fire {e}: the fire as Sentinel-2 saw it mid-event', fontsize=12); fig.tight_layout(); fig.savefig(out, dpi=100)
