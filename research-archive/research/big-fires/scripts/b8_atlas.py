"""One page per big fire, for checking by eye (Akkshay 18:25Z).
Left: scar outline (v2) in grey, every detection as its real block (VIIRS solid 375 m+, MODIS dashed 1 km+, Sentinel-2/Landsat
hot pixels as red dots), coloured and numbered by look (look = detections within 2 h). Right: the look table in IST.
Out: figures/big_fires_atlas.pdf, results/big_fires_list.csv
"""
import glob, pickle
import numpy as np, pandas as pd, pyproj
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
from shapely.geometry import Point
ROOT = '/mnt/project-files'; R = f'{ROOT}/research/big-fires/results'; FG = f'{ROOT}/research/big-fires/figures'
F = pd.read_csv(f'{R}/fires.csv'); A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t']); S = pickle.load(open(f'{R}/fire_scars.pkl', 'rb'))
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
B = F[F.big].sort_values(['season', 'date0']).reset_index(drop=True)
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
inv = pyproj.Transformer.from_crs(32643, 4326, always_xy=True).transform
h = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_*.csv')], ignore_index=True)
h['t'] = pd.to_datetime(h.date + ' ' + h.time_utc); h['x'], h['y'] = tp(h.lon.values, h.lat.values)
IST = pd.Timedelta(hours=5, minutes=30)
SATN = {'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21', 'modis': 'MODIS'}
rows = []
with PdfPages(f'{FG}/big_fires_atlas.pdf') as pdf:
    for n, f in B.iterrows():
        poly = S[f.fire]; a = A[A.fire == f.fire].copy().sort_values('t')
        x0, y0, x1, y1 = poly.bounds
        hh = h[(h.x > x0 - 200) & (h.x < x1 + 200) & (h.y > y0 - 200) & (h.y < y1 + 200) &
               (h.t >= a.t.min() - pd.Timedelta(days=2)) & (h.t <= a.t.max() + pd.Timedelta(days=2))]
        zb = poly.buffer(100); hh = hh[np.array([zb.contains(Point(xx, yy)) for xx, yy in zip(hh.x, hh.y)], dtype=bool)]
        allt = pd.concat([a[['t']].assign(src=a.sat), hh[['t']].assign(src='hotpix')]).sort_values('t')
        slot = (allt.t.diff() > pd.Timedelta(hours=2)).cumsum() + 1
        a['L'] = slot[allt.src != 'hotpix'].values if False else None
        # assign look numbers
        tt = allt.t.values; ss = slot.values
        def look_of(t): return int(ss[np.searchsorted(tt, np.datetime64(t), side='right') - 1])
        a['L'] = [look_of(t) for t in a.t]; hh = hh.assign(L=[look_of(t) for t in hh.t])
        nL = int(slot.max()); cm = plt.cm.turbo
        col = lambda L: cm((L - 1) / max(nL - 1, 1))
        fig = plt.figure(figsize=(16.5, 10))
        ax = fig.add_axes([0.03, 0.06, 0.58, 0.84])
        for g in getattr(poly, 'geoms', [poly]):
            xs, ys = g.exterior.xy; ax.fill(xs, ys, color='0.88', ec='k', lw=0.8)
            for hole in g.interiors:
                xs, ys = hole.xy; ax.fill(xs, ys, color='white', ec='k', lw=0.4)
        for r in a.itertuples():
            md = r.sat == 'modis'
            w = (r.scan if np.isfinite(r.scan) else (1 if md else .375)) * 1000
            ht = (r.track if np.isfinite(r.track) else (1 if md else .375)) * 1000
            ax.add_patch(Rectangle((r.x - w / 2, r.y - ht / 2), w, ht, fc='none', ec=col(r.L), lw=0.9 if md else 1.7, ls='--' if md else '-'))
        for L, g in a.groupby('L'):
            ax.text(g.x.mean(), g.y.mean(), str(L), fontsize=11, weight='bold', color=col(L), ha='center', va='center',
                    bbox=dict(fc='white', ec=col(L), alpha=0.85, pad=1.5))
        if len(hh): ax.scatter(hh.x, hh.y, s=4, c='red', zorder=5, label='Sentinel-2/Landsat hot pixel')
        pad = 900; ax.set_xlim(min(x0, a.x.min()) - pad, max(x1, a.x.max()) + pad); ax.set_ylim(min(y0, a.y.min()) - pad, max(y1, a.y.max()) + pad)
        ax.set_aspect('equal')
        xt = ax.get_xticks(); yt = ax.get_yticks()
        ax.set_xticks(xt); ax.set_xticklabels([f'{inv(v_, (y0 + y1) / 2)[0]:.3f}E' for v_ in xt], fontsize=7)
        ax.set_yticks(yt); ax.set_yticklabels([f'{inv((x0 + x1) / 2, v_)[1]:.3f}N' for v_ in yt], fontsize=7)
        ax.set_xlim(min(x0, a.x.min()) - pad, max(x1, a.x.max()) + pad); ax.set_ylim(min(y0, a.y.min()) - pad, max(y1, a.y.max()) + pad)
        ax.plot([], [], 'k-', lw=1.7, label='VIIRS block (real size)'); ax.plot([], [], 'k--', lw=0.9, label='MODIS block (real size)')
        ax.legend(loc='lower left', fontsize=8)
        # 1 km scale bar
        sx, sy = ax.get_xlim()[1] - 1400, ax.get_ylim()[0] + 300
        ax.plot([sx, sx + 1000], [sy, sy], 'k-', lw=3); ax.text(sx + 500, sy + 80, '1 km', ha='center', fontsize=8)
        lat, lon = inv(poly.centroid.x, poly.centroid.y)[::-1]
        ax.set_title(f'Big fire {n + 1} of {len(B)}  (fire id {f.fire}, events {f.events.replace(";", ", ")[:90]})\n'
                     f'scar {f.area_ha:.0f} ha, centre {lat:.4f}N {lon:.4f}E, {f.date0} to {f.date1}', fontsize=10, loc='left')
        # table of looks
        tab = []
        for L in range(1, nL + 1):
            g = a[a.L == L]; gh = hh[hh.L == L]
            if not len(g) and not len(gh): continue
            t = (pd.concat([g.t, gh.t]).min() + IST)
            parts = [(gg.t.min(), f'{SATN.get(s, s)} {len(gg)} @{(gg.t.min() + IST):%H:%M}') for s, gg in g.groupby('sat')]
            if len(gh): parts.append((gh.t.min(), f'{"/".join(gh.sensor.unique()).replace("s2", "Sentinel-2").replace("ls", "Landsat")} hot px {len(gh)} @{(gh.t.min() + IST):%H:%M}'))
            sats = ', '.join(p_ for _, p_ in sorted(parts))
            frp = g.frp.sum()
            tab.append([str(L), t.strftime('%d %b %H:%M'), sats, f'{frp:.0f}' if len(g) else '-'])
        ax2 = fig.add_axes([0.62, 0.06, 0.37, 0.84]); ax2.axis('off')
        ax2.set_title('Looks (time in IST, detections within 2 h = one look)', fontsize=10, loc='left')
        import textwrap
        yy = 0.97; fs = 8 if len(tab) <= 14 else 6.5; dy = 0.022 if len(tab) <= 14 else 0.017
        ax2.text(0.0, yy, 'look   date, first IST     FRP MW   detections (sensor, count @ time IST)', fontsize=fs, family='monospace', weight='bold', transform=ax2.transAxes)
        yy -= dy * 1.3
        for r_ in tab:
            if yy < 0.01:
                ax2.text(0, yy, '... more looks in results/big_fires_list.csv', fontsize=fs, transform=ax2.transAxes); break
            ax2.text(0.0, yy, f'{r_[0]:>3}', fontsize=fs, family='monospace', weight='bold', color='white', transform=ax2.transAxes,
                     bbox=dict(fc=col(int(r_[0])), ec='none', pad=1))
            ax2.text(0.06, yy, f'{r_[1]}    {r_[3]:>4}', fontsize=fs, family='monospace', transform=ax2.transAxes)
            for k_, line in enumerate(textwrap.wrap(r_[2], 48)):
                ax2.text(0.40, yy, line, fontsize=fs, family='monospace', transform=ax2.transAxes); yy -= dy
            yy -= dy * 0.3
        pdf.savefig(fig); plt.close(fig)
        rows.append(dict(page=n + 1, fire=f.fire, events=f.events, date0=f.date0, date1=f.date1, area_ha=round(f.area_ha), lat=round(lat, 5), lon=round(lon, 5),
                         n_viirs=int((a.sat != 'modis').sum()), n_modis=int((a.sat == 'modis').sum()), n_hotpix=len(hh), n_looks=len(tab),
                         looks=' | '.join(f'{r_[0]}: {r_[1]} {r_[2]}' for r_ in tab)))
pd.DataFrame(rows).to_csv(f'{R}/big_fires_list.csv', index=False)
print(len(rows), 'pages')
