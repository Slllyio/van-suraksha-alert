"""A4: regional spread-rate map. Corrected outward speed (A1, nuisance terms held out by season half) per 25 km cell
and per forest type, day and night, with N and 95% cluster-bootstrap CIs.
Is the map real? (1) chi-square of cell speeds around the all-MP mean, against their own bootstrap SEs;
(2) even-season vs odd-season cell speeds (held-out reproducibility), weighted correlation.
Out: results/a4_cells_{25,50}km.csv, a4_forest_types.csv, a4_map.json, fig_a4_map.png"""
import json, os
import numpy as np, pandas as pd, geopandas as gpd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = f'{HERE}/results'
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r20_a'
rng = np.random.default_rng(24); NB = 300
D = pd.read_parquet(f'{SC}/pairs_corr.parquet', columns=['fire', 'dn', 'mx', 'my', 'gap_h', 'p_corr', 'cl', 'vtm', 'season', 'forest'])
D = D[D.fire == 1].copy()
VT = {170: 'agriculture', 26: 'dry deciduous', 25: 'teak', 28: 'teak', 37: 'teak', 23: 'moist deciduous', 106: 'degraded forest', 36: 'sal', 27: 'sal',
      120: 'scrub / grass', 121: 'scrub / grass', 123: 'scrub / grass', 116: 'scrub / grass', 117: 'scrub / grass', 135: 'scrub / grass', 40: 'bamboo', 30: 'bamboo'}
D['ftype'] = D.vtm.map(VT).fillna(pd.Series(np.where(D.vtm.between(11, 119), 'other forest', 'other non-forest'), index=D.index))
def ratio_ci(g, nb=NB):
    cl = pd.factorize(g.cl)[0]; nc = cl.max() + 1; sv = np.bincount(cl, g.p_corr.values, nc); sg = np.bincount(cl, g.gap_h.values, nc)
    m = sv.sum() / sg.sum(); bs = np.array([sv[s].sum() / sg[s].sum() for s in (rng.integers(0, nc, nc) for _ in range(nb))])
    return m, np.quantile(bs, .025), np.quantile(bs, .975), bs.std(), nc
MIN_N = {'D': 500, 'N': 320}     # pairs needed to see 50 m/h with 80% power (pooled thread's power table)
res = {}
for km in (25, 50):
    D['cx'] = np.floor(D.mx / (km * 1000)).astype(int); D['cy'] = np.floor(D.my / (km * 1000)).astype(int)
    rows = []
    for (dn, cx, cy), g in D.groupby(['dn', 'cx', 'cy']):
        if len(g) < 30: rows.append(dict(dn=dn, cx=cx, cy=cy, n=len(g))); continue
        m, lo, hi, se, nc = ratio_ci(g, 200)
        ev, od = g[g.season % 2 == 0], g[g.season % 2 == 1]
        me = ev.p_corr.sum() / ev.gap_h.sum() if len(ev) >= 30 else np.nan; mo = od.p_corr.sum() / od.gap_h.sum() if len(od) >= 30 else np.nan
        rows.append(dict(dn=dn, cx=cx, cy=cy, n=len(g), clusters=nc, speed=round(m, 1), lo=round(lo, 1), hi=round(hi, 1), se=round(se, 2),
                         speed_even=me, speed_odd=mo, n_even=len(ev), n_odd=len(od), forest_share=round(g.forest.mean(), 2)))
    C = pd.DataFrame(rows)
    C['lon'] = (C.cx + .5) * km * 1000 / (111320 * np.cos(np.radians(23.5))) + 78.0; C['lat'] = (C.cy + .5) * km * 1000 / 110574 + 23.5
    C['enough'] = C.n >= C.dn.map(MIN_N)
    C.to_csv(f'{OUT}/a4_cells_{km}km.csv', index=False)
    r = {}
    for dn in 'DN':
        c = C[(C.dn == dn) & C.enough]; d = D[D.dn == dn]; mall = d.p_corr.sum() / d.gap_h.sum()
        chi = float((((c.speed - mall) / c.se) ** 2).sum())
        e = c.dropna(subset=['speed_even', 'speed_odd']); e = e[(e.n_even >= C.dn.map(MIN_N)[e.index] / 2) & (e.n_odd >= C.dn.map(MIN_N)[e.index] / 2)]
        wcor = np.nan
        if len(e) > 5:
            w = 1 / (e.se ** 2); x, y = e.speed_even, e.speed_odd
            mx_, my_ = np.average(x, weights=w), np.average(y, weights=w)
            wcor = float(np.average((x - mx_) * (y - my_), weights=w) / np.sqrt(np.average((x - mx_) ** 2, weights=w) * np.average((y - my_) ** 2, weights=w)))
            # null: same correlation after shuffling cells
            nul = []
            for _ in range(500):
                yy = y.sample(frac=1, random_state=int(rng.integers(1e9))).values
                nul.append(np.average((x - mx_) * (yy - np.average(yy, weights=w)), weights=w) / np.sqrt(np.average((x - mx_) ** 2, weights=w) * np.average((yy - np.average(yy, weights=w)) ** 2, weights=w)))
            p_null = float(np.mean(np.array(nul) >= wcor))
        else: p_null = np.nan
        r[dn] = dict(cells_total=int((C.dn == dn).sum()), cells_enough=len(c), pairs_in_enough=int(c.n.sum()), all_mp_speed=round(mall, 1),
                     cell_speed_p10_p50_p90=[round(float(q), 1) for q in np.quantile(c.speed, [.1, .5, .9])] if len(c) else None,
                     chi2=round(chi, 1), dof=len(c) - 1, cells_ci_excluding_all_mp_mean=int(((c.lo > mall) | (c.hi < mall)).sum()),
                     even_vs_odd_weighted_r=round(wcor, 2) if np.isfinite(wcor) else None, even_odd_cells=len(e), shuffle_p=p_null)
    res[f'{km}km'] = r
# forest types
rows = []
for (dn, ft), g in D.groupby(['dn', 'ftype']):
    m, lo, hi, se, nc = ratio_ci(g, 400)
    rows.append(dict(dn=dn, forest_type=ft, n=len(g), speed=round(m, 1), lo=round(lo, 1), hi=round(hi, 1)))
FT = pd.DataFrame(rows).pivot(index='forest_type', columns='dn'); FT.to_csv(f'{OUT}/a4_forest_types.csv')
res['forest_types'] = pd.DataFrame(rows).to_dict('records')
json.dump(res, open(f'{OUT}/a4_map.json', 'w'), indent=1, default=float); print(json.dumps({k: v for k, v in res.items() if k != 'forest_types'}, indent=1)); print(FT.to_string())
# figure (50 km: 25 km cells are mostly too thin, see a4_cells_25km.csv)
KM = 50
C = pd.read_csv(f'{OUT}/a4_cells_{KM}km.csv')
mp = gpd.read_file('/mnt/project-files/fire-alert-scars/mp/mp_beats_aoi.geojson')
fig, axs = plt.subplots(1, 2, figsize=(13, 5.6))
dx = KM * 1000 / (111320 * np.cos(np.radians(23.5))); dy = KM * 1000 / 110574
for ax, dn, vmax, title in [(axs[0], 'D', 70, 'Day (13:00-14:30 IST)'), (axs[1], 'N', 35, 'Night (01:30-03:00 IST)')]:
    c = C[C.dn == dn]
    norm = TwoSlopeNorm(vmin=-vmax / 2, vcenter=0, vmax=vmax); cmap = plt.get_cmap('RdYlBu_r')
    for _, r in c.iterrows():
        x0, y0 = r.lon - dx / 2, r.lat - dy / 2
        if r.get('enough', False) and np.isfinite(r.speed):
            ax.add_patch(plt.Rectangle((x0, y0), dx, dy, color=cmap(norm(np.clip(r.speed, -vmax / 2, vmax))), lw=0))
            if r.lo > 0: ax.plot(r.lon, r.lat, '.', color='k', ms=2)
        else:
            ax.add_patch(plt.Rectangle((x0, y0), dx, dy, facecolor='none', edgecolor='#999999', hatch='////', lw=0.2))
    mp.boundary.plot(ax=ax, color='#555555', lw=0.2)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap); fig.colorbar(sm, ax=ax, shrink=.75, label='corrected outward speed (m/h)')
    ax.set_xlim(74, 82.9); ax.set_ylim(21, 27); ax.set_aspect(1 / np.cos(np.radians(23.5)))
    ax.set_title(f'{title}: {KM} km cells; hatched = too few pairs (<{MIN_N[dn]}); dot = CI above 0', fontsize=9)
    ax.plot(77.6, 22.95, marker='*', color='k', ms=9); ax.annotate('Ratapani', (77.6, 22.95), xytext=(77.7, 22.6), fontsize=8)
fig.suptitle('Pooled VIIRS small-gap outward speed across Madhya Pradesh, 2018-2026 (edge/geometry terms removed); grey lines = forest beats', fontsize=11)
fig.tight_layout(); fig.savefig(f'{OUT}/fig_a4_map.png', dpi=130)
