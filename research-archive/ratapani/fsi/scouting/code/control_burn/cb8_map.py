"""Step 8. Where to control burn: the repeat patches (tr3: burnt 3+ of the 5 seasons 2017-21, >= 10 forest ha), ranked by what a
late-February burn would do per hectare treated, scored on the held-out seasons 2022-25:
  converted ha/yr = forest ha x share of the patch burnt per season 2022-25 x 0.70 (hot-season fire turned into a cool burn)
  outside ha/yr   = forest ha outside the patch burnt by fires that started inside it, 2022-25 mean (m5) x 0.70 (stopped)
  benefit per 100 ha treated = 100 x (converted + outside) / forest ha
Tiers by cumulative forest ha: 25k, 50k, 100k, 200k, all. 'core' = at least half the patch is an all5 patch (burnt 5+ of 9).
Out: out/control_burn_patches_mp.geojson, .csv, out/control_burn_by_division.csv, figs_r29/r29_fig3_map.png, r29_fig4_divisions.png"""
import sys, os, json
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import shape
from rasterio import features
from rasterio.transform import from_origin
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
FIG = '/mnt/project-files/ratapani/fsi/scouting/figs_r29/'
M5 = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2/out/m5_patches.csv')
TIERS = [25000, 50000, 100000, 200000, 10**9]; TLAB = ['first 25k ha', '25-50k ha', '50-100k ha', '100-200k ha', 'rest']
PROT = 0.70


def main():
    feats = []; rows = []
    for key in B.KEYS:
        L, FOR = B.load_div(key); H, W = L['H'], L['W']
        Z = np.load(B.SC26 + f'patches_{key}.npz'); lab = Z['lab_tr3']; a5 = Z['lab_all5'] > 0
        if lab.max() == 0: continue
        cte = (Z['cnt_all'] - Z['cnt_tr']).astype(float)
        fb = Z['fb'] > 0                                   # forest at 120 m
        h2, w2 = lab.shape
        tr = from_origin(L['x0'], L['y1'], 120.0, 120.0)
        n = lab.max(); ids = np.arange(1, n + 1)
        from scipy import ndimage as ndi
        fcells = ndi.sum(fb, lab, ids); freq_te = ndi.mean(np.where(fb, cte / 4.0, np.nan), lab, ids) if False else None
        # mean held-out burn share over forest cells of the patch
        s = ndi.sum(np.where(fb, cte, 0), lab, ids); freq_te = s / np.maximum(fcells, 1) / 4.0
        s9 = ndi.sum(np.where(fb, Z['cnt_all'].astype(float), 0), lab, ids); freq9 = s9 / np.maximum(fcells, 1) / 9.0
        core = ndi.mean(a5.astype(float), lab, ids)
        m5 = M5[M5.key == key].set_index('patch')
        geoms = {}
        for geom, v in features.shapes(lab.astype(np.int32), mask=lab > 0, transform=tr):
            geoms.setdefault(int(v), []).append(shape(geom))
        from shapely.ops import unary_union
        for i, p in enumerate(ids):
            if p not in geoms: continue
            g = unary_union(geoms[p]); fha = fcells[i] * 1.44
            te_out = float(m5.te_out.get(p, 0.0)); te_in = float(m5.te_in.get(p, 0.0))
            conv = fha * freq_te[i] * PROT; out = te_out * PROT
            c = g.centroid; lon, lat = B.C25.TB.transform(c.x, c.y)
            rows.append(dict(key=key, division=L['div'], patch=int(p), forest_ha=round(fha, 1), burnt_share_per_season_2022_25=round(freq_te[i], 3),
                             burnt_share_per_season_2017_25=round(freq9[i], 3), core_all5=bool(core[i] >= 0.5),
                             converted_ha_yr=round(conv, 1), outside_ha_yr=round(out, 1), inside_start_fires_ha_yr=round(te_in, 1),
                             benefit_per_100ha=round(100 * (conv + out) / fha, 1), lat=round(lat, 5), lon=round(lon, 5)))
            feats.append((len(rows) - 1, g))
        print(key, n, flush=True)
    D = pd.DataFrame(rows)
    D = D.sort_values('benefit_per_100ha', ascending=False).reset_index(drop=True)
    D['rank'] = np.arange(1, len(D) + 1); D['cum_ha'] = D.forest_ha.cumsum()
    D['tier'] = pd.cut(D.cum_ha, [0] + TIERS, labels=TLAB).astype(str)
    order = {i: r for r, i in enumerate(D.index)}  # not needed; keep simple
    G = gpd.GeoDataFrame(D.drop(columns=[]), geometry=[None] * len(D), crs='EPSG:32643')
    gm = {i: g for i, g in feats}
    # rows were reordered: map by (key, patch)
    key2geom = {}
    for i, g in feats: key2geom[(rows[i]['key'], rows[i]['patch'])] = g
    G['geometry'] = [key2geom[(k, p)] for k, p in zip(D.key, D.patch)]
    G = G.to_crs(4326)
    G.to_file(B.OUT + 'control_burn_patches_mp.geojson', driver='GeoJSON')
    D.to_csv(B.OUT + 'control_burn_patches_mp.csv', index=False)
    T = D.groupby(['division', 'tier']).agg(patches=('patch', 'size'), forest_ha=('forest_ha', 'sum'), converted_ha_yr=('converted_ha_yr', 'sum'), outside_ha_yr=('outside_ha_yr', 'sum')).reset_index()
    T.to_csv(B.OUT + 'control_burn_by_division.csv', index=False)
    S = D.groupby('tier').agg(patches=('patch', 'size'), forest_ha=('forest_ha', 'sum'), converted=('converted_ha_yr', 'sum'), outside=('outside_ha_yr', 'sum'), divisions=('division', 'nunique'))
    S = S.loc[[t for t in TLAB if t in S.index]]; S['benefit_per_100ha'] = 100 * (S.converted + S.outside) / S.forest_ha; print(S.round(0))
    top = D.groupby('division').agg(patches=('patch', 'size'), forest_ha=('forest_ha', 'sum'), converted=('converted_ha_yr', 'sum'), outside=('outside_ha_yr', 'sum')).sort_values('forest_ha', ascending=False)
    print(top.head(20).round(0))
    # maps
    DV = gpd.read_file('/mnt/project-files/fire-alert-scars/mp/out/mp_divisions.geojson').to_crs(4326)
    cols = {'first 25k ha': '#b2182b', '25-50k ha': '#ef8a62', '50-100k ha': '#fdb863', '100-200k ha': '#92c5de', 'rest': '#bbbbbb'}
    fig, ax = plt.subplots(figsize=(14, 12))
    DV.boundary.plot(ax=ax, color='grey', lw=.4)
    for t in reversed(TLAB):
        g = G[G.tier == t]
        if len(g): g.plot(ax=ax, color=cols[t], lw=0, label=f'{t}: {len(g)} patches, {g.forest_ha.sum()/1000:.0f}k ha')
    ax.legend(loc='lower left', title='rank by benefit per ha treated (held out 2022-25)'); ax.set_title('Where to control burn in MP: repeat-burn patches (burnt 3+ of 5 seasons 2017-21), ranked')
    ax.set_xlabel('longitude'); ax.set_ylabel('latitude'); plt.tight_layout(); plt.savefig(FIG + 'r29_fig3_map.png', dpi=130); plt.close()
    tops = top.head(8).index.tolist()
    fig, axs = plt.subplots(2, 4, figsize=(22, 11))
    for ax, dv in zip(axs.ravel(), tops):
        dvp = DV[DV.Division == dv]
        if len(dvp) == 0: dvp = DV[DV.Division.str.startswith(dv.split(' (')[0])]
        dvp.boundary.plot(ax=ax, color='grey', lw=.6)
        g = G[G.division == dv]
        for t in reversed(TLAB):
            gg = g[g.tier == t]
            if len(gg): gg.plot(ax=ax, color=cols[t], lw=0)
        ax.set_title(f'{dv}: {len(g)} patches, {g.forest_ha.sum()/1000:.1f}k ha, {g.converted_ha_yr.sum()+g.outside_ha_yr.sum():,.0f} ha/yr', fontsize=10)
        if len(dvp): b = dvp.total_bounds; ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3])
    plt.tight_layout(); plt.savefig(FIG + 'r29_fig4_divisions.png', dpi=110); plt.close(); print('maps ok')


if __name__ == '__main__':
    main()
