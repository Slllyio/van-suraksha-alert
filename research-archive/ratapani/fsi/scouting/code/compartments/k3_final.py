"""Step 3. Final (in-sample) compartment plan on 2017-25 repeat patches (>= 5 of 9 seasons) and the geojson.
Same statewide allocation as k2 (greedy over each patch's concave benefit curve), using 2017-25 fires (9 seasons, in-sample).
Out: out/final_patches.csv (one row per patch with n* at each budget), out/final_cuts.csv, out/compartments.geojson
  layers: compartment_2017_25 (compartments of patches cut at the 1000 km budget), cut_2017_25 (cuts, with the first budget that
          takes them), cut_tested_2017_21 (cuts chosen on 2017-21 and taken at the 500 km budget, with their 2022-25 result per patch)."""
import pickle, glob, json
import numpy as np, pandas as pd, shapely, geopandas as gpd
from scipy import ndimage as ndi
from rasterio import features
from rasterio.transform import Affine
import k0 as K
from k2_score import hull, take
from k1_cuts import S4, MINC


def lonlat(x, y): return K.C25.TB.transform(x, y)


def cut_geom(cells, W, x0, y1):
    r, c = cells // W, cells % W
    x = x0 + (c + .5) * K.RES; y = y1 - (r + .5) * K.RES
    lo, la = lonlat(x, y)
    if len(lo) < 2: lo = np.r_[lo, lo + 1e-5]; la = np.r_[la, la]
    return shapely.simplify(shapely.LineString(np.c_[lo, la]), 0.0002)


def compartments(rec, cells_list, W, x0, y1):
    r0, r1, c0, c1 = rec['box']; P = rec['comp_final'] != 0
    P = P | rec['line_final']   # patch cells (compartments, slivers and line cells)
    Lm = np.zeros_like(P)
    for cl in cells_list:
        r, c = cl // W - r0, cl % W - c0; ok = (r >= 0) & (r < P.shape[0]) & (c >= 0) & (c < P.shape[1]); Lm[r[ok], c[ok]] = True
    lab, n = ndi.label(P & ~Lm, S4)
    T = Affine(K.RES, 0, x0 + c0 * K.RES, 0, -K.RES, y1 - r0 * K.RES)
    out = []
    for g, v in features.shapes(lab.astype(np.int32), mask=lab > 0, transform=T):
        poly = shapely.geometry.shape(g)
        out.append((int(v), poly))
    return out, lab


def main():
    items, P, meta = [], {}, {}
    for f in sorted(glob.glob(K.SC + 'cuts_all5_*.pkl')):
        R = pickle.load(open(f, 'rb'))
        if not R['patches']: continue
        key = R['key']
        for r in R['patches']:
            if not r['seq']: continue
            km = np.array([s['km'] for s in r['seq']]); g = np.array([s['g'][0] for s in r['seq']])
            P[(key, r['patch'])] = dict(km=km, g=g, gall=np.array([s['g'] for s in r['seq']]), rec=r, grid=(R['W'], R['x0'], R['y1']), div=R['div'])
            for o, (i, j, k_, v) in enumerate(hull(km, g)): items.append(((key, r['patch']), o, k_, v, j))
    segj = {(it[0], it[1]): it[4] for it in items}
    nst = {}
    curve = []
    for B in sorted(set(list(K.BUDGETS) + [50, 2000, 3000])):
        got, tot = take([it[:4] for it in items], B); last = {}
        for ow, od, k_, v in got: last[ow] = max(last.get(ow, -1), od)
        nst[B] = {ow: segj[(ow, od)] for ow, od in last.items()}
        curve.append(dict(budget=B, km=round(tot, 1), patches=len(nst[B]), cuts=sum(nst[B].values()),
                          insample_patch_ha_yr=round(sum(P[ow]['g'][:n].sum() for ow, n in nst[B].items()), 1),
                          lam=round(min((v / k_ for _, _, k_, v in got), default=np.nan), 3)))
    C = pd.DataFrame(curve); C.to_csv(K.OUT + 'final_budget_curve.csv', index=False); print(C)
    rows, cuts, feats = [], [], []
    for ow, d in P.items():
        key, p = ow; rec = d['rec']; W, x0, y1 = d['grid']
        r0, r1, c0, c1 = rec['box']; pm = (rec['comp_final'] != 0) | rec['line_final']
        rr, cc = np.nonzero(pm); lo, la = lonlat(x0 + (cc.mean() + c0 + .5) * K.RES, y1 - (rr.mean() + r0 + .5) * K.RES)
        row = dict(key=key, division=d['div'], patch=p, lon=round(float(lo), 4), lat=round(float(la), 4), patch_ha=round(rec['n_patch_cells'] * K.CELL_HA, 1),
                   fires_2017_25=rec['n_fires'], cuts_available=len(rec['seq']))
        for B in K.BUDGETS:
            n = nst[B].get(ow, 0); row[f'nstar_{B}'] = n + 1; row[f'km_{B}'] = round(float(d['km'][:n].sum()), 2)
            row[f'insample_ha_yr_{B}'] = round(float(d['g'][:n].sum()), 2); row[f'insample_forest_ha_yr_{B}'] = round(float(d['gall'][:n, 1].sum()), 2)
        rows.append(row)
        first = {}
        for B in sorted(K.BUDGETS, reverse=True):
            for i in range(nst[B].get(ow, 0)): first[i] = B
        for i, s in enumerate(rec['seq']):
            if i not in first: continue
            cuts.append(dict(key=key, division=d['div'], patch=p, order=i + 1, km=round(s['km'], 3), kind=s['kind'], first_budget_km=first[i],
                             insample_patch_ha_yr=round(float(s['g'][0]), 3), insample_forest_ha_yr=round(float(s['g'][1]), 3)))
            feats.append(dict(layer='cut_2017_25', division=d['div'], patch=int(p), order=i + 1, km=round(s['km'], 3), kind=s['kind'], first_budget_km=first[i],
                              insample_patch_ha_yr=round(float(s['g'][0]), 3), geometry=cut_geom(s['cells'], W, x0, y1)))
        n = nst[1000].get(ow, 0)
        if n:
            comps, _ = compartments(rec, [s['cells'] for s in rec['seq'][:n]], W, x0, y1)
            polys = gpd.GeoSeries([g for _, g in comps], crs=32643).to_crs(4326)
            for (v, _), g in zip(comps, polys):
                feats.append(dict(layer='compartment_2017_25', division=d['div'], patch=int(p), compartment=v, nstar_1000=n + 1,
                                  area_ha=round(_.area / 1e4, 1), geometry=shapely.set_precision(shapely.simplify(g, 0.0001), 1e-5)))
    FP = pd.DataFrame(rows).sort_values('insample_ha_yr_500', ascending=False); FP.to_csv(K.OUT + 'final_patches.csv', index=False)
    pd.DataFrame(cuts).to_csv(K.OUT + 'final_cuts.csv', index=False)
    # tested cuts (2017-21 choice, 500 km budget) with 2022-25 per-patch result
    A = pickle.load(open(K.SC + 'alloc.pkl', 'rb'))
    for f in sorted(glob.glob(K.SC + 'cuts_tr3_*.pkl')):
        R = pickle.load(open(f, 'rb')); key = R['key']; byp = {r['patch']: r for r in R['patches']}
        for (k, p), n in A[('comp', 500)].items():
            if k != key: continue
            rec = byp[p]
            for i in range(n):
                s = rec['seq'][i]
                feats.append(dict(layer='cut_tested_2017_21', division=R['div'], patch=int(p), order=i + 1, km=round(s['km'], 3), kind=s['kind'],
                                  train_patch_ha_yr=round(float(s['g'][0]), 3), patch_test_ha_yr_all_cuts=round(float(rec['test_cum'][n - 1, 0]), 3),
                                  geometry=cut_geom(s['cells'], R['W'], R['x0'], R['y1'])))
    G = gpd.GeoDataFrame(feats, geometry='geometry', crs=4326)
    G.to_file(K.OUT + 'compartments.geojson', driver='GeoJSON')
    print(G.layer.value_counts(), flush=True)


if __name__ == '__main__':
    main()
