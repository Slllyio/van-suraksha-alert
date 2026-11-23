"""C-DAC-style fire fronts for the 146 big fires, checked against the real burn scar (Oct 17, Akkshay: "create the burn scar front as
C-DAC has done" / "are those matched with real burn scars?").
Per fire, two panels on the same hillshade and extent:
  left : C-DAC-style FORECAST. Our physics (Rothermel, 1.5 t/ha loose litter bed, speed x2, leaf fall by date, roads as barriers, no wind,
         ERA5-Land hourly = hindcast weather) started from the FIRST VIIRS look only; fronts at +6/12/24/48 h after that look.
  right: what REALLY happened. The fire-continuity thread's "blend" arrival map inside the scar outline v2 (every VIIRS look pulls each
         20 m pixel's time; 84% of pixels right on 340 mid-fire photos), with fronts at the same hours.
Scores per fire: Sorensen overlap of forecast vs real burned ground at 12/24/48 h, and of the 48 h forecast vs the whole outline; areas.
  FC_SCRATCH=/tmp/claude-0/fronts python3 cdac_fronts.py out.pdf out.csv [n_fires]
"""
import os, sys, io, pickle, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D
from rasterio import features
from rasterio.transform import Affine
from PIL import Image
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
import c0_lib as C
import sim, footprint as fp

OUT_PDF, OUT_CSV = sys.argv[1], sys.argv[2]; NMAX = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 6
BF = '/mnt/project-files/research/big-fires/results'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv').set_index('fire'); L = pd.read_csv(f'{BF}/big_fires_list.csv')
SC = pickle.load(open(f"{os.environ['FC_SCRATCH']}/fire_scars.pkl", 'rb'))
IST = pd.Timedelta(hours=5, minutes=30); HRS = [6, 12, 24, 48]; COL = {6: '#fde725', 12: '#35b779', 24: '#31688e', 48: '#440154'}
CFG = dict(fp.CFG, ign_snap=False, hours=72)
WX = {}


def blend(fire, d, t0):
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = C.rc_of(xs.min() - 1500, ys.max() + 1500); r1, c1 = C.rc_of(xs.max() + 1500, ys.min() - 1500)
    r0, c0 = max(int(r0), 0), max(int(c0), 0); r1, c1 = min(int(r1), C.NR - 1), min(int(c1), C.NC - 1)
    box = C.Box(r0, r1 + 1, c0, c1 + 1)
    tr = Affine(20, 0, C.X0 + box.c0 * 20, 0, -20, C.Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    T, lo, hi, idx, dmin = C.blend_map(box, dom, d, clock=C.Clock(t0), p=4)
    Tg = np.full(box.shape, np.nan); rr, cc = np.where(dom); Tg[rr, cc] = np.where(np.isfinite(T), T, np.nan)
    Dm = np.full(box.shape, np.nan); Dm[rr, cc] = dmin
    return box, dom, Tg, Dm


def physics(fire, d, t0, box):
    s = int(F.season[fire])
    if s not in WX:
        WX.clear(); WX[s] = sim.load_weather(s)
    first = d[d.lk == 0]
    ev = pd.DataFrame(dict(x=first.x.values, y=first.y.values, t=first.t.values, season=s, overpass=first.t.min()))
    ev['t'] = pd.to_datetime(ev.t)
    o = sim.run_event(ev, WX[s], dict(CFG, win=(box.r0, box.r1, box.c0, box.c1)), hours=72)
    Th = o['T'] / 60.0 - (t0 - ev.t.min().floor('h')).total_seconds() / 3600    # hours after the first look
    return Th, first


from matplotlib.colors import ListedColormap, BoundaryNorm
BCM = ListedColormap([COL[6], COL[12], COL[24], COL[48], '#bbbbbb']); BNORM = BoundaryNorm([-1e3, 6, 12, 24, 48, 1e4], 5)


def bands(ax, T, ext, tmax=72):
    ax.imshow(np.ma.masked_invalid(np.where(T <= tmax, T, np.nan)), cmap=BCM, norm=BNORM, extent=ext, alpha=.45, interpolation='nearest')


def soren(a, b):
    return 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


rows, pages = [], []
for page, fire in enumerate(L.fire.tolist()[:NMAX], 1):
    d = C.viirs_looks(A[A.fire == fire]); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    box, dom, Tg, Dm = blend(fire, d, t0)
    Th, first = physics(fire, d, t0, box)
    real = {h: dom & np.isfinite(Tg) & (Tg <= h) for h in HRS}; fc = {h: np.isfinite(Th) & (Th <= h) for h in HRS}
    r = dict(page=page, fire=fire, season=int(F.season[fire]), date=str((t0 + IST).date()), outline_ha=dom.sum() * .04, n_looks=int(d.lk.max() + 1),
             first_look_dots=len(first), hours_seen=round(d.th.max(), 1))
    for h in HRS:
        r[f'real_{h}h_ha'] = real[h].sum() * .04; r[f'fc_{h}h_ha'] = fc[h].sum() * .04; r[f'sor_{h}h'] = round(soren(real[h], fc[h]), 3)
    r['sor_48h_vs_outline'] = round(soren(dom, fc[48]), 3)
    tfit = Th[dom & np.isfinite(Th)]
    r['fc_hours_to_outline_size'] = round(float(np.sort(Th[np.isfinite(Th)])[min(dom.sum(), np.isfinite(Th).sum()) - 1]), 1) if np.isfinite(Th).sum() else np.nan
    r['outline_reached_by_fc_48h'] = round(float((tfit <= 48).sum() / max(dom.sum(), 1)), 3)
    rows.append(r)
    # ---- page
    ls = LightSource(azdeg=315, altdeg=40); hs = ls.hillshade(box.elev, vert_exag=4, dx=20, dy=20)
    ext = [box.X[0, 0] - 10, box.X[0, -1] + 10, box.Y[-1, 0] - 10, box.Y[0, 0] + 10]
    fig, axs = plt.subplots(1, 2, figsize=(14, 7.6)); fig.subplots_adjust(left=.01, right=.99, top=.80, bottom=.10, wspace=.03)
    for ax in axs:
        ax.imshow(hs, cmap='gray', extent=ext, vmin=0, vmax=1)
        ax.contour(box.X, box.Y, dom.astype(float), levels=[.5], colors='red', linewidths=1.6)
        rd = sim.BARRIER[box.r0:box.r1, box.c0:box.c1] if hasattr(sim, 'BARRIER') else None
        if rd is not None:
            ax.contour(box.X, box.Y, rd.astype(float), levels=[.5], colors='black', linewidths=.4, alpha=.6)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect('equal')
        x0 = ext[0] + .04 * (ext[1] - ext[0]); y0 = ext[2] + .04 * (ext[3] - ext[2])
        ax.plot([x0, x0 + 1000], [y0, y0], color='white', lw=3); ax.text(x0 + 500, y0 + 80, '1 km', color='white', ha='center', fontsize=8)
    ax = axs[0]
    bands(ax, np.where(np.isfinite(Th), Th, np.nan), ext)
    for h in HRS:
        if fc[h].any():
            ax.contour(box.X, box.Y, np.nan_to_num(Th, nan=1e6, posinf=1e6), levels=[h], colors=COL[h], linewidths=2)
    ax.scatter(first.x, first.y, s=40, c='orange', edgecolors='black', zorder=5)
    ax.set_title(f"C-DAC-style forecast from the first alert ({(t0 + IST).strftime('%d %b %Y %H:%M')} IST)", fontsize=11)
    ax = axs[1]
    near = Dm <= 600
    bands(ax, np.where(dom, Tg, np.nan), ext, tmax=1e4)
    Tm = np.ma.masked_where(~dom | ~np.isfinite(Tg), Tg)
    for h in HRS:
        if real[h].any() and (~real[h] & dom).any():
            ax.contour(box.X, box.Y, Tm, levels=[h], colors=COL[h], linewidths=1.6)
    ax.scatter(d.x, d.y, s=22, c='white', edgecolors='black', zorder=5)
    for k, g in d.groupby('lk'):
        ax.annotate(str(k + 1), (g.x.mean(), g.y.mean()), fontsize=8, color='white', weight='bold', ha='center', va='center', zorder=6,
                    bbox=dict(boxstyle='circle,pad=0.15', fc='black', alpha=.7, lw=0))
    ax.set_title('What really happened: burn scar and its fronts from all satellite looks', fontsize=11)
    hand = [Line2D([], [], color=COL[h], lw=2, label=f'burned by +{h} h') for h in HRS] + [Line2D([], [], color='#bbbbbb', lw=6, label='after 48 h (forecast: to 72 h)'), Line2D([], [], color='red', lw=1.6, label='real burn scar (v2)')]
    fig.legend(handles=hand, loc='lower center', ncol=6, fontsize=9, frameon=False)
    fig.text(.01, .955, f"Big fire {page}  |  {r['outline_ha']:.0f} ha burn scar  |  seen at {r['n_looks']} satellite looks over {r['hours_seen']:.0f} h",
             fontsize=13, weight='bold')
    fig.text(.01, .875, f"Match with the real scar (1 = perfect, 0 = none):  at 12 h {r['sor_12h']:.2f},  24 h {r['sor_24h']:.2f},  48 h {r['sor_48h']:.2f};  "
             f"48 h forecast vs whole scar {r['sor_48h_vs_outline']:.2f}.\n"
             f"Burned by 24 h: forecast {r['fc_24h_ha']:.0f} ha, real {r['real_24h_ha']:.0f} ha.  "
             f"Looks: " + '; '.join(f"{k + 1} {(g.t.min() + IST).strftime('%d %b %H:%M')}" for k, g in d.groupby('lk'))[:150],
             fontsize=9, va='center')
    buf = io.BytesIO(); fig.savefig(buf, dpi=85, format='png'); plt.close(fig); pages.append(Image.open(buf).convert('RGB'))
    if page % 10 == 0:
        print(page, flush=True); pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
pages[0].save(OUT_PDF, save_all=True, append_images=pages[1:], quality=80, resolution=85)
pages[0].save(OUT_PDF.replace('.pdf', '_page1.png'))
print('done', len(rows))
