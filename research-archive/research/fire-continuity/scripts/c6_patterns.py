"""Patterns in how the 146 big fires fill their outlines, read from the growth maps (walking distance inside the outline).
Each 20 m pixel is assigned to the VIIRS look whose footprints are nearest by walking ("which look burned it") -- this uses
no speed and no day/night clock. Per fire:
  A. growth timeline: share of final area by look, hours to reach 50% / 90% of the outline
  B. day vs night: ground assigned to looks ending a morning gap (01:30 -> 13:30 IST) vs an afternoon/evening gap (13:30 -> 01:30)
  C. fronts: at each look, new footprints (outside all earlier ones) split into groups > 1 km apart = separate fronts;
     share of each look's new ground that is > 600 m walk from everything burned before (a new patch, not an advancing edge)
  D. terrain along the surface: within-fire Spearman of arrival look-time with elevation, local height (valley -/ridge +, 500 m),
     slope, tree cover; null = the same time field rotated 180 deg about the fire centre (keeps its shape, breaks its tie to terrain)
  E. what sits at the edges: ground just outside the outline (40-200 m) vs ground just inside: burned earlier this season
     (burn-label start day < fire start - 2), tree cover, local height, slope, roads
Out: results/patterns_fires.csv, results/patterns_looks.csv, results/patterns.json"""
import sys, os, json, pickle
import numpy as np, pandas as pd
from scipy.stats import spearmanr, wilcoxon
from scipy.ndimage import uniform_filter, distance_transform_edt, label
from rasterio import features
from rasterio.transform import Affine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c0_lib import *

BF = f'{ROOT}/research/big-fires/results'; HERE = f'{ROOT}/research/fire-continuity'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv'); L = pd.read_csv(f'{BF}/big_fires_list.csv')
SC = pickle.load(open(f'{SCRATCH}/fire_scars.pkl', 'rb'))
IST = pd.Timedelta(hours=5, minutes=30)

def rs(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    return spearmanr(a[ok], b[ok])[0] if ok.sum() > 30 and np.ptp(a[ok]) > 0 and np.ptp(b[ok]) > 0 else np.nan

fr, lr = [], []
for fire in L.fire:
    d = viirs_looks(A[A.fire == fire]); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]; f = F[F.fire == fire].iloc[0]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = rc_of(xs.min() - 1500, ys.max() + 1500); r1, c1 = rc_of(xs.max() + 1500, ys.min() - 1500)
    box = Box(int(r0), int(r1) + 1, int(c0), int(c1) + 1)
    tr = Affine(20, 0, X0 + box.c0 * 20, 0, -20, Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    M, idx, rr, cc = box.graph(dom)
    looks = sorted(d.lk.unique()); tl = np.array([d[d.lk == k].th.min() for k in looks])
    fps, Ek = [], []
    for k in looks:
        fp = np.zeros(box.shape, bool)
        for det in d[d.lk == k].itertuples(): fp |= box.footprint(det, dom)
        fps.append(fp); Ek.append(walk(M, idx, fp))
    Ek = np.stack(Ek, 1); Ek[~np.isfinite(Ek)] = 1e7
    who = Ek.argmin(1); Tpx = tl[who]                         # look that burned each pixel
    n = len(rr); share = np.bincount(who, minlength=len(looks)) / n
    # A. timeline
    cum = np.cumsum(share)
    h50 = tl[np.searchsorted(cum, .5)]; h90 = tl[np.searchsorted(cum, .9)]
    # C. fronts and new patches; B. day/night
    region = np.zeros(box.shape, bool)
    for i, k in enumerate(looks):
        new = fps[i] & ~region
        if i > 0:
            g = d[d.lk == k]; prev = d[d.lk < k]
            far = np.hypot(g.x.values[:, None] - prev.x.values[None], g.y.values[:, None] - prev.y.values[None]).min(1) > 400
            nf = 0
            if far.any():   # new dots, grouped into fronts > 1 km apart
                gx = g[far]; lab = -np.ones(len(gx), int); cur = 0
                for j in range(len(gx)):
                    if lab[j] >= 0: continue
                    stack = [j]; lab[j] = cur
                    while stack:
                        a = stack.pop(); dd = np.hypot(gx.x.values - gx.x.values[a], gx.y.values - gx.y.values[a])
                        for b in np.where((dd <= 1000) & (lab < 0))[0]: lab[b] = cur; stack.append(b)
                    cur += 1
                nf = cur
            Dprev = walk(M, idx, region)
            mine = who == i
            lt_ist = (t0 + pd.Timedelta(hours=tl[i]) + IST).hour
            lr.append(dict(fire=fire, look=i, th=tl[i], gap_h=tl[i] - tl[i - 1], look_hour_ist=lt_ist,
                           gap_kind='morning gap (ends ~13:30)' if 9 <= lt_ist <= 17 else ('evening/night gap (ends ~01:30)' if lt_ist <= 5 or lt_ist >= 21 else 'other'),
                           share=share[i], ha=mine.sum() * .04, new_fronts=nf,
                           far_patch_share=float((Dprev[mine] > 600).mean()) if mine.any() else np.nan))
        region |= fps[i]
    # D. terrain along the surface
    el = box.elev; loc = el - uniform_filter(el, 51)                      # + ridge / - valley, ~1 km window
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(el, 20))))
    tree = (box.wc == 10).astype(float)
    cy, cx = np.mean(rr), np.mean(cc)
    rr2 = np.clip(np.round(2 * cy - rr).astype(int), 0, box.shape[0] - 1); cc2 = np.clip(np.round(2 * cx - cc).astype(int), 0, box.shape[1] - 1)
    rec = dict(fire=fire, area_ha=n * .04, n_looks=len(looks), duration_h=tl[-1], month=int(pd.Timestamp(f.date0).month),
               first_look_share=share[0], max_look_share=share.max(), h50=h50, h90=h90,
               looks_holding_half=int(np.searchsorted(np.sort(share)[::-1].cumsum(), .5) + 1))
    for nm, lay in [('elev', el), ('local_height', loc), ('slope', slope), ('tree', tree)]:
        rec[f'r_{nm}'] = rs(Tpx, lay[rr, cc]); rec[f'r0_{nm}'] = rs(Tpx, lay[rr2, cc2])
    # E. edges: just outside (40-200 m) vs just inside (40-200 m)
    din = distance_transform_edt(dom) * 20; dout = distance_transform_edt(~dom) * 20
    inner = dom & (din > 40) & (din <= 200); outer = ~dom & (dout > 40) & (dout <= 200)
    yr = int(f.season); doy0 = pd.Timestamp(f.date0).dayofyear
    bs = G[f'burn_start_{yr}'][box.r0:box.r1, box.c0:box.c1]
    earlier = (bs > -999) & (bs < doy0 - 2)
    crop = np.isin(box.wc, [40, 50]).astype(float); grass = np.isin(box.wc, [20, 30]).astype(float)
    for nm, lay in [('burned_earlier', earlier.astype(float)), ('tree', tree), ('grass_shrub', grass), ('crop_built', crop),
                    ('local_height', loc), ('slope', slope), ('road', box.road.astype(float))]:
        rec[f'in_{nm}'] = float(lay[inner].mean()); rec[f'out_{nm}'] = float(lay[outer].mean())
    # same, only where the ground outside is not crop/built (edges inside the forest)
    o2 = outer & (crop == 0)
    for nm, lay in [('tree', tree), ('local_height', loc)]:
        rec[f'in_{nm}_forestedge'] = float(lay[inner].mean()); rec[f'out_{nm}_forestedge'] = float(lay[o2].mean()) if o2.sum() > 20 else np.nan
    rec['outer_share_crop'] = float(crop[outer].mean())
    fr.append(rec)
X = pd.DataFrame(fr); LK = pd.DataFrame(lr)
X.to_csv(f'{HERE}/results/patterns_fires.csv', index=False); LK.to_csv(f'{HERE}/results/patterns_looks.csv', index=False)

out = {}
q = lambda s: [round(float(v), 3) for v in np.nanpercentile(s, [25, 50, 75])]
out['timeline'] = dict(first_look_share=q(X.first_look_share), max_single_look_share=q(X.max_look_share), h50=q(X.h50), h90=q(X.h90),
                       looks_holding_half=q(X.looks_holding_half), duration_h=q(X.duration_h))
g = LK[LK.gap_kind != 'other'].groupby('gap_kind')
out['day_night'] = g.agg(n=('ha', 'size'), ha_median=('ha', 'median'), ha_per_h_median=('ha', lambda s: float(np.median(s / LK.loc[s.index, 'gap_h']))),
                         share_median=('share', 'median')).round(3).to_dict('index')
out['fronts'] = dict(looks=len(LK), share_looks_with_2plus_new_fronts=round(float((LK.new_fronts >= 2).mean()), 3),
                     share_fires_ever_2plus=round(float(LK.groupby('fire').new_fronts.max().ge(2).mean()), 3),
                     far_patch_share_of_new_ground=q(LK.far_patch_share))
ter = {}
for nm in ['elev', 'local_height', 'slope', 'tree']:
    a, b = X[f'r_{nm}'], X[f'r0_{nm}']; ok = a.notna() & b.notna()
    ter[nm] = dict(median_r=round(float(a.median()), 3), share_positive=round(float((a[ok] > 0).mean()), 3),
                   null_median_r=round(float(b.median()), 3), null_share_positive=round(float((b[ok] > 0).mean()), 3),
                   p_real_vs_null=float(wilcoxon(a[ok], b[ok]).pvalue))
out['terrain_along_growth'] = ter
edg = {}
for nm in ['burned_earlier', 'tree', 'grass_shrub', 'crop_built', 'local_height', 'slope', 'road', 'tree_forestedge', 'local_height_forestedge']:
    a, b = X[f'in_{nm}'], X[f'out_{nm}']; ok = a.notna() & b.notna()
    edg[nm] = dict(inside_mean=round(float(a.mean()), 4), outside_mean=round(float(b.mean()), 4),
                   share_fires_outside_higher=round(float((b[ok] > a[ok]).mean()), 3), p=float(wilcoxon(a[ok], b[ok]).pvalue))
out['edges'] = edg
mon = X.assign(rate=X.area_ha / X.duration_h.clip(lower=1)).groupby('month').agg(n=('fire', 'size'), ha_per_h=('rate', 'median'), area=('area_ha', 'median'))
out['by_month'] = mon.round(2).to_dict('index')
print(json.dumps(out, indent=1, default=str)); json.dump(out, open(f'{HERE}/results/patterns.json', 'w'), indent=1, default=str)
