"""Step 5. Tables, bootstrap ranges, figures and geojson for repeat_patch_fire_lines.md.
Out: out/tables.json, out/division_table.csv, out/test_lines.csv, out/top_patches.csv, out/fig_*.png, out/repeat_patches_lines.geojson"""
import pickle, glob, json
import numpy as np, pandas as pd, shapely, geopandas as gpd
from rasterio import features
from rasterio.transform import Affine
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import c26 as C

RNG = np.random.default_rng(55); NB = 1000
SETN = lambda k: 'core' if k in C.CORE else 'rest'
T = {}


def rates_by_year():
    """Step 1: patch counts, forest, share of each season's burnt forest inside the patches."""
    P = pd.read_csv(C.SC + 'patch_stats.csv'); P['grp'] = P.key.map(SETN)
    rows = []
    for (grp, s), g in pd.concat([P, P.assign(grp='all MP')]).groupby(['grp', 'set']):
        r = dict(grp=grp, set=s, n_patches=int(g.n_patches.sum()), patch_kha=round(g.patch_forest_ha.sum() / 1e3, 1),
                 pct_forest=round(100 * g.patch_forest_ha.sum() / g.forest_ha.sum(), 2))
        for y in C.ALL: r[y] = round(100 * g[f'inpatch_{y}'].sum() / max(g[f'burnt_{y}'].sum(), 1), 1)
        tr = [y for y in C.TRAIN]; te = list(C.TEST)
        r['in_train_yrs'] = round(100 * sum(g[f'inpatch_{y}'].sum() for y in tr) / sum(g[f'burnt_{y}'].sum() for y in tr), 1)
        r['in_test_yrs'] = round(100 * sum(g[f'inpatch_{y}'].sum() for y in te) / sum(g[f'burnt_{y}'].sum() for y in te), 1)
        rows.append(r)
    R = pd.DataFrame(rows); T['step1'] = R.to_dict('records')
    burnt = {grp: {y: float(g[f'burnt_{y}'].sum()) for y in C.ALL} for grp, g in pd.concat([P, P.assign(grp='all MP')])[lambda d: d.set == 'tr3'].groupby('grp')}
    T['burnt_forest_ha'] = burnt
    # how often 120 m forest cells burn (2017-25) vs if seasons were independent
    hist = {}
    for grp in ('core', 'rest', 'all MP'):
        obs = np.zeros(10); exp = np.zeros(10)
        for p in glob.glob(C.SC + 'patches_*.npz'):
            k = p.split('patches_')[1][:-4]
            if grp != 'all MP' and SETN(k) != grp: continue
            Z = np.load(p); m = (Z['fb'] >= 2) & Z['ins']; ca = Z['cnt_all'][m]
            obs += np.bincount(ca, minlength=10)[:10]
        T.setdefault('hist', {})[grp] = obs.tolist()
    # independence: each season burns a share q_y of forest cells at random
    for grp in ('core', 'rest', 'all MP'):
        n = np.array(T['hist'][grp]); N = n.sum()
        P_ = pd.read_csv(C.SC + 'patch_stats.csv'); P_ = P_[P_.set == 'tr3']
        if grp != 'all MP': P_ = P_[P_.key.map(SETN) == grp]
        if not len(P_): continue
        q = [P_[f'burnt_{y}'].sum() / P_.forest_ha.sum() for y in C.ALL]
        dist = np.array([1.0])
        for qq in q: dist = np.convolve(dist, [1 - qq, qq])
        T.setdefault('hist_indep', {})[grp] = (dist * N).tolist()
    return R


def boot(groups, fn):
    """fn(list of per-division index arrays) -> statistic; resample fires within each division."""
    out = []
    for _ in range(NB):
        out.append(fn([RNG.integers(0, n, n) if n else np.zeros(0, int) for n in groups]))
    return np.percentile(out, [2.5, 97.5])


def test_tables():
    R = {}
    for p in sorted(glob.glob(C.SC + 'test_tr3_*.pkl')):
        r = pickle.load(open(p, 'rb')); R[r['key']] = r
    ny = len(C.TEST); nyt = len(C.TRAIN)
    M = ['entry', 'rand_edge', 'ring', 'road', 'r25_same_km', 'r25_20km']
    rows = []
    for grp in ('core', 'rest', 'all MP'):
        G = [r for k, r in R.items() if grp == 'all MP' or SETN(k) == grp]
        if not G: continue
        for pstop in (0.35, 1.0):
            for m in M:
                for w, wi in (('all', 0), ('patch', 1)):
                    if m.startswith('r25') and w == 'patch': continue
                    km = sum(r['test']['comb'][(m, pstop)][2] for r in G)
                    if km == 0: continue
                    est = sum(r['test']['comb'][(m, pstop)][wi].sum() for r in G) / km / ny
                    ns = [r['test']['n'] for r in G]
                    lo, hi = boot(ns, lambda I: sum(r['test']['comb'][(m, pstop)][wi][i].sum() for r, i in zip(G, I)) / km / ny)
                    tr = sum(r['train']['comb'][(m, pstop)][wi].sum() for r in G) / max(sum(r['train']['comb'][(m, pstop)][2] for r in G), 1e-9) / nyt
                    rows.append(dict(grp=grp, p=pstop, method=m, what=w, km=round(km, 1), test=round(est, 2), lo=round(lo, 2), hi=round(hi, 2), train=round(tr, 2),
                                     n_div=len(G)))
            # paired difference entry - rand_edge (all ha)
            for w, wi in (('all', 0), ('patch', 1)):
                ke = sum(r['test']['comb'][('entry', pstop)][2] for r in G); kr = sum(r['test']['comb'][('rand_edge', pstop)][2] for r in G)
                f = lambda I: sum(r['test']['comb'][('entry', pstop)][wi][i].sum() for r, i in zip(G, I)) / ke / ny - sum(r['test']['comb'][('rand_edge', pstop)][wi][i].sum() for r, i in zip(G, I)) / kr / ny
                ns = [r['test']['n'] for r in G]
                lo, hi = boot(ns, f); rows.append(dict(grp=grp, p=pstop, method='entry_minus_rand_edge', what=w, test=round(f([np.arange(n) for n in ns]), 2), lo=round(lo, 2), hi=round(hi, 2)))
    D = pd.DataFrame(rows); T['test'] = D.to_dict('records'); D.to_csv(C.OUT + 'test_summary.csv', index=False)
    # per division
    dr = []
    for k, r in R.items():
        t = r['test']; n = t['n']
        row = dict(key=k, division=r['div'], set=SETN(k), n_lines=sum(1 for l in r['lines'] if l[0] == 'entry'), km=round(t['comb'][('entry', 0.35)][2], 1),
                   test_fires=n, test_burnt_ha=round(t['fire_ha'].sum()))
        for m in ('entry', 'rand_edge', 'ring', 'road', 'r25_same_km', 'r25_20km'):
            v, vp, km = t['comb'][(m, 0.35)]; row[m] = round(v.sum() / max(km, 1e-9) / ny, 2)
        v, vp, km = t['comb'][('entry', 0.35)]; row['entry_patch'] = round(vp.sum() / km / ny, 2)
        row['entry_p1'] = round(t['comb'][('entry', 1.0)][0].sum() / km / ny, 2)
        lo, hi = boot([n], lambda I: v[I[0]].sum() / km / ny); row['entry_lo'], row['entry_hi'] = round(lo, 2), round(hi, 2)
        row['entry_train'] = round(r['train']['comb'][('entry', 0.35)][0].sum() / km / nyt, 2)
        row['pct_test_burnt'] = round(100 * v.sum() / t['fire_ha'].sum(), 3)
        dr.append(row)
    DD = pd.DataFrame(dr).sort_values('entry', ascending=False); DD.to_csv(C.OUT + 'division_table.csv', index=False)
    return R, D, DD


def per_line(R):
    """one row per proposed (tested) line: entries through it in 2022-25, ha saved."""
    E = pd.read_parquet(C.SC + 'entries_tr3.parquet'); S = pd.read_parquet(C.SC + 'patches_tr3.parquet')
    RG = pickle.load(open(C.SC + 'rings_tr3.pkl', 'rb'))
    rows = []
    for k, r in R.items():
        Ek = E[(E.key == k) & E.year.isin(C.TEST)]
        dom = Ek.sort_values('burn_ha', ascending=False).drop_duplicates(['patch', 'year'])
        L = pickle.load(open(C.SC + f'fires_{k}.pkl', 'rb'))
        for i, l in enumerate(r['lines']):
            if l[0] != 'entry': continue
            p = l[1]; s = S[(S.key == k) & (S.patch == p)].iloc[0]; m = RG['meta'][k][p]
            d = dom[dom.patch == p]
            x = L['x0'] + (m['cx'] + .5) * C.RES; y = L['y1'] - (m['cy'] + .5) * C.RES; lon, lat = C.C25.TB.transform(x, y)
            rows.append(dict(key=k, division=r['div'], patch=p, lon=round(lon, 4), lat=round(lat, 4), patch_forest_ha=round(m['forest_ha']), line_km=round(l[2], 2),
                             train_entries=int(s.n_entered), train_years=int(s.n_years), train_share=round(s.mode_share, 2), side_deg=round(s.mean_bear),
                             p_chance=s.get('p_chance', np.nan), test_years_burned=len(d), test_inside=int((d.status == 'inside').sum()),
                             test_entered=int((d.status == 'entered').sum()), test_through_line=int(((d.status == 'entered') & (d.seg == l[3]['seg'])).sum()),
                             test_patch_ha=round(d.burn_ha.sum(), 1),
                             test_saved_all_ha_yr=round(r['test']['allv'][i].sum() * 0.35 / len(C.TEST), 2), test_saved_patch_ha_yr=round(r['test']['patv'][i].sum() * 0.35 / len(C.TEST), 2),
                             test_saved_patch_ha_yr_p1=round(r['test']['patv'][i].sum() / len(C.TEST), 2), train_saved_all_ha_yr=round(r['train']['allv'][i].sum() * 0.35 / len(C.TRAIN), 2)))
    PL = pd.DataFrame(rows); PL.to_csv(C.OUT + 'test_lines.csv', index=False)
    # held-out: did 2022-25 entries come through the proposed segment more often than chance (segment length / ring length)?
    obs_rows = []
    for k, r in R.items():
        Ek = E[(E.key == k) & E.year.isin(C.TEST)]
        for i, l in enumerate(r['lines']):
            if l[0] != 'entry': continue
            p = l[1]; m = RG['meta'][k][p]
            d = Ek[Ek.patch == p].sort_values('burn_ha', ascending=False).drop_duplicates('year'); d = d[d.status == 'entered']
            for fo in (False, True):
                dd = d[d.from_out.astype(bool)] if fo else d
                obs_rows.append(dict(grp=SETN(k), from_out=fo, n=len(dd), hit=int((dd.seg == l[3]['seg']).sum()), exp=len(dd) * m['seg_km'][l[3]['seg']] / m['seg_km'].sum()))
    O = pd.DataFrame(obs_rows); res = {}
    for grp in ('core', 'rest', 'all MP'):
        for fo in (False, True):
            o = O[(O.from_out == fo) & ((O.grp == grp) if grp != 'all MP' else True)]
            if not len(o) or o.n.sum() == 0: continue
            bs = []
            for _ in range(NB):
                q = o.iloc[RNG.integers(0, len(o), len(o))]; bs.append(q.hit.sum() / max(q.n.sum(), 1) - q.exp.sum() / max(q.n.sum(), 1))
            res[f'{grp}|{"from_out" if fo else "all_entries"}'] = dict(lines=len(o), entries=int(o.n.sum()), through_line=int(o.hit.sum()), share=round(o.hit.sum() / o.n.sum(), 3),
                                                                     chance=round(o.exp.sum() / o.n.sum(), 3), diff_lo=round(np.percentile(bs, 2.5), 3), diff_hi=round(np.percentile(bs, 97.5), 3))
    T['through_line_test'] = res
    return PL


def entry_stats():
    out = {}
    for pset, yrs in (('tr3', C.TRAIN), ('all5', C.ALL)):
        E = pd.read_parquet(C.SC + f'entries_{pset}.parquet'); S = pd.read_parquet(C.SC + f'patches_{pset}.parquet')
        E['grp'] = E.key.map(SETN); S['grp'] = S.key.map(SETN)
        for grp in ('core', 'rest', 'all MP'):
            e = E if grp == 'all MP' else E[E.grp == grp]; s = S if grp == 'all MP' else S[S.grp == grp]
            for per, ys in (('def', yrs), ('test', C.TEST)) if pset == 'tr3' else (('def', yrs),):
                ee = e[e.year.isin(ys)]
                dom = ee.sort_values('burn_ha', ascending=False).drop_duplicates(['key', 'patch', 'year'])
                st = dom.status.value_counts(); n = len(dom)
                if n == 0: continue
                ent = dom[dom.status == 'entered']
                r = dict(patch_years=n, inside=round(100 * st.get('inside', 0) / n, 1), entered=round(100 * st.get('entered', 0) / n, 1),
                         entered_from_out=round(100 * ent.from_out.astype(bool).sum() / n, 1), unreached=round(100 * st.get('unreached', 0) / n, 1),
                         near=round(100 * dom.near.mean(), 1), fires_per_patch_year=round(len(ee) / max(n, 1), 2),
                         ha_inside=round(100 * dom[dom.status == 'inside'].burn_ha.sum() / dom.burn_ha.sum(), 1),
                         agree_day=round(100 * (ent.seg_day == ent.seg).mean(), 1),
                         agree_day_multiday=round(100 * (ent.seg_day == ent.seg)[ent.patch_days > 0].mean(), 1), n_multiday=int((ent.patch_days > 0).sum()),
                         agree_dot=round(100 * (ent.seg_dot[ent.seg_dot.fillna(-1) >= 0] == ent.seg[ent.seg_dot.fillna(-1) >= 0]).mean(), 1), n_dot=int((ent.seg_dot.fillna(-1) >= 0).sum()))
                if per == 'def':
                    s3 = s[s.n_entered >= 3]
                    r.update(n_patches_burned=len(s), patches_ge3_entries=len(s3), consistent=int(s.consistent.sum()), consistent_out=int(s.consistent_out.sum()),
                             mode_share_med=round(s3.mode_share.median(), 2), chance_share_med=round(s3.chance_share.median(), 2),
                             beats_chance_p05=int((s3.p_chance <= 0.05).sum()), R_med=round(s3.R_bear.median(), 2),
                             consistent_beats_chance=int((s.consistent & (s.p_chance <= 0.05)).sum()),
                             mean_years=round(s.n_years.mean(), 2), median_nseg=float(s3.nseg.median()) if len(s3) else np.nan)
                out[f'{pset}|{grp}|{per}'] = r
    T['entries'] = out
    return out


def chain_geom(cells, W, x0, y1):
    """order unordered ring cells into a line (greedy nearest neighbour from the end cell); return LineString in lon/lat."""
    from scipy.spatial import cKDTree
    pts = np.c_[(cells % W + .5) * C.RES + x0, y1 - (cells // W + .5) * C.RES]
    if len(pts) < 2: return None
    c = pts.mean(0); i = int(np.argmax(((pts - c) ** 2).sum(1)))
    left = np.ones(len(pts), bool); order = []; tr = cKDTree(pts)
    for _ in range(len(pts)):
        order.append(i); left[i] = False
        if not left.any(): break
        d, j = tr.query(pts[i], k=min(len(pts), 12))
        j = [jj for jj in np.atleast_1d(j) if left[jj]]
        if j: i = j[0]
        else:
            rem = np.nonzero(left)[0]; i = int(rem[np.argmin(((pts[rem] - pts[i]) ** 2).sum(1))])
    q = pts[order]
    # split at jumps > 200 m
    parts, cur = [], [q[0]]
    for a, b in zip(q[:-1], q[1:]):
        if np.hypot(*(b - a)) > 200:
            if len(cur) > 1: parts.append(cur)
            cur = [b]
        else: cur.append(b)
    if len(cur) > 1: parts.append(cur)
    if not parts: return None
    lon = lambda a: np.c_[C.C25.TB.transform(np.array(a)[:, 0], np.array(a)[:, 1])]
    return shapely.set_precision(shapely.simplify(shapely.MultiLineString([lon(p) for p in parts]), 0.00015), 1e-5)


def geojson_and_final(R):
    feats = []
    S3 = pd.read_parquet(C.SC + 'patches_tr3.parquet').set_index(['key', 'patch'])
    S5 = pd.read_parquet(C.SC + 'patches_all5.parquet').set_index(['key', 'patch'])
    RG5 = pickle.load(open(C.SC + 'rings_all5.pkl', 'rb')); RG3 = pickle.load(open(C.SC + 'rings_tr3.pkl', 'rb'))
    F5 = {}
    for p in glob.glob(C.SC + 'test_all5_*.pkl'):
        r = pickle.load(open(p, 'rb')); F5[r['key']] = r
    PL = pd.read_csv(C.OUT + 'test_lines.csv').set_index(['key', 'patch'])
    top = []
    for p in sorted(glob.glob(C.SC + 'patches_*.npz')):
        k = p.split('patches_')[1][:-4]
        L = pickle.load(open(C.SC + f'fires_{k}.pkl', 'rb')); Z = np.load(p)
        T2 = Affine(C.RES * C.AGG, 0, L['x0'], 0, -C.RES * C.AGG, L['y1'])
        for pset, SS in (('all5', S5), ('tr3', S3)):
            lab = Z['lab_' + pset]
            for geom, v in features.shapes(lab, mask=lab > 0, transform=T2):
                v = int(v); g = shapely.geometry.shape(geom)
                s = SS.loc[(k, v)] if (k, v) in SS.index else None
                if pset == 'tr3' and (s is None or not bool(s.consistent)): continue   # 2017-21 patches: only those that got a tested line
                gg = shapely.set_precision(gpd.GeoSeries([g], crs=32643).to_crs(4326).iloc[0].simplify(0.0004), 1e-5)
                feats.append(dict(layer=f'patch_{pset}', division=L['div'], patch=v, seasons=('2017-21, burnt in >=3 of 5' if pset == 'tr3' else '2017-25, burnt in >=5 of 9'),
                                  forest_ha=round(float(RG5['meta' if pset == 'all5' else 'meta'][k][v]['forest_ha']) if pset == 'all5' and k in RG5['meta'] and v in RG5['meta'][k] else (RG3['meta'][k][v]['forest_ha'] if k in RG3['meta'] and v in RG3['meta'][k] else np.nan), 1),
                                  years_burned=None if s is None else int(s.n_years), started_inside=None if s is None else int(s.n_inside), entered=None if s is None else int(s.n_entered),
                                  top_side_share=None if s is None or pd.isna(s.get('mode_share')) else round(float(s.mode_share), 2),
                                  consistent=None if s is None else bool(s.consistent), geometry=gg))
        for pset, RG, SS, LT in (('tr3', RG3, S3, R.get(k)), ('all5', RG5, S5, F5.get(k))):
            if LT is None: continue
            for i, l in enumerate(LT['lines']):
                if l[0] not in ('entry',): continue
                pp = l[1]; ring, seg = RG['rings'][k][pp]; cells = ring[seg == l[3]['seg']]
                g = chain_geom(cells, L['W'], L['x0'], L['y1'])
                if g is None: continue
                s = SS.loc[(k, pp)]
                d = dict(layer='line_tested_2017_21' if pset == 'tr3' else 'line_proposed_2017_25', division=L['div'], patch=pp, km=round(l[2], 2),
                         entries=int(s.n_entered), seasons_burned=int(s.n_years), share_through_segment=round(float(s.mode_share), 2),
                         side_deg_from_patch_centre=round(float(s.mean_bear)), p_chance=None if pd.isna(s.get('p_chance', np.nan)) else round(float(s.p_chance), 3), geometry=g)
                if pset == 'tr3' and (k, pp) in PL.index:
                    q = PL.loc[(k, pp)]; d.update(test_entries_through_line=int(q.test_through_line), test_seasons_burned=int(q.test_years_burned),
                                                  test_saved_patch_ha_yr=float(q.test_saved_patch_ha_yr), test_saved_all_ha_yr=float(q.test_saved_all_ha_yr))
                if pset == 'all5':
                    a = LT['all']; d['insample_saved_all_ha_yr'] = round(a['allv'][i].sum() * 0.35 / len(C.ALL), 2); d['insample_saved_patch_ha_yr'] = round(a['patv'][i].sum() * 0.35 / len(C.ALL), 2)
                    m = RG['meta'][k][pp]; x = L['x0'] + (m['cx'] + .5) * C.RES; y = L['y1'] - (m['cy'] + .5) * C.RES; lon, lat = C.C25.TB.transform(x, y)
                    top.append(dict(division=L['div'], set=SETN(k), patch=pp, lon=round(lon, 4), lat=round(lat, 4), patch_forest_ha=round(m['forest_ha']), line_km=round(l[2], 2),
                                    seasons_burned=int(s.n_years), entered=int(s.n_entered), inside=int(s.n_inside), share=round(float(s.mode_share), 2), side_deg=round(float(s.mean_bear)),
                                    p_chance=s.get('p_chance', np.nan), insample_patch_ha_yr=d['insample_saved_patch_ha_yr'], insample_all_ha_yr=d['insample_saved_all_ha_yr']))
                feats.append(d)
    G = gpd.GeoDataFrame(feats, geometry='geometry', crs=4326)
    G.to_file(C.OUT + 'repeat_patches_lines.geojson', driver='GeoJSON')
    TP = pd.DataFrame(top).sort_values('insample_all_ha_yr', ascending=False); TP.to_csv(C.OUT + 'top_patches.csv', index=False)
    return G, TP


if __name__ == '__main__':
    rates_by_year()
    entry_stats()
    R, D, DD = test_tables()
    PL = per_line(R)
    G, TP = geojson_and_final(R)
    json.dump(T, open(C.OUT + 'tables.json', 'w'), indent=1, default=float)
    print(pd.DataFrame(T['step1']).to_string()); print(pd.DataFrame(T['entries']).T.to_string()); print(D.to_string()); print(DD.to_string()); print(PL.to_string()); print(TP.head(30).to_string())
