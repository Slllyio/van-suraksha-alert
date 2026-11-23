"""Smoke plumes as a wind vane. For every Sentinel-2 scene taken while a fire was burning (hot pixels in the scene), measure the
direction of the smoke plume from the blue-band excess over the latest clear pre-fire scene, in 30-degree sectors around the hot
pixels. Compare with the ERA5 wind at the scene hour and with where the scar went. Usage: plume.py k/n out.parquet [figdir]"""
import numpy as np, pandas as pd, sys, os, time
import rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from pyproj import Transformer
from scipy import ndimage
import sim, score
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2")
k, n = map(int, sys.argv[1].split('/')); out = sys.argv[2]; figdir = sys.argv[3] if len(sys.argv) > 3 else None
ms = pd.read_parquet(f'{sim.DATA}/midevent_scenes.parquet'); ms = ms[ms.sensor == 's2'].sort_values('n_hot', ascending=False).reset_index(drop=True)
ms = ms.iloc[k::n]
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); rd = pd.read_parquet(f'{sim.DATA}/rundir.parquet').set_index('event')
TO_LL = Transformer.from_crs(32643, 4326, always_xy=True); TO_XY = Transformer.from_crs(4326, 32643, always_xy=True)
CAT = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')
RES = 10.0; HALF = 3500.0
AF = {}
def af(s):
    if s not in AF:
        a = pd.read_csv(f'/mnt/project-files/fire-alert-scars/out/af/af_{s}.csv'); a['date'] = pd.to_datetime(a.date)
        x, y = TO_XY.transform(a.lon.values, a.lat.values); a['x'], a['y'] = x, y; AF[s] = a
    return AF[s]
def reader(TR, W, H):
    def read(it, b, rs=Resampling.bilinear):
        with rasterio.open(it.assets[b].href) as src, WarpedVRT(src, crs='EPSG:32643', transform=TR, width=W, height=H, resampling=rs) as vv:
            return vv.read(1).astype(np.float32)
    return read
def refl(it, read, b):
    off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
    a = (read(it, b) - off) / 10000; a[a <= -0.09] = np.nan; return a
rows = []; wx = {}; tt = time.time()
for i, r in ms.iterrows():
    try:
        ev = v[v.event == r.event].sort_values('t'); s = int(r.season)
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        h = af(s); h = h[(h.scene == r.scene)]
        d, _ = __import__('scipy.spatial', fromlist=['cKDTree']).cKDTree(ev[['x', 'y']].values).query(h[['x', 'y']].values); h = h[d <= 1500]
        hx, hy = h.x.mean(), h.y.mean()
        x0, x1, y0, y1 = hx - HALF, hx + HALF, hy - HALF, hy + HALF; W = H = int(2 * HALF / RES); TR = from_origin(x0, y1, RES, RES); read = reader(TR, W, H)
        lon0, lat0 = TO_LL.transform(x0, y0); lon1, lat1 = TO_LL.transform(x1, y1)
        now = list(CAT.search(collections=['sentinel-2-l2a'], ids=[r.scene]).items())
        if not now:
            now = [it for it in CAT.search(collections=['sentinel-2-l2a'], bbox=[lon0, lat0, lon1, lat1], datetime=f'{r.date:%Y-%m-%d}T00:00:00Z/{r.date:%Y-%m-%d}T23:59:59Z').items()]
        if not now: print('no scene', r.event, r.scene, flush=True); continue
        now = pc.sign(now[0])
        B02n, B04n, B12n, SCLn = refl(now, read, 'B02'), refl(now, read, 'B04'), refl(now, read, 'B12'), read(now, 'SCL', Resampling.nearest)
        # before: latest clear scene in the 30 days before
        bef = list(CAT.search(collections=['sentinel-2-l2a'], bbox=[lon0, lat0, lon1, lat1], datetime=f'{r.date - pd.Timedelta(days=30):%Y-%m-%d}T00:00:00Z/{r.date - pd.Timedelta(days=1):%Y-%m-%d}T23:59:59Z', query={'eo:cloud_cover': {'lt': 60}}).items())
        bef.sort(key=lambda it: it.datetime, reverse=True); B02b = None
        for it in bef:
            it = pc.sign(it); scl = read(it, 'SCL', Resampling.nearest)
            if np.isin(scl, [4, 5, 6, 7]).mean() < 0.85: continue
            B02b = refl(it, read, 'B02'); dbef = it.datetime.date(); break
        if B02b is None: print('no before', r.event, flush=True); continue
        dB = B02n - B02b
        yy, xx = np.mgrid[0:H, 0:W]; px = x0 + xx * RES + RES / 2; py = y1 - yy * RES - RES / 2
        hot = np.zeros((H, W), bool); hr = ((y1 - h.y.values) / RES).astype(int); hc = ((h.x.values - x0) / RES).astype(int)
        okm = (hr >= 0) & (hr < H) & (hc >= 0) & (hc < W); hot[hr[okm], hc[okm]] = True; hot = ndimage.binary_dilation(hot, iterations=6)
        dist = np.hypot(px - hx, py - hy); bear = (np.degrees(np.arctan2(px - hx, py - hy)) + 360) % 360
        valid = np.isfinite(dB) & ~hot & (dist >= 250) & (dist <= 3000) & ~np.isin(SCLn, [6]) & (B12n < 0.6)   # no water, no bright soil
        # scene-to-scene offset (haze, calibration): take the window median out, then rank sectors by their 75th percentile
        dB = dB - np.nanmedian(dB[valid])
        sec = (bear // 30).astype(int)
        profs = {}
        for q in range(12):
            m = valid & (sec == q); x = dB[m]
            profs[q] = (np.nanmedian(x), np.nanmean(x), np.nanpercentile(x, 75), np.nanpercentile(x, 90), float((x > 0.02).mean())) if m.sum() > 200 else (np.nan,) * 5
        prof = np.array([profs[q][2] for q in range(12)])
        if np.isfinite(prof).sum() < 8: print('few sectors', r.event, flush=True); continue
        best = int(np.nanargmax(prof)); plume_az = best * 30 + 15
        others = np.delete(prof, best); strength = float((prof[best] - np.nanmedian(others)) / (np.nanstd(others) + 1e-4))
        # weighted-vector version: positive blue excess as weight
        wpos = np.where(valid & (dB > 0.01), dB, 0.0); vx = (wpos * np.sin(np.radians(bear))).sum(); vy = (wpos * np.cos(np.radians(bear))).sum(); R = float(np.hypot(vx, vy) / (wpos.sum() + 1e-9))
        az_vec = float((np.degrees(np.arctan2(vx, vy)) + 360) % 360)
        extra = {f'p{q}_{nm}': profs[q][i] for q in range(12) for i, nm in enumerate(['med', 'mean', 'p75', 'p90', 'haze'])}
        cloud = float(np.isin(SCLn, [8, 9, 10]).mean())
        Wd, P = wx[s]; pid = P.index[np.argmin(np.hypot(P.x - hx, P.y - hy))]; th = pd.Timestamp(now.datetime).tz_localize(None).floor('h'); w = Wd[pid].loc[th]
        first = ev[ev.overpass == ev.overpass.min()]
        hot_az = float((np.degrees(np.arctan2(hx - first.x.mean(), hy - first.y.mean())) + 360) % 360); hot_d = float(np.hypot(hx - first.x.mean(), hy - first.y.mean()))
        # scar centroid relative to the hot pixels: where the fire went from here
        rr, cc = sim.rc(ev.x.values, ev.y.values); i0, i1 = max(rr.min() - 150, 0), min(rr.max() + 150, sim.NY); j0, j1 = max(cc.min() - 150, 0), min(cc.max() + 150, sim.NX)
        S, _ = score.scar_footprint(dict(win=(i0, i1, j0, j1), season=s), ev); ys, xs = np.nonzero(S)
        scx, scy = sim.X0 + (j0 + xs.mean()) * sim.RES, sim.Y0 - (i0 + ys.mean()) * sim.RES
        ahead_az = float((np.degrees(np.arctan2(scx - hx, scy - hy)) + 360) % 360); ahead_d = float(np.hypot(scx - hx, scy - hy))
        # scar pixels beyond the hot pixels along the plume direction vs opposite (does the fire go downwind?)
        sxm, sym = sim.X0 + (j0 + xs) * sim.RES, sim.Y0 - (i0 + ys) * sim.RES; sb = (np.degrees(np.arctan2(sxm - hx, sym - hy)) + 360) % 360; sd = np.hypot(sxm - hx, sym - hy)
        far = sd > 300; dw = far & (np.abs(((sb - plume_az) + 180) % 360 - 180) <= 45); uw = far & (np.abs(((sb - plume_az) + 180) % 360 - 180) >= 135)
        rows.append(dict(event=int(r.event), season=s, date=r.date, scene=r.scene, n_hot=len(h), before=str(dbef), plume_az=plume_az, strength=strength, prof_max=float(prof[best]),
                         prof_med=float(np.nanmedian(others)), az_vec=az_vec, R=R, cloud=cloud, wind_az=float(w.waz), wind_ms=float(w.ws), hot_az=hot_az, hot_d=hot_d,
                         ahead_az=ahead_az, ahead_d=ahead_d, scar_dw=int(dw.sum()), scar_uw=int(uw.sum()), scar_far=int(far.sum()),
                         run_az=float(rd.loc[r.event, 'run_az']), run_m=float(rd.loc[r.event, 'run_m']), mom_az=float(rd.loc[r.event, 'mom_az']), hours_after_first=float(r.hours_after_first), **extra))
        if figdir and len(rows) <= 16:
            import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
            fig, axs = plt.subplots(1, 2, figsize=(13, 6.5)); ext = (x0, x1, y0, y1)
            rgb = np.stack([B04n, read(now, 'B03') / 10000 - (0.1 if float(now.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0), B02n], -1)
            lo, hi = np.nanpercentile(rgb, 1, axis=(0, 1)), np.nanpercentile(rgb, 99, axis=(0, 1)); axs[0].imshow(np.clip((rgb - lo) / (hi - lo + 1e-6), 0, 1), extent=ext, origin='upper')
            im = axs[1].imshow(np.where(valid, dB, np.nan), extent=ext, origin='upper', cmap='RdBu_r', vmin=-0.05, vmax=0.05); plt.colorbar(im, ax=axs[1], fraction=0.04, label='blue excess vs before')
            for ax in axs:
                ax.scatter(h.x, h.y, s=4, color='lime'); ax.contour(S.astype(float), levels=[0.5], colors=['white'], linewidths=1, linestyles='--', extent=(sim.X0 + j0 * sim.RES, sim.X0 + j1 * sim.RES, sim.Y0 - i1 * sim.RES, sim.Y0 - i0 * sim.RES), origin='upper')
                L = 1200
                for azd, col, lab in [(plume_az, 'magenta', 'plume (sectors)'), (w.waz, 'yellow', 'ERA5 wind'), (ahead_az, 'cyan', 'to scar centre')]:
                    ax.annotate('', xy=(hx + L * np.sin(np.radians(azd)), hy + L * np.cos(np.radians(azd))), xytext=(hx, hy), arrowprops=dict(arrowstyle='->', lw=2.5, color=col)); ax.plot([], [], color=col, label=lab)
                ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc='lower left', fontsize=8)
            axs[0].set_title(f'fire {r.event} {r.date:%d %b %Y} 10:45 IST true colour; {len(h)} hot pixels', fontsize=10); axs[1].set_title(f'blue excess over {dbef}; plume strength {strength:.1f}, ERA5 {w.ws:.1f} m/s', fontsize=10)
            fig.tight_layout(); fig.savefig(f'{figdir}/plume_{s}_{int(r.event)}_{r.date:%m%d}.png', dpi=90); plt.close(fig)
        if len(rows) % 10 == 0: print(len(rows), f'{time.time() - tt:.0f}s', flush=True); pd.DataFrame(rows).to_parquet(out)
    except Exception as ex:
        print('fail', r.event, r.date, repr(ex)[:120], flush=True)
pd.DataFrame(rows).to_parquet(out); print('done', len(rows))
