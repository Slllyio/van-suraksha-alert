"""Per division and season tables and maps of January-February burning. Sources: out/viirs_clusters_jan_feb.csv (2014-26, every
division) and out/scar_fires_jan_feb.csv (scars 15-28 Feb 2017-25 statewide; Jan only in Ratapani, which ran the scar method
all season). Out: out/jan_feb_by_division_season.csv, out/jan_feb_statewide.csv, out/dept_burns_jan_feb.geojson,
figs/map_<season>.png (one map per season), figs/trend.png"""
import os, numpy as np, pandas as pd, geopandas as gpd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'; FIG = HERE + '/figs/'; os.makedirs(FIG, exist_ok=True)
C = pd.read_csv(OUT + 'viirs_clusters_jan_feb.csv'); F = pd.read_csv(OUT + 'scar_fires_jan_feb.csv')
C['dept_like'] = C.cls.str.contains('control-like') | C.pre15 & (C.d_edge <= 100)   # pre-15 Feb points on a beat boundary count too
C['on_line'] = (C.d_edge <= 100) | (C.d_road <= 100)
g = C.groupby(['Division', 'season']).agg(clusters=('cid', 'size'), points=('n', 'sum'), pre15_clusters=('pre15', 'sum'), control_like=('flag', 'sum'), dept_like=('dept_like', 'sum'), on_line=('on_line', 'sum'), day_only_share=('day_only', 'mean'), frp_med=('frp_max', 'median')).reset_index()
s = F.groupby(['key', 'season']).agg(scar_fires=('ha', 'size'), scar_ha=('ha', 'sum'), scar_forest_ha=('forest_ha', 'sum'), scar_dept_like=('dept_like', 'sum'), scar_dept_like_ha=('ha', lambda x: x[F.loc[x.index, 'dept_like']].sum()), strips=('strip', 'sum')).reset_index().rename(columns={'key': 'Division'})
s['Division'] = s.Division.replace({'Barghat_Project': 'Barghat Project', 'Kanha_Tiger_Reserve': 'Kanha Tiger Reserve', 'PTR_MP': 'PTR MP'})
T = g.merge(s, on=['Division', 'season'], how='outer').fillna(0).sort_values(['season', 'dept_like'], ascending=[True, False])
T.to_csv(OUT + 'jan_feb_by_division_season.csv', index=False)
S = T.groupby('season').agg(divisions_with_burning=('Division', 'size'), clusters=('clusters', 'sum'), points=('points', 'sum'), pre15_clusters=('pre15_clusters', 'sum'), control_like=('control_like', 'sum'), dept_like=('dept_like', 'sum'), on_line=('on_line', 'sum'), scar_fires=('scar_fires', 'sum'), scar_ha=('scar_ha', 'sum'), scar_dept_like=('scar_dept_like', 'sum'), scar_dept_like_ha=('scar_dept_like_ha', 'sum')).reset_index()
S.to_csv(OUT + 'jan_feb_statewide.csv', index=False); print(S.round(0).to_string(index=False))
print('top divisions, dept-like clusters per season (2017-26 mean):'); print(T[T.season >= 2017].groupby('Division').dept_like.mean().sort_values(ascending=False).head(15).round(1))
# geojson of every Jan-Feb event: VIIRS clusters (with class) and scar fires
G1 = gpd.GeoDataFrame(C[['cid', 'Division', 'beat', 'season', 'date', 'n', 'frp_max', 'day_only', 'short', 'elong', 'd_road', 'd_edge', 'flag', 'cls', 'dept_like', 'on_line']].assign(source='viirs_cluster'), geometry=gpd.points_from_xy(C.lon, C.lat), crs=4326)
G2 = gpd.GeoDataFrame(F[['key', 'division', 'fire', 'season', 'date', 'ha', 'forest_ha', 'length_m', 'width_m', 'edge_share', 'burn_days', 'viirs_pts', 'night_share', 'frp_max', 'strip', 'cls', 'dept_like']].assign(source='scar_fire'), geometry=gpd.points_from_xy(F.lon, F.lat), crs=4326)
G = pd.concat([G1, G2], ignore_index=True); G['date'] = G.date.astype(str); G.to_file(OUT + 'dept_burns_jan_feb.geojson', driver='GeoJSON')
# maps: one per season, clusters coloured by class
col = {'pre-15 Feb control-like': 'tab:blue', 'pre-15 Feb other': 'tab:cyan', '15-28 Feb control-like': 'tab:orange', '15-28 Feb other': 'tab:red'}
seasons = sorted(C.season.unique()); fig, axes = plt.subplots(4, 4, figsize=(20, 19)); axes = axes.ravel()
for ax, y in zip(axes, seasons):
    d = C[C.season == y]
    for k, c in col.items():
        e = d[d.cls == k]; ax.scatter(e.lon, e.lat, s=3, c=c, label=f'{k} ({len(e)})', alpha=0.7)
    ax.set_xlim(74, 82.8); ax.set_ylim(21, 26.8); ax.set_aspect(1 / np.cos(np.radians(23.5))); ax.set_title(f'{y}: {len(d)} Jan-Feb burn clusters'); ax.legend(fontsize=7, loc='lower left'); ax.tick_params(labelsize=7)
for ax in axes[len(seasons):]: ax.axis('off')
fig.suptitle('January-February VIIRS burn-day clusters in MP forest by season (blue = before 15 Feb, control-like = day-only single-day small cool burn)', fontsize=13); fig.tight_layout(); fig.savefig(FIG + 'maps_by_season.png', dpi=110)
fig, ax = plt.subplots(figsize=(9, 4.5)); ax.plot(S.season, S.pre15_clusters, 'o-', label='clusters before 15 Feb'); ax.plot(S.season, S.control_like, 's-', label='control-like clusters, Jan-Feb'); ax.plot(S.season, S.clusters, '^-', label='all Jan-Feb clusters')
ax.set_xlabel('season'); ax.set_ylabel('burn-day clusters (750 m, same day)'); ax.legend(); ax.grid(alpha=0.3); ax.set_title('January-February burning in MP forest, VIIRS 2014-26'); fig.tight_layout(); fig.savefig(FIG + 'trend.png', dpi=130); print('figs saved')
