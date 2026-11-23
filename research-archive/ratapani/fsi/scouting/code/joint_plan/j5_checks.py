"""Round r30, step 5. Fold the five checks (control_burning.md sections 10-14) into the plan files: escape flag per patch into
j1_patches.csv/.geojson, and a map of the first programme's patches by escape flag (figs_r30/r30_fig8_escape.png)."""
import os
import numpy as np, pandas as pd, geopandas as gpd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Patch
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'; FIG = '/mnt/project-files/ratapani/fsi/scouting/figs_r30/'
E = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/control_burn/out/cb14_escape_patches.csv')[['key', 'patch', 'feb_fires', 'feb_left_patch', 'feb_max_out_ha', 'mar_fires', 'mar_max_out_ha', 'all_fires', 'all_max_out_ha', 'escape_flag']]
P = pd.read_csv(OUT + 'j1_patches.csv'); P = P.drop(columns=[c for c in E.columns if c in P.columns and c not in ('key', 'patch')]).merge(E, on=['key', 'patch'], how='left')
P.to_csv(OUT + 'j1_patches.csv', index=False)
G = gpd.read_file(OUT + 'j1_patches.geojson'); G = G.drop(columns=[c for c in E.columns if c in G.columns and c not in ('key', 'patch')]).merge(E, on=['key', 'patch'], how='left')
G.to_file(OUT + 'j1_patches.geojson', driver='GeoJSON')
DIV = gpd.read_file('/mnt/project-files/fire-alert-scars/mp/out/mp_divisions.geojson')
B = G[G.cum_ha <= 100000].copy(); col = {'low': '#fdd49e', 'medium: 50-200 ha outside': '#fc8d59', 'high: a fire from here ran 200+ ha outside': '#7f0000'}
fig, ax = plt.subplots(figsize=(13, 11)); DIV.boundary.plot(ax=ax, color='#999999', lw=0.4)
for k, c in col.items():
    g = B[B.escape_flag == k]
    if len(g): g.plot(ax=ax, color=c, lw=0)
for _, d in DIV.iterrows():
    c = d.geometry.representative_point(); ax.text(c.x, c.y, d.Division.replace('_', ' '), fontsize=5, ha='center', color='#555555')
ax.set_axis_off(); ax.legend(handles=[Patch(color=col['high: a fire from here ran 200+ ha outside'], label=f"high: a fire from the patch ran 200+ ha outside it ({(B.escape_flag.str.startswith('high')).sum()} patches)"),
                              Patch(color=col['medium: 50-200 ha outside'], label=f"medium: 50-200 ha outside ({(B.escape_flag.str.startswith('medium')).sum()})"), Patch(color=col['low'], label=f"low: never over 50 ha outside ({(B.escape_flag == 'low').sum()})")], loc='lower left', fontsize=9)
ax.set_title('First programme patches (first 100k ha) by escape record 2017-25: where the edge boundary must be real', fontsize=12)
plt.tight_layout(); plt.savefig(FIG + 'r30_fig8_escape.png', dpi=170); plt.close(); print('ok', len(B), B.escape_flag.value_counts().to_dict())
