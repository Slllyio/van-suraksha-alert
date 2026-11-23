"""Step 6. The proposed lines, all over MP: compartment cuts in the all-season repeat patches (all5 = burnt in >= 5 of 9 seasons
2017-25), chosen with the drop-best-year objective on all nine seasons (m2 'final'), ranked statewide by the greedy knapsack (one
lambda) up to 5,000 km. Each line carries its statewide rank, cumulative km and the budget tier it falls in.
Out: out/proposed_fire_lines_mp.geojson (WGS84 lines), out/proposed_fire_lines_mp.csv, out/proposed_lines_by_division.csv,
figs_r28/r28_fig2_map.png"""
import pickle, glob, os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0 as M
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/compartments/')
from k2_score import hull, take   # noqa: E402
from pyproj import Transformer
TB = Transformer.from_crs(32643, 4326, always_xy=True)
KMAX = 5000; TIERS = (500, 1000, 2000, 5000)


def main(obj='final', suffix=''):
    P = {}; items = []; meta = {}
    for fn in sorted(glob.glob(M.SC + f'cuts_all5_{obj}_*.pkl')):
        R = pickle.load(open(fn, 'rb')); key = R['key']
        if not R['patches']: continue
        meta[key] = dict(div=R['div'], W=R['W'], x0=R['x0'], y1=R['y1'])
        for r in R['patches']:
            if not r['seq']: continue
            km = np.array([s['km'] for s in r['seq']]); g = np.array([s['g'] for s in r['seq']])
            P[(key, r['patch'])] = dict(seq=r['seq'], km=km, g=g, ha=R['patch_ha'][r['patch']], box=r['box'])
            for o, (i, j, k_, v) in enumerate(hull(km, g)): items.append(((key, r['patch']), o, k_, v, j))
    segj = {(it[0], it[1]): it[4] for it in items}
    got, tot = take([it[:4] for it in items], KMAX)
    # order of hull segments taken = statewide rank order; expand each segment into its cuts (patch order)
    order = sorted(got, key=lambda t: -t[3] / max(t[2], 1e-9))
    rows = []; feats = []; rank = 0; cum = 0.0; done = {}
    for ow, od, k_, v in order:
        n0 = done.get(ow, 0); n1 = segj[(ow, od)]
        for i in range(n0, n1):
            s = P[ow]['seq'][i]; key, p = ow; m = meta[key]; W = m['W']
            cells = s['cells']; r = cells // W; c = cells % W
            x = m['x0'] + (c + 0.5) * M.RES; y = m['y1'] - (r + 0.5) * M.RES
            lon, lat = TB.transform(x, y)
            rank += 1; cum += s['km']
            tier = next((t for t in TIERS if cum <= t), None)
            fha = float(s['train_mean'][1]) if i == 0 else float(s['train_mean'][1] - P[ow]['seq'][i - 1]['train_mean'][1])
            feat = s.get('feat', {})
            row = dict(rank=rank, division=m['div'], patch=p, patch_forest_ha=round(P[ow]['ha'], 1), cut_no=i + 1, compartments_after=s['n_after'], km=round(s['km'], 2),
                       cum_km=round(cum, 1), budget_tier_km=tier, kind=s['kind'], forest_ha_per_yr_in_sample=round(fha, 1), objective_gain=round(float(s['g']), 2),
                       km_on_nala=round(feat.get('valley', 0), 2), km_on_ridge=round(feat.get('ridge', 0), 2), km_on_road=round(feat.get('road', 0), 2), km_on_forest_edge=round(feat.get('edge', 0), 2),
                       km_steep_over_15pct=round(feat.get('km_steep', 0), 2), mean_grade=round(feat.get('grade_mean', 0), 3),
                       lon_start=round(float(lon[0]), 5), lat_start=round(float(lat[0]), 5), lon_end=round(float(lon[-1]), 5), lat_end=round(float(lat[-1]), 5))
            rows.append(row)
            if len(lon) < 2: continue        # a one-cell cut (60 m) has no line geometry; it stays in the CSV
            feats.append(dict(type='Feature', properties=row, geometry=dict(type='LineString', coordinates=[[round(float(a), 5), round(float(b), 5)] for a, b in zip(lon, lat)])))
        done[ow] = n1
    T = pd.DataFrame(rows); T.to_csv(M.OUT + f'proposed_fire_lines_mp{suffix}.csv', index=False)
    json.dump(dict(type='FeatureCollection', features=feats), open(M.OUT + f'proposed_fire_lines_mp{suffix}.geojson', 'w'))
    D = []
    for t in TIERS:
        x = T[T.cum_km <= t]
        for dv, g in x.groupby('division'):
            D.append(dict(budget_km=t, division=dv, patches=g.patch.nunique(), lines=len(g), km=round(g.km.sum(), 1), forest_ha_per_yr_in_sample=round(g.forest_ha_per_yr_in_sample.sum())))
    D = pd.DataFrame(D); D.to_csv(M.OUT + f'proposed_lines_by_division{suffix}.csv', index=False)
    print('lines', len(T), 'km', round(T.km.sum()), 'patches', T.patch.nunique() if False else len(set(zip(T.division, T.patch))))
    for t in TIERS:
        x = T[T.cum_km <= t]; print(t, 'km:', len(x), 'lines in', len(set(zip(x.division, x.patch))), 'patches,', x.division.nunique(), 'divisions; in-sample forest ha/yr', round(x.forest_ha_per_yr_in_sample.sum()))
    print(D[D.budget_km == 2000].sort_values('km', ascending=False).head(20).to_string(index=False))
    # map
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    import geopandas as gpd
    DV = gpd.read_file('/mnt/project-files/fire-alert-scars/mp/out/mp_divisions.geojson').to_crs(4326)
    fig, ax = plt.subplots(figsize=(11, 9.5)); DV.boundary.plot(ax=ax, color='0.75', linewidth=0.4)
    G = gpd.GeoDataFrame.from_features(feats, crs=4326)
    cols = {500: ('red', 'first 500 km'), 1000: ('orange', '500-1,000 km'), 2000: ('blue', '1,000-2,000 km'), 5000: ('0.4', '2,000-5,000 km')}
    for t in TIERS[::-1]:
        g = G[G.budget_tier_km == t]
        if len(g): g.plot(ax=ax, color=cols[t][0], linewidth=1.6 if t <= 1000 else 1.0, label=cols[t][1])
    # draw as buffered points so short lines show at state scale
    for t in TIERS:
        g = G[G.budget_tier_km == t]
        if len(g): ax.scatter(g.lon_start, g.lat_start, s=6 if t <= 1000 else 3, color=cols[t][0], alpha=0.8)
    ax.legend(loc='lower left', title='proposed compartment lines, by statewide rank'); ax.set_title('Proposed fire lines, Madhya Pradesh: compartment cuts in repeat-burn patches (burnt 5+ of 9 seasons), ranked statewide', fontsize=10)
    ax.set_xlabel('lon'); ax.set_ylabel('lat'); ax.set_aspect('equal'); plt.tight_layout(); plt.savefig(M.FIG + f'r28_fig2_map{suffix}.png', dpi=150); plt.close()
    # per-division zoom sheets for the top 8 divisions
    top = D[D.budget_km == 2000].sort_values('km', ascending=False).division.head(8).tolist()
    fig, axs = plt.subplots(2, 4, figsize=(18, 9))
    for ax, dv in zip(axs.ravel(), top):
        d = DV[DV.Division.map(M.K.slug) == M.K.slug(dv)] if 'Division' in DV else DV.iloc[:0]
        if len(d): d.boundary.plot(ax=ax, color='0.6', linewidth=0.6)
        g = G[G.division == dv]
        for t in TIERS[::-1]:
            gg = g[g.budget_tier_km == t]
            if len(gg): gg.plot(ax=ax, color=cols[t][0], linewidth=1.4)
        ax.set_title(f'{dv}: {len(g)} lines, {g.km.sum():.0f} km (to 5,000 km tier)', fontsize=9); ax.set_aspect('equal'); ax.tick_params(labelsize=7)
    plt.tight_layout(); plt.savefig(M.FIG + f'r28_fig3_divisions{suffix}.png', dpi=130); plt.close()


if __name__ == '__main__':
    main(*sys.argv[1:]) if len(sys.argv) > 1 else main()
