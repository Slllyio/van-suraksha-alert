"""New question 4. Which side of each repeat patch is downwind in the burn window, and does the wind actually say where a
fire from the patch goes? ERA5 10 m wind (scratch era5wind/, n4_fetch_wind.py: 06/09/12 UTC, 15 Feb-15 Mar 2017-25, 0.25 deg).
(a) Test: every scar fire 2017-25 starting inside a tr3 patch between 15 Feb and 15 Mar that burnt 10+ ha outside the patch:
    bearing from its ignition cells to the outside burnt ground, against the afternoon wind of its first two days at the nearest
    ERA5 cell, and against the patch's late-February wind climatology. Random = 25% within 45 deg, 50% within 90 deg.
(b) Per patch: late-Feb (15-28 Feb) and early-March (1-15 Mar) downwind bearing, constancy (resultant / mean speed), mean speed,
    dominant octant and its share of afternoon hours, years (of 9) whose dominant octant agrees.
Out: out/n4_escapes.csv, out/n4_test.csv, out/n4_patches.csv, out/n4_divisions.csv, figs_r30/r30_fig10_wind.png"""
import os, sys, glob
import numpy as np, pandas as pd
from pyproj import Transformer
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/')
import cb0 as B
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'; FIG = '/mnt/project-files/ratapani/fsi/scouting/figs_r30/'
WD = B.SCR + 'era5wind/'; INV = Transformer.from_crs(32643, 4326, always_xy=True)
OCT = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
def octant(b): return OCT[int(((b + 22.5) % 360) // 45)]
def to_bearing(u, v): return np.degrees(np.arctan2(u, v)) % 360          # direction the wind blows TOWARD
def angdiff(a, b): return ((a - b + 180) % 360) - 180
# wind: daily afternoon mean per day
U, V, DAYS = {}, {}, {}
for y in range(2017, 2026):
    Z = np.load(WD + f'wind_{y}.npz', allow_pickle=True); lat, lon = Z['lat'], Z['lon']
    u = Z['u'].mean(1); v = Z['v'].mean(1)
    for i, d in enumerate(Z['days']): U[str(d)] = u[i]; V[str(d)] = v[i]
def gi(la, lo): return int(np.argmin(np.abs(lat - la))), int(np.argmin(np.abs(lon - lo)))
def clim(i, j, m0, d0, m1, d1):
    """mean vector over all years' afternoons in window (m0/d0..m1/d1) at cell i,j"""
    uu, vv, yrs = [], [], {}
    for d in U:
        t = pd.Timestamp(d)
        if (t.month, t.day) >= (m0, d0) and (t.month, t.day) <= (m1, d1):
            uu.append(U[d][i, j]); vv.append(V[d][i, j]); yrs.setdefault(t.year, []).append((U[d][i, j], V[d][i, j]))
    uu, vv = np.array(uu), np.array(vv); sp = np.hypot(uu, vv)
    mu, mv = uu.mean(), vv.mean(); bear = to_bearing(mu, mv); const = np.hypot(mu, mv) / sp.mean()
    octs = pd.Series([octant(b) for b in to_bearing(uu, vv)]); dom = octs.value_counts(); dom_oct = dom.index[0]; dom_share = dom.iloc[0] / len(octs)
    agree = sum(1 for y, a in yrs.items() if octant(to_bearing(np.mean([p[0] for p in a]), np.mean([p[1] for p in a]))) == octant(bear))
    return dict(bear=bear, const=const, speed=sp.mean(), dom_oct=dom_oct, dom_share=dom_share, years_agree=agree)
# (a) escapes
rows = []; YI = range(2017, 2026)
for key in B.KEYS:
    L, FOR = B.load_div(key); Zp = np.load(B.SC26 + f'patches_{key}.npz'); lab = Zp['lab_tr3']
    if lab.max() == 0: continue
    H, W = L['H'], L['W']
    for f in L['fires']:
        if f['year'] not in YI: continue
        t0 = (f['t0'] + pd.Timedelta(hours=5.5)).normalize(); md = (t0.month, t0.day)
        if md < (2, 15) or md > (3, 14): continue
        h, w = f['shape']; Mm = np.unpackbits(f['M'])[:h * w].astype(bool).reshape(h, w)
        ig = f['ign']; ir, ic = ig // w + f['r0'], ig % w + f['c0']
        pl = lab[np.clip(ir // 2, 0, lab.shape[0] - 1), np.clip(ic // 2, 0, lab.shape[1] - 1)]
        vals, cnt = np.unique(pl[pl > 0], return_counts=True)
        if len(vals) == 0 or cnt.max() < 0.5 * len(pl): continue
        pid = int(vals[np.argmax(cnt)])
        rr, cc = np.nonzero(Mm); rr = rr + f['r0']; cc = cc + f['c0']
        inside = lab[np.clip(rr // 2, 0, lab.shape[0] - 1), np.clip(cc // 2, 0, lab.shape[1] - 1)] == pid
        n_out = (~inside).sum(); out_ha = n_out * B.CELL_HA
        if out_ha < 10: continue
        x0, y0 = L['x0'] + ic.mean() * B.RES, L['y1'] - ir.mean() * B.RES
        x1, y1 = L['x0'] + cc[~inside].mean() * B.RES, L['y1'] - rr[~inside].mean() * B.RES
        esc = np.degrees(np.arctan2(x1 - x0, y1 - y0)) % 360
        lo, la = INV.transform(x0, y0); i, j = gi(la, lo)
        ds = [d for d in (t0.strftime('%Y-%m-%d'), (t0 + pd.Timedelta(days=1)).strftime('%Y-%m-%d')) if d in U]
        if not ds: continue
        u = np.mean([U[d][i, j] for d in ds]); v = np.mean([V[d][i, j] for d in ds])
        rows.append(dict(key=key, fire=f['fire'], year=f['year'], date=t0.date(), doy=t0.dayofyear, patch=pid, ha=f['ha'], out_ha=out_ha, dist_km=np.hypot(x1 - x0, y1 - y0) / 1000,
                         esc_bear=esc, wind_to=to_bearing(u, v), speed=np.hypot(u, v), gi=i, gj=j, lat=la, lon=lo))
    print(key, len(rows), flush=True)
E = pd.DataFrame(rows)
cl = {}
for (i, j) in set(zip(E.gi, E.gj)): cl[(i, j)] = clim(i, j, 2, 15, 2, 28)
E['clim_to'] = [cl[(i, j)]['bear'] for i, j in zip(E.gi, E.gj)]; E['clim_const'] = [cl[(i, j)]['const'] for i, j in zip(E.gi, E.gj)]
E['d_day'] = angdiff(E.esc_bear, E.wind_to); E['d_clim'] = angdiff(E.esc_bear, E.clim_to)
E.to_csv(OUT + 'n4_escapes.csv', index=False)
def summ(d, col, name):
    a = np.abs(d[col]); keys = d.key.values; uk = np.unique(keys); bs = []
    rng = np.random.default_rng(0)
    for _ in range(300):
        pick = rng.choice(uk, len(uk)); m = np.concatenate([np.nonzero(keys == k)[0] for k in pick]); bs.append((a.values[m] <= 90).mean())
    return dict(test=name, fires=len(d), within_45=(a <= 45).mean(), within_90=(a <= 90).mean(), within_90_ci_lo=np.percentile(bs, 2.5), within_90_ci_hi=np.percentile(bs, 97.5), mean_cos=np.cos(np.radians(d[col])).mean(), random_45=0.25, random_90=0.5)
T = [summ(E, 'd_day', 'wind of the fire days, all escapes'), summ(E, 'd_clim', 'late-Feb climatology, all escapes')]
for lo_, hi_, nm in ((10, 50, '10-50 ha outside'), (50, 200, '50-200 ha outside'), (200, 1e9, '200+ ha outside')):
    d = E[(E.out_ha >= lo_) & (E.out_ha < hi_)]; T.append(summ(d, 'd_day', f'fire-day wind, {nm}')); T.append(summ(d, 'd_clim', f'climatology, {nm}'))
q = E.speed.quantile([1 / 3, 2 / 3]).values
for nm, d in (('calm third (fire-day wind)', E[E.speed < q[0]]), ('windy third (fire-day wind)', E[E.speed >= q[1]])): T.append(summ(d, 'd_day', nm))
T.append(summ(E[E.doy <= 59], 'd_day', 'fire-day wind, 15-28 Feb starts')); T.append(summ(E[E.doy > 59], 'd_day', 'fire-day wind, 1-14 Mar starts'))
T.append(summ(E[E.clim_const >= E.clim_const.median()], 'd_clim', 'climatology, steadier half of cells'))
T = pd.DataFrame(T); T.to_csv(OUT + 'n4_test.csv', index=False); print(T.round(3).to_string(index=False))
# (b) per patch climatology
P = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/j1_patches.csv')
cells = {}
out = []
for r in P.itertuples():
    i, j = gi(r.lat, r.lon)
    if (i, j) not in cells: cells[(i, j)] = (clim(i, j, 2, 15, 2, 28), clim(i, j, 3, 1, 3, 15))
    a, b = cells[(i, j)]
    out.append(dict(key=r.key, division=r.division, patch=r.patch, pid=r.pid, forest_ha=r.forest_ha, rank=r.rank, tier=r.tier, role_S3=r.role_S3, lat=r.lat, lon=r.lon,
                    feb_downwind_bearing=a['bear'], feb_downwind_side=octant(a['bear']), feb_constancy=a['const'], feb_speed_ms=a['speed'], feb_dominant_octant=a['dom_oct'], feb_dominant_share=a['dom_share'], feb_years_agree_of_9=a['years_agree'],
                    mar_downwind_bearing=b['bear'], mar_downwind_side=octant(b['bear']), mar_constancy=b['const'], mar_speed_ms=b['speed'], mar_years_agree_of_9=b['years_agree']))
PW = pd.DataFrame(out); PW.to_csv(OUT + 'n4_patches.csv', index=False)
D = PW.groupby('division').agg(patches=('pid', 'size'), feb_side=('feb_downwind_side', lambda s: s.value_counts().index[0]), feb_constancy=('feb_constancy', 'mean'), feb_speed_ms=('feb_speed_ms', 'mean'), feb_years_agree=('feb_years_agree_of_9', 'mean'), mar_side=('mar_downwind_side', lambda s: s.value_counts().index[0]), mar_constancy=('mar_constancy', 'mean')).reset_index()
D.to_csv(OUT + 'n4_divisions.csv', index=False)
print('first programme patches by Feb downwind side:', PW[PW.role_S3 == 'burn'].feb_downwind_side.value_counts().to_dict())
print('constancy quartiles (Feb):', PW.feb_constancy.quantile([.25, .5, .75]).round(2).tolist(), 'years agree median', PW.feb_years_agree_of_9.median())
# figure
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(9, 8))
sc = ax.scatter(PW.lon, PW.lat, c=PW.feb_constancy, s=6, cmap='viridis', vmin=0, vmax=1, zorder=2)
I, J = np.meshgrid(np.arange(len(lat)), np.arange(len(lon)), indexing='ij')
mu = np.mean([np.array([U[d] for d in U if (pd.Timestamp(d).month, pd.Timestamp(d).day) >= (2, 15) and pd.Timestamp(d).month == 2])], axis=(0, 1)); mv = np.mean([np.array([V[d] for d in V if (pd.Timestamp(d).month, pd.Timestamp(d).day) >= (2, 15) and pd.Timestamp(d).month == 2])], axis=(0, 1))
LO, LA = np.meshgrid(lon, lat); ax.quiver(LO, LA, mu, mv, color='0.3', scale=40, width=0.0025, zorder=3)
plt.colorbar(sc, ax=ax, label='wind constancy, 15-28 Feb afternoons 2017-25 (1 = always the same way)')
ax.set_xlim(74, 82.8); ax.set_ylim(21.0, 26.8); ax.set_aspect(1 / np.cos(np.radians(23.5))); ax.set_xlabel('longitude'); ax.set_ylabel('latitude')
ax.set_title('Late-Feb afternoon wind 2017-25 (arrows) and repeat patches coloured by wind constancy')
fig.tight_layout(); fig.savefig(FIG + 'r30_fig10_wind.png', dpi=150); print('fig saved')
