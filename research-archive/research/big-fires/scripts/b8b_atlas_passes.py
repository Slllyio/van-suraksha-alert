"""Atlas v2 (Akkshay 20:06Z): one page per big fire, EVERY satellite pass its own number, time and colour; nothing merged.
Left: scar (v2) grey; each detection as its real block (VIIRS solid, MODIS dashed, Sentinel-2/Landsat hot pixels as dots),
coloured by time; pass number printed at the pass centre. Right: one line per pass: time IST, satellite, detections,
FRP, pixel size, minutes since the previous pass. Bottom: front distance from the start area against time, with the
robust speed line fitted through all passes (b12).
Out: figures/big_fires_atlas.pdf (replaces the look-merged version)
"""
import pickle, os, textwrap
import numpy as np, pandas as pd, pyproj
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
R = '/mnt/project-files/research/big-fires/results'; FG = '/mnt/project-files/research/big-fires/figures'
SP = f'{R}/fire_scars.pkl' if os.path.exists(f'{R}/fire_scars.pkl') else '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/fire_scars.pkl'
S = pickle.load(open(SP, 'rb'))
F = pd.read_csv(f'{R}/fires.csv'); P = pd.read_csv(f'{R}/passes.csv', parse_dates=['t', 't_ist']); D = pd.read_csv(f'{R}/detections.csv', parse_dates=['t', 't_ist'])
FS = pd.read_csv(f'{R}/front_speed.csv').set_index('fire')
B = F[F.fire.isin(P[P.big].fire.unique())].sort_values(['season', 'date0']).reset_index(drop=True)
inv = pyproj.Transformer.from_crs(32643, 4326, always_xy=True).transform
COL = {'S-NPP': 'tab:blue', 'NOAA-20': 'tab:green', 'NOAA-21': 'tab:olive', 'Terra MODIS': 'tab:purple', 'Aqua MODIS': 'tab:pink', 'MODIS': 'tab:pink',
       'Sentinel-2': 'tab:red', 'Landsat': 'tab:orange'}
with PdfPages(f'{FG}/big_fires_atlas.pdf') as pdf:
    for n, f in B.iterrows():
        poly = S[f.fire]; p = P[P.fire == f.fire].sort_values('t').reset_index(drop=True); p['num'] = np.arange(1, len(p) + 1)
        d = D[D.fire == f.fire].merge(p[['pass_id', 'num']], on='pass_id')
        t0 = p.t.min(); hrs = (p.t - t0).dt.total_seconds() / 3600; Hmax = max(hrs.max(), 1); cm = plt.cm.turbo
        colt = lambda t: cm(((t - t0).total_seconds() / 3600) / Hmax)
        fig = plt.figure(figsize=(17, 11))
        ax = fig.add_axes([0.03, 0.30, 0.55, 0.62])
        for g in getattr(poly, 'geoms', [poly]):
            xs, ys = g.exterior.xy; ax.fill(xs, ys, color='0.88', ec='k', lw=0.8)
            for hole in g.interiors: xs, ys = hole.xy; ax.fill(xs, ys, color='white', ec='k', lw=0.4)
        for r in d.itertuples():
            c = colt(r.t)
            if r.sensor in ('Sentinel-2', 'Landsat'): ax.plot(r.x, r.y, 's', ms=2.5, color=c)
            else:
                md = 'MODIS' in r.sensor
                ax.add_patch(Rectangle((r.x - r.pix_w_m / 2, r.y - r.pix_h_m / 2), r.pix_w_m, r.pix_h_m, fc='none', ec=c, lw=0.8 if md else 1.4, ls='--' if md else '-'))
        for r in p.itertuples():
            ax.text(r.x, r.y, str(r.num), fontsize=7.5, weight='bold', color=colt(r.t), ha='center', va='center', bbox=dict(fc='white', ec=colt(r.t), alpha=0.8, pad=0.8))
        x0, y0, x1, y1 = poly.bounds; pad = 900
        ax.set_xlim(min(x0, d.x.min()) - pad, max(x1, d.x.max()) + pad); ax.set_ylim(min(y0, d.y.min()) - pad, max(y1, d.y.max()) + pad); ax.set_aspect('equal')
        xt, yt = ax.get_xticks(), ax.get_yticks(); xl, yl = ax.get_xlim(), ax.get_ylim()
        ax.set_xticks(xt); ax.set_xticklabels([f'{inv(v_, (y0 + y1) / 2)[0]:.3f}E' for v_ in xt], fontsize=7)
        ax.set_yticks(yt); ax.set_yticklabels([f'{inv((x0 + x1) / 2, v_)[1]:.3f}N' for v_ in yt], fontsize=7); ax.set_xlim(xl); ax.set_ylim(yl)
        sx, sy = xl[1] - 1400, yl[0] + 300; ax.plot([sx, sx + 1000], [sy, sy], 'k-', lw=3); ax.text(sx + 500, sy + 80, '1 km', ha='center', fontsize=8)
        ax.plot([], [], 'k-', lw=1.4, label='VIIRS block (real size)'); ax.plot([], [], 'k--', lw=0.8, label='MODIS block (real size)')
        ax.plot([], [], 'ks', ms=3, label='Sentinel-2/Landsat hot pixel'); ax.legend(loc='lower left', fontsize=8)
        lat, lon = inv(poly.centroid.x, poly.centroid.y)[::-1]
        ax.set_title(f'Big fire {n + 1} of {len(B)} (fire id {f.fire})   scar {f.area_ha:.0f} ha, centre {lat:.4f}N {lon:.4f}E, {f.date0} to {f.date1}\n'
                     f'{len(p)} satellite passes; colour = hours since the first pass (blue early, red late); number = pass', fontsize=10, loc='left')
        # pass table
        ax2 = fig.add_axes([0.60, 0.03, 0.39, 0.92]); ax2.axis('off')
        fs = 7.5 if len(p) <= 34 else 6
        dy = 0.026 if len(p) <= 34 else 0.0175
        yy = 0.99
        ax2.text(0, yy, ' #  date   time IST  satellite     dets  FRP MW  pixel m    gap', fontsize=fs, family='monospace', weight='bold', transform=ax2.transAxes)
        yy -= dy
        for r in p.itertuples():
            if yy < 0.005: ax2.text(0, yy, '... more passes in results/passes.csv', fontsize=fs, transform=ax2.transAxes); break
            gap = '' if pd.isna(r.gap_from_prev_min) else (f'{r.gap_from_prev_min:5.0f} min' if r.gap_from_prev_min < 180 else f'{r.gap_from_prev_min / 60:5.1f} h')
            frp = '' if (pd.isna(r.frp_sum) or r.sensor in ('Sentinel-2', 'Landsat')) else f'{r.frp_sum:6.1f}'
            pix = f'{r.pix_w_m:4.0f}x{r.pix_h_m:<4.0f}' if r.sensor not in ('Sentinel-2', 'Landsat') else '  20-30  '
            ax2.text(0, yy, f'{r.num:>2}', fontsize=fs, family='monospace', weight='bold', color='white', transform=ax2.transAxes, bbox=dict(fc=colt(r.t), ec='none', pad=0.8))
            ax2.text(0.045, yy, f' {r.t_ist:%d %b %H:%M}  {r.sensor:<12} {r.n:>4}  {frp:>6}  {pix} {gap}', fontsize=fs, family='monospace', transform=ax2.transAxes,
                     color=COL.get(r.sensor, 'k'))
            yy -= dy
        # front distance vs time
        ax3 = fig.add_axes([0.06, 0.05, 0.50, 0.19])
        st = p[p.t <= t0 + pd.Timedelta(hours=2)]; ox, oy = st.x.mean(), st.y.mean()
        for r in p.itertuples():
            dd = d[d.pass_id == r.pass_id]; fr = np.hypot(dd.x - ox, dd.y - oy).max() if r.sensor not in ('Sentinel-2', 'Landsat') else np.hypot(r.x - ox, r.y - oy)
            ax3.plot((r.t - t0).total_seconds() / 3600, fr, 'o', color=COL.get(r.sensor, 'k'), ms=5)
            ax3.text((r.t - t0).total_seconds() / 3600, fr, f' {r.num}', fontsize=6)
        if f.fire in FS.index and np.isfinite(FS.loc[f.fire].get('all_speed_m_per_h', np.nan)):
            s_ = FS.loc[f.fire]; xx = np.array([0, Hmax])
            med = np.median([np.hypot(dd.x - ox, dd.y - oy).max() for _, dd in d[~d.sensor.isin(['Sentinel-2', 'Landsat'])].groupby('pass_id')])
            ax3.set_title(f'Front distance from the start area. Robust fit through all passes: {s_.all_speed_m_per_h:.0f} m/h '
                          f'(95% range {s_.all_speed_lo:.0f} to {s_.all_speed_hi:.0f}); VIIRS only {s_.viirs_speed_m_per_h:.0f} m/h', fontsize=9, loc='left')
        for k_, c_ in COL.items():
            if k_ in set(p.sensor): ax3.plot([], [], 'o', color=c_, label=k_)
        ax3.legend(fontsize=7, ncol=4, loc='upper left'); ax3.set_xlabel('hours since first pass'); ax3.set_ylabel('m')
        pdf.savefig(fig); plt.close(fig)
print(len(B), 'pages')
