"""Atlas: forecast vs real for every fire and every VIIRS look (Oct 17, Akkshay: "give me whole atlas of what predicted and what is real").
One page per fire, one panel per look (up to 6, evenly spaced). Forecast = forecast_fronts.forecast() with the all-fire models that
never saw the fire's season (unseen_validation/models_all_fires). Real = blend arrival map inside outline v2.
  FC_SCRATCH=/tmp/claude-0/fronts python3 uv_atlas.py prefix label out_dir chunk nchunks
"""
import os, sys, pickle, warnings, numpy as np, pandas as pd, matplotlib
warnings.filterwarnings('ignore'); matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from rasterio import features
from rasterio.transform import Affine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forecast_fronts as FF
C = FF.C
PRE, LABEL, OUT, CH, NCH = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
MD = '/mnt/project-files/ratapani/spread/unseen_validation/models_all_fires'
X0, Y0 = 737300.0, 2560500.0; IST = pd.Timedelta(hours=5, minutes=30)
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
Fz = pd.read_csv('/mnt/project-files/research/big-fires/results/fires.csv').set_index('fire')
I = pd.read_parquet(f'{PRE}_issues.parquet'); M = pickle.load(open(f'{PRE}_maps.pkl', 'rb'))
S = pd.read_csv(f'{PRE}_apply_loso_issues.csv').set_index(['fire', 'k'])
SC = pickle.load(open(f"{os.environ['FC_SCRATCH']}/fire_scars.pkl", 'rb'))
MOD = {}
fires = sorted(I.fire.unique()); fires = fires[CH::NCH]
os.makedirs(OUT, exist_ok=True)
cm = ListedColormap(['#9e9e9e', '#f39c12'])
for n, fire in enumerate(fires):
    g = I[I.fire == fire].sort_values('k'); s = int(g.season.iloc[0])
    if s not in MOD:
        MOD[s] = (FF.lgb.Booster(model_file=f'{MD}/growth24_{s}.txt'), FF.lgb.Booster(model_file=f'{MD}/stop24_{s}.txt'))
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg, dom = mp['Tg'], mp['dom']
    elev = C.ELEV[r0:r1, c0:c1].astype(float); hs = LightSource(azdeg=315, altdeg=40).hillshade(elev, vert_exag=4, dx=20, dy=20)
    tr = Affine(20, 0, X0 + c0 * 20, 0, -20, Y0 - r0 * 20); ext = (X0 + c0 * 20, X0 + c1 * 20, Y0 - r1 * 20, Y0 - r0 * 20)
    allg = A[A.fire == fire]; dl = C.viirs_looks(allg)
    ks = g.k.values if len(g) <= 6 else g.k.values[np.unique(np.linspace(0, len(g) - 1, 6).round().astype(int))]
    nc = min(len(ks), 3); nr = int(np.ceil(len(ks) / nc))
    fig, axs = plt.subplots(nr, nc, figsize=(4.6 * nc, 4.6 * nr + .9), squeeze=False)
    poly = SC[fire]
    bx = np.r_[poly.bounds[0], poly.bounds[2], allg.x.min(), allg.x.max()]; by = np.r_[poly.bounds[1], poly.bounds[3], allg.y.min(), allg.y.max()]
    zx = (max(bx.min() - 700, ext[0]), min(bx.max() + 700, ext[1])); zy = (max(by.min() - 700, ext[2]), min(by.max() + 700, ext[3]))
    for ax, k in zip(axs.ravel(), ks):
        it = g[g.k == k].iloc[0]; tiss = dl[dl.lk == k].t.max()
        d, kk, feats, foot, fc, band = FF.forecast(allg.copy(), tiss, MOD[s])
        before = dom & (Tg <= it.th); new = dom & (Tg > it.th) & (Tg <= it.th + 24)
        lay = np.full(dom.shape, np.nan); lay[before] = 0; lay[new] = 1
        ax.imshow(hs, cmap='gray', extent=ext, vmin=0, vmax=1, alpha=.55)
        ax.imshow(lay, cmap=cm, extent=ext, vmin=0, vmax=1, alpha=.75, interpolation='nearest')
        for geom, col, lw, ls in [(poly, 'red', .8, '-'), (fc, '#1f4fe0', 1.8, '-'), (foot, 'k', .7, ':')]:
            gs = getattr(geom, 'geoms', [geom])
            for p in gs:
                if p.is_empty:
                    continue
                x, y = p.exterior.xy; ax.plot(x, y, color=col, lw=lw, ls=ls)
        old = d[d.lk < kk]; last = d[d.lk == kk]
        ax.scatter(old.x, old.y, s=6, c='k', zorder=5); ax.scatter(last.x, last.y, s=28, c='#e01f1f', edgecolor='k', lw=.5, zorder=6)
        for f, kind, act, gx, grow, pstop in feats:
            if act:
                cx, cy = gx.mean(0); ax.text(cx, cy, f' {grow:.0f} ha\n stop {pstop:.0%}', fontsize=8, color='#0b2a8a', fontweight='bold', zorder=7)
        sc = S.loc[(fire, int(k))]
        ax.set_title(f"look {k + 1}  {(tiss + IST):%d %b %H:%M} IST\nforecast +{sc.fc_ha - sc.foot_ha:.0f} ha | real +{it.new24_ha:.0f} ha | "
                     f"overlap {sc.sor_tool:.2f} (24 ha rule {sc.sor_blob_median:.2f})", fontsize=8)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_xlim(zx); ax.set_ylim(zy); ax.set_aspect('equal')
    for ax in axs.ravel()[len(ks):]:
        ax.axis('off')
    ss = S.loc[fire]
    fig.suptitle(f"{LABEL} | fire {fire} | season {s} | scar {Fz.area_ha[fire]:.0f} ha | {int(g.k.max()) + 1} looks | "
                 f"mean 24 h overlap: forecast {ss.sor_tool.mean():.2f}, dots only {ss.sor_foot.mean():.2f}, 24 ha rule {ss.sor_blob_median.mean():.2f}",
                 fontsize=10)
    fig.legend(handles=[Patch(color='#9e9e9e', label='really burned before the look'), Patch(color='#f39c12', label='really burned in the next 24 h'),
                        Line2D([], [], color='#1f4fe0', lw=1.8, label='forecast: burned by +24 h'), Line2D([], [], color='k', ls=':', label='375 m blocks so far'),
                        Line2D([], [], color='red', lw=.8, label='final scar outline v2'),
                        Line2D([], [], marker='o', ls='', color='#c0392b', label='dots at this look'), Line2D([], [], marker='o', ls='', color='k', ms=3, label='earlier dots')],
               loc='lower center', ncol=7, fontsize=7, frameon=False)
    plt.tight_layout(rect=(0, .03, 1, .96)); fig.savefig(f'{OUT}/{fire:05d}.jpg', dpi=80, pil_kwargs=dict(quality=72)); plt.close(fig)
    if n % 25 == 0:
        print(CH, n, len(fires), flush=True)
print('done', CH, flush=True)
