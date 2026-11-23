"""C-DAC style example maps for Ratapani fires: the hourly spread forecast from the first VIIRS
detection, over terrain, roads, the mapped burn scar and the later detections; and the same outline
over Sentinel-2 false colour before and after the fire (as in C-DAC's Sikkim slides).
Usage: examples.py cfgjson event[,event...] outdir"""
import numpy as np, pandas as pd, sys, json, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from pyproj import Transformer
from scipy import ndimage
import sim, score
from engine import arrival, OFFS
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
                  GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="TRUE")
cfg = json.loads(sys.argv[1]); cfg['return_fields'] = True; events = [int(x) for x in sys.argv[2].split(',')]; outdir = sys.argv[3]
os.makedirs(outdir, exist_ok=True)
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet')
TO_LL = Transformer.from_crs(32643, 4326, always_xy=True)
CAT = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')


def s2_scene(bounds, t_from, t_to, want_after=True):
    """First (or last) clear Sentinel-2 L2A false-colour composite over bounds in [t_from, t_to]."""
    x0, y0, x1, y1 = bounds; lon0, lat0 = TO_LL.transform(x0, y0); lon1, lat1 = TO_LL.transform(x1, y1)
    items = list(CAT.search(collections=['sentinel-2-l2a'], bbox=[lon0, lat0, lon1, lat1],
                            datetime=f'{t_from:%Y-%m-%dT%H:%M:%SZ}/{t_to:%Y-%m-%dT%H:%M:%SZ}', query={'eo:cloud_cover': {'lt': 70}}).items())
    items.sort(key=lambda it: it.datetime, reverse=not want_after)
    res = 10.0; W, H = int((x1 - x0) / res), int((y1 - y0) / res); TR = from_origin(x0, y1, res, res)
    def read(href, rs):
        with rasterio.open(href) as src, WarpedVRT(src, crs='EPSG:32643', transform=TR, width=W, height=H, resampling=rs) as vv:
            return vv.read(1)
    for it in items:
        it = pc.sign(it)
        scl = read(it.assets['SCL'].href, Resampling.nearest)
        clear = np.isin(scl, [2, 3, 4, 5, 6, 7]).mean()
        if clear < 0.9:
            continue
        off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
        rgb = np.stack([(read(it.assets[b].href, Resampling.bilinear).astype(np.float32) - off) / 10000 for b in ('B08', 'B04', 'B03')], -1)
        lo, hi = np.nanpercentile(rgb, 2, axis=(0, 1)), np.nanpercentile(rgb, 98, axis=(0, 1))
        return np.clip((rgb - lo) / (hi - lo + 1e-6), 0, 1), it.datetime.date()
    return None, None


def outline(ax, mask, extent, color, lw, label=None, ls='-'):
    ax.contour(mask.astype(float), levels=[0.5], colors=[color], linewidths=lw, extent=extent, origin='upper', linestyles=ls)
    if label:
        ax.plot([], [], color=color, lw=lw, ls=ls, label=label)


summary = []
wx = {}
for e in events:
    ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    o = sim.run_event(ev, wx[s], cfg, hours=48, scar_fn=score.scar_footprint)
    Wd, P = wx[s]; pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]
    ww = Wd[pid][(Wd[pid].index >= ev.t.min()) & (Wd[pid].index <= ev.t.min() + pd.Timedelta(hours=24))]
    wu, wv = (ww.ws * np.sin(np.radians(ww.waz))).mean(), (ww.ws * np.cos(np.radians(ww.waz))).mean()
    T, S, B, (i0, i1, j0, j1), t0 = o['T'], o['S'], o['burnable'], o['win'], o['t0']
    tfirst = (ev.t.min() - t0).total_seconds() / 60
    Th = (T - tfirst) / 60.0     # hours since first detection
    F48 = Th <= 48; tend = (ev.t.max() - ev.t.min()).total_seconds() / 3600 + 12
    Fend = Th <= tend
    ig_all, tg_all = sim.ignition_mask(ev, S, B, (i0, i1, j0, j1), cfg, t0); ii, jj = np.nonzero(ig_all)
    T_rs = arrival(o['Rh'], o['Dh'], o['Eh'], B, ii.astype(np.int64), jj.astype(np.int64), tg_all[ii, jj], sim.RES, tfirst + tend * 60, OFFS, int(cfg.get('strict', 0)))
    Frs = T_rs <= tfirst + tend * 60
    # crop to the fire
    m = S | F48 | o['ig'] | Frs
    rr, cc = np.nonzero(m); pad = 25
    a0, a1 = max(rr.min() - pad, 0), min(rr.max() + pad, m.shape[0]); b0, b1 = max(cc.min() - pad, 0), min(cc.max() + pad, m.shape[1])
    crop = (slice(a0, a1), slice(b0, b1))
    x0, x1 = sim.X0 + (j0 + b0) * sim.RES, sim.X0 + (j0 + b1) * sim.RES
    y1, y0 = sim.Y0 - (i0 + a0) * sim.RES, sim.Y0 - (i0 + a1) * sim.RES
    extent = (x0, x1, y0, y1)
    elev = sim.ELEV[i0 + a0:i0 + a1, j0 + b0:j0 + b1]
    hs = LightSource(azdeg=315, altdeg=45).hillshade(elev.astype(float), vert_exag=2, dx=20, dy=20)
    road = sim.BARRIER[i0 + a0:i0 + a1, j0 + b0:j0 + b1] if sim.BARRIER is not None else np.zeros(elev.shape, bool)
    nonburn = ~np.isin(sim.WC[i0 + a0:i0 + a1, j0 + b0:j0 + b1], [10, 20, 30])
    fig, axs = plt.subplots(1, 3, figsize=(21, 7.2))
    ax = axs[0]
    ax.imshow(hs, cmap='gray', extent=extent, origin='upper', vmin=0, vmax=1)
    ax.imshow(np.ma.masked_where(~nonburn, nonburn), cmap='Blues', alpha=0.25, extent=extent, origin='upper', vmin=0, vmax=1)
    cf = ax.contourf(Th[crop], levels=[0, 6, 12, 24, 48], colors=['#fff176', '#ffb74d', '#ef5350', '#8e24aa'], alpha=0.75, extent=extent, origin='upper')
    outline(ax, S[crop], extent, 'black', 2.2, 'mapped burn scar (Sentinel-2/Landsat)')
    ax.imshow(np.ma.masked_where(~road, road), cmap='gray_r', vmin=0, vmax=1, extent=extent, origin='upper', alpha=0.9, interpolation='nearest')
    passes = sorted(ev.overpass.unique()); cols = plt.cm.cool(np.linspace(0, 1, len(passes)))
    for k, p in enumerate(passes):
        g = ev[ev.overpass == p]; hh = (g.t.min() - ev.t.min()).total_seconds() / 3600
        ax.scatter(g.x, g.y, s=90, marker='*' if k == 0 else 'o', color=cols[k], edgecolor='k', zorder=5,
                   label=f'VIIRS pass {k + 1}: {g.t.min() + pd.Timedelta(hours=5.5):%d %b %H:%M} IST (+{hh:.0f} h)')
    # wind arrow: mean ERA5 10 m wind over the first 24 h, drawn in the direction the wind blows toward
    wsp = float(np.hypot(wu, wv)); L = 0.12 * (x1 - x0)
    ax.annotate('', xy=(x0 + 0.85 * (x1 - x0) + L * wu / max(wsp, 1e-6), y0 + 0.9 * (y1 - y0) + L * wv / max(wsp, 1e-6)),
                xytext=(x0 + 0.85 * (x1 - x0), y0 + 0.9 * (y1 - y0)), arrowprops=dict(arrowstyle='->', lw=2, color='navy'))
    cb = fig.colorbar(cf, ax=ax, fraction=0.04, pad=0.02); cb.set_label('forecast arrival, hours after first detection')
    ax.legend(loc='lower left', fontsize=7.5, framealpha=0.9)
    ax.set_title(f'Fire {e}, season {s}: forecast from the first VIIRS detection\n'
                 f'24 h {int((Th[crop] <= 24).sum()) * 0.04:.0f} ha, 48 h {int(F48[crop].sum()) * 0.04:.0f} ha; scar {S.sum() * 0.04:.0f} ha\n'
                 f'roads black, non-forest blue; arrow = ERA5 wind {wsp:.1f} m/s (first 24 h mean)', fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])
    # Sentinel-2 before and after
    bounds = (x0, y0, x1, y1)
    for ax, (want_after, t_from, t_to, lab) in zip(axs[1:], [(False, ev.t.min() - pd.Timedelta(days=30), ev.t.min() - pd.Timedelta(hours=1), 'before'),
                                                          (True, ev.t.max() + pd.Timedelta(hours=1), ev.t.max() + pd.Timedelta(days=30), 'after')]):
        try:
            rgb, d = s2_scene(bounds, t_from, t_to, want_after)
        except Exception as ex:
            rgb, d = None, str(ex)[:60]
        if rgb is None:
            ax.text(0.5, 0.5, f'no clear Sentinel-2 scene {lab} the fire\n{d}', ha='center', va='center', transform=ax.transAxes); ax.set_xticks([]); ax.set_yticks([]); continue
        ax.imshow(rgb, extent=extent, origin='upper')
        outline(ax, Fend[crop], extent, 'yellow', 2.0, f'forecast burnt area to last detection + 12 h ({int(Fend[crop].sum()) * 0.04:.0f} ha)')
        outline(ax, S[crop], extent, 'black', 1.6, 'mapped burn scar', ls='--')
        outline(ax, Frs[crop], extent, 'white', 1.4, f'restarted from every pass ({int(Frs[crop].sum()) * 0.04:.0f} ha)', ls=':')
        ax.scatter(ev.x, ev.y, s=40, marker='o', facecolor='none', edgecolor='cyan', zorder=5, label='VIIRS detections')
        ax.legend(loc='lower left', fontsize=7.5, framealpha=0.85)
        ax.set_title(f'Sentinel-2 false colour {lab} the fire, {d} (NIR, red, green: red = live vegetation, dark = burnt)', fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f'Ratapani fire {e}: first detection {ev.t.min() + pd.Timedelta(hours=5.5):%d %b %Y %H:%M} IST, {len(ev)} detections on {len(passes)} passes; '
                 f'Sorensen vs scar: free forecast {score.soren(Fend, S):.2f}, restarted from every pass {score.soren(Frs, S):.2f}', fontsize=11)
    fig.tight_layout(); fig.savefig(f'{outdir}/fire_{s}_{e}.png', dpi=110); plt.close(fig)
    summary.append(dict(event=e, season=s, first=str(ev.t.min()), n_det=len(ev), n_pass=len(passes), scar_ha=round(S.sum() * 0.04, 1),
                        fc24_ha=round(float((Th <= 24).sum()) * 0.04, 1), fc48_ha=round(float(F48.sum()) * 0.04, 1), fcend_ha=round(float(Fend.sum()) * 0.04, 1),
                        sorensen_end=round(score.soren(Fend, S), 3), fcrs_ha=round(float(Frs.sum()) * 0.04, 1), sorensen_rs=round(score.soren(Frs, S), 3)))
    print(summary[-1], flush=True)
json.dump(summary, open(f'{outdir}/summary.json', 'w'), indent=1)
