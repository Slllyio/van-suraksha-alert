"""Figures for the best statewide big-fire cases (Akkshay Oct 19 09:30Z: 'select best cases for representation').
Pick: fires with >= 4 looks and scar >= 300 ha, ranked by mean learned-map score over their forecasts, at most 2 per division, top N.
Each fire = one page: up to 4 forecasts (looks 1..4). Grey = final scar, orange = truly burned by +24 h, blue line = 24 h forecast
(blocks + learned area, nearest-first), black dots = VIIRS dots seen so far, red dots = dots of the next 24 h.
  python3 mp_bigfire_figs.py [N]
"""
import sys, json, pickle, numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from scipy.spatial import cKDTree
from shapely.geometry import shape, Point
from shapely.ops import transform as stransform
from pyproj import Transformer
N = int(sys.argv[1]) if len(sys.argv) > 1 else 12; IN = '/tmp/claude-0/mpbig'; OUT = '/mnt/project-files/ratapani/spread/mp_bigfires'
MED = 24.1
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
DV = [(f['properties']['Division'], stransform(lambda x, y, z=None: to43(x, y), shape(f['geometry']))) for f in json.load(open('/mnt/project-files/fire-alert-scars/mp/out/mp_divisions.geojson'))['features']]
def division(x, y):
    p = Point(x, y)
    for n, g in DV:
        if g.contains(p): return n
    return min(DV, key=lambda t: t[1].distance(p))[0] + ' (edge)'
R = pd.read_csv(f'{IN}/mp_bigfire_rows.csv'); R = R[R.skip.isna()] if 'skip' in R else R
F = R.groupby('seed').agg(learned=('learned', 'mean'), rule=('rule', 'mean'), oracle=('oracle', 'mean'), looks=('n_looks', 'first'), scar=('scar_ha', 'first'),
                          x=('x', 'first'), y=('y', 'first'), t=('t', 'first')).reset_index()
F['division'] = [division(a, b) for a, b in zip(F.x, F.y)]; F.to_csv(f'{OUT}/fires_summary.csv', index=False)
C = F[(F.looks >= 4) & (F.scar >= 300)].sort_values('learned', ascending=False)
pick = []; cnt = {}
for r in C.itertuples():
    dv = r.division.replace(' (edge)', '')
    if cnt.get(dv, 0) >= 2: continue
    pick.append(r); cnt[dv] = cnt.get(dv, 0) + 1
    if len(pick) >= N: break
pd.DataFrame(pick).to_csv(f'{OUT}/best_cases.csv', index=False)
with PdfPages(f'{OUT}/best_cases.pdf') as pdf:
    # cover table
    fig, ax = plt.subplots(figsize=(11.7, 8.3)); ax.axis('off')
    ax.set_title('24 h burn-scar map on big unseen fires across Madhya Pradesh: best cases', fontsize=14, loc='left')
    tab = [[i + 1, p.division, p.t[:10], f'{p.scar:.0f}', p.looks, f'{p.rule:.2f}', f'{p.learned:.2f}', f'{p.oracle:.2f}'] for i, p in enumerate(pick)]
    t = ax.table(cellText=tab, colLabels=['#', 'Division', 'First look', 'Scar ha', 'Looks', "Today's rule", 'New map', 'True size'], loc='upper left', cellLoc='center')
    t.scale(1, 1.6); t.set_fontsize(10)
    ax.text(0, .02, f"All {len(F)} fires: today's rule {F.rule.mean():.3f}, new map {F.learned.mean():.3f}, true size {F.oracle.mean():.3f} (mean overlap per fire). "
            "New map = 265 m blocks + learned 24 h area (trained on Ratapani only), nearest-first.", transform=ax.transAxes, fontsize=9, wrap=True)
    pdf.savefig(fig); plt.close(fig)
    for i, p in enumerate(pick):
        z = pickle.load(open(f'{IN}/fire_{p.seed}.pkl', 'rb')); x0, y1, W, H = z['box']; dom, Tg, th, d = z['dom'], z['Tg'], z['th'], z['d']
        rows = R[R.seed == p.seed].sort_values('k').head(4)
        fig, axs = plt.subplots(1, len(rows), figsize=(4.2 * len(rows), 4.8))
        axs = np.atleast_1d(axs); ext = [x0, x0 + W * 20, y1 - H * 20, y1]
        rr, cc = np.mgrid[0:H, 0:W]; P = np.c_[(x0 + (cc + .5) * 20).ravel(), (y1 - (rr + .5) * 20).ravel()]
        for ax, r in zip(axs, rows.itertuples()):
            k = r.k; kn = d[d.lk <= k]; nx = d[(d.lk > k) & (d.lk <= k + 2)]
            xy = kn[['x', 'y']].values; dd = cKDTree(xy).query(P)[0]; foot = dd <= 265
            order = np.argsort(np.where(foot, -1, dd), kind='stable'); m = np.zeros(len(P), bool); m[order[:int(foot.sum() + r.learned_ha / .04)]] = True
            truth = dom & (Tg <= th[k] + 24)
            img = np.ones((H, W, 3)); img[dom] = (.85, .85, .85); img[truth] = (.98, .6, .2)
            ax.imshow(img, extent=ext); ax.contour(m.reshape(H, W), levels=[.5], colors='#1f4e9c', linewidths=1.6, extent=ext, origin='upper')
            ax.scatter(kn.x, kn.y, s=6, c='k', zorder=3); ax.scatter(nx.x, nx.y, s=6, c='r', zorder=3)
            ax.set_title(f'Look {k + 1}  {pd.Timestamp(r.t):%d %b %H:%M} UTC\nnew map {r.learned:.2f}  vs rule {r.rule:.2f}', fontsize=9)
            ax.set_xticks([]); ax.set_yticks([])
            ax.plot([ext[0] + 300, ext[0] + 1300], [ext[2] + 300] * 2, 'k-', lw=2); ax.text(ext[0] + 300, ext[2] + 380, '1 km', fontsize=7)
        fig.suptitle(f'#{i + 1}  {p.division}, {p.t[:10]}: scar {p.scar:.0f} ha, {p.looks} VIIRS looks. Grey = final scar, orange = burned by +24 h, '
                     'blue = 24 h forecast, black = dots so far, red = next dots', fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, .92)); fig.savefig(f'{OUT}/case_{i + 1:02d}.png', dpi=110); pdf.savefig(fig); plt.close(fig)
print('picked', len(pick), [p.division for p in pick])
