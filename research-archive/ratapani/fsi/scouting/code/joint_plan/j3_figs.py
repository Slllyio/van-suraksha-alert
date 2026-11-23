"""Round r30, step 3. Figures for the combined plan (figs_r30/)."""
import os, json
import numpy as np, pandas as pd, geopandas as gpd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
FIG = '/mnt/project-files/ratapani/fsi/scouting/figs_r30/'; os.makedirs(FIG, exist_ok=True)
SC = '/mnt/project-files/ratapani/fsi/scouting/code/'
P = gpd.read_file(OUT + 'j1_patches.geojson').to_crs(32643)
Ln = gpd.read_file(OUT + 'j1_lines.geojson').to_crs(32643)
DIV = gpd.read_file('/mnt/project-files/fire-alert-scars/mp/out/mp_divisions.geojson').to_crs(32643)
PR = pd.read_csv(OUT + 'j1_programmes.csv'); DV = pd.read_csv(OUT + 'j1_by_division.csv')
TCOL = {'first 25k ha': '#7f0000', '25-50k ha': '#d7301f', '50-100k ha': '#fc8d59', '100-200k ha': '#fdd49e', 'rest': '#d9d9d9'}
P['col'] = P.tier.map(TCOL)
P.loc[(P.cum_ha > 100000) & (P.lines > 0), 'col'] = '#6baed6'      # lined, not burnt (S3)
LCOL = {'burn-block boundary': '#2b0000', 'cut': '#08306b'}

def km_bar(ax, km, x=0.04, y=0.05):
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim(); xs = x0 + x * (x1 - x0); ys = y0 + y * (y1 - y0)
    ax.plot([xs, xs + km * 1000], [ys, ys], color='k', lw=3); ax.text(xs + km * 500, ys + 0.012 * (y1 - y0), f'{km} km', ha='center', fontsize=8)

# fig 1: all MP
fig, ax = plt.subplots(figsize=(13, 11))
DIV.boundary.plot(ax=ax, color='#999999', lw=0.4)
P.plot(ax=ax, color=P.col, lw=0)
for role, c in LCOL.items():
    g = Ln[Ln.role_S3 == role]
    if len(g): g.plot(ax=ax, color=c, lw=0.5)
for _, d in DIV.iterrows():
    c = d.geometry.representative_point(); ax.text(c.x, c.y, d.Division.replace('_', ' '), fontsize=5, ha='center', color='#555555')
ax.set_axis_off()
leg = [Patch(color=TCOL['first 25k ha'], label='burn every year: first 25k ha (160 patches)'), Patch(color=TCOL['25-50k ha'], label='burn: 25-50k ha'),
       Patch(color=TCOL['50-100k ha'], label='burn: 50-100k ha'), Patch(color='#6baed6', label='not burnt, fire lines through it (477 patches)'),
       Patch(color='#d9d9d9', label='other repeat patches (later years)'), Line2D([0], [0], color=LCOL['burn-block boundary'], lw=1.5, label='practical line as burn-block boundary'),
       Line2D([0], [0], color=LCOL['cut'], lw=1.5, label='practical line as fire break')]
ax.legend(handles=leg, loc='lower left', fontsize=8, frameon=True)
ax.set_title('Combined plan, first programme (100k ha burnt + lines elsewhere): repeat patches and practical lines, all MP', fontsize=12)
km_bar(ax, 100, 0.75, 0.04); plt.tight_layout(); plt.savefig(FIG + 'r30_fig1_map_mp.png', dpi=170); plt.close()

# fig 2: twelve divisions with the largest benefit under S3
d3 = DV[DV.programme == 'S3'].sort_values('benefit_total', ascending=False)
top = d3.division.head(12).tolist()
fig, axs = plt.subplots(3, 4, figsize=(18, 14))
for ax, dn in zip(axs.ravel(), top):
    g = DIV[DIV.Division == dn]; pp = P[P.division == dn]; ll = Ln[Ln.division == dn]
    g.boundary.plot(ax=ax, color='#777777', lw=0.6)
    if len(pp): pp.plot(ax=ax, color=pp.col, lw=0)
    for role, c in LCOL.items():
        q = ll[ll.role_S3 == role]
        if len(q): q.plot(ax=ax, color=c, lw=0.8)
    r = d3[d3.division == dn].iloc[0]
    ax.set_title(f"{dn.replace('_', ' ')}\nburn {r.ha_burnt:,.0f} ha in {r.patches_burnt:.0f} patches, boundary {r.boundary_km + r.block_lines_km:,.0f} km, breaks {r.cut_km:,.0f} km\n"
                 f"saved {r.saved_total:,.0f} ha/yr + {r.converted:,.0f} ha/yr cool-burnt", fontsize=8)
    ax.set_axis_off(); km_bar(ax, 10)
fig.legend(handles=leg, loc='lower center', ncol=4, fontsize=8); plt.tight_layout(rect=(0, 0.04, 1, 1)); plt.savefig(FIG + 'r30_fig2_divisions.png', dpi=150); plt.close()

# fig 3: close-up of the largest first-tier patch in Ratapani, lines coloured by ground
pp = P[(P.division == 'Obedullahganj (Ratapani)') & (P.cum_ha <= 100000)].sort_values('line_km', ascending=False)
pt = pp.iloc[0]; ll = Ln[Ln.pid == pt.pid]
fig, ax = plt.subplots(figsize=(10, 9))
bx = pt.geometry.bounds; ax.set_xlim(bx[0] - 1500, bx[2] + 1500); ax.set_ylim(bx[1] - 1500, bx[3] + 1500)
gpd.GeoSeries([pt.geometry]).plot(ax=ax, color='#fdd49e', edgecolor='#7f0000', lw=1.2)
near = P[P.geometry.intersects(pt.geometry.buffer(3000)) & (P.pid != pt.pid)]
if len(near): near.plot(ax=ax, color='#eeeeee', edgecolor='#aaaaaa', lw=0.5)
GC = {'nala': '#1f78b4', 'ridge': '#6a3d9a', 'road': '#000000', 'edge': '#33a02c', 'forest': '#e31a1c'}
for _, l in ll.iterrows():
    kinds = {'nala': l.km_on_nala, 'ridge': l.km_on_ridge, 'road': l.km_on_road, 'edge': l.km_on_forest_edge}
    k = max(kinds, key=kinds.get) if max(kinds.values()) > 0.5 * l.km else 'forest'
    gpd.GeoSeries([l.geometry]).plot(ax=ax, color=GC[k], lw=2)
ax.set_axis_off(); km_bar(ax, 2)
ax.legend(handles=[Patch(facecolor='#fdd49e', edgecolor='#7f0000', label=f'patch to burn 15-28 Feb ({pt.forest_ha:,.0f} forest ha, burns {100 * pt.burnt_share_per_season_2022_25:.0f}% a season)'),
                   Patch(color='#eeeeee', label='other repeat patches'),
                   Line2D([0], [0], color=GC['nala'], lw=2, label='block boundary mostly on a nala'), Line2D([0], [0], color=GC['ridge'], lw=2, label='mostly on a ridge crest'),
                   Line2D([0], [0], color=GC['road'], lw=2, label='mostly on a road or track'), Line2D([0], [0], color=GC['edge'], lw=2, label='mostly on the forest edge'),
                   Line2D([0], [0], color=GC['forest'], lw=2, label='through forest, along contour')], loc='lower right', fontsize=8)
ax.set_title(f"Worked example: Ratapani patch {pt.patch} ({pt.forest_ha:,.0f} forest ha): {len(ll)} practical lines ({ll.km.sum():.1f} km) split it into burn blocks;"
             f"\nburn one block a day from the downwind side, each block's line cleared beforehand; patch edge needs ~{pt.boundary_km:.0f} km of boundary", fontsize=10)
plt.tight_layout(); plt.savefig(FIG + 'r30_fig3_example.png', dpi=160); plt.close()

# fig 4: programme frontier
fig, ax = plt.subplots(figsize=(9, 6))
S = PR[PR.programme.str.startswith('S')]
ax.plot(S.cost_crore, S.saved_total / 1000, '-o', color='#08306b', label='forest ha not burnt at all (outside stopped + line breaks)')
ax.plot(S.cost_crore, S.benefit_total / 1000, '-s', color='#d7301f', label='plus patch hectares turned into cool February burns')
for _, r in S.iterrows():
    ax.annotate(r.burn_set.replace('first ', '').replace('all 419k ha', 'all patches'), (r.cost_crore, r.benefit_total / 1000), textcoords='offset points', xytext=(6, -2), fontsize=8)
L = PR[PR.programme == 'L'].iloc[0]; ax.plot(L.cost_crore, L.saved_total / 1000, '^', color='#6baed6', ms=10, label='fire lines only, all 4,986 km (held out)')
ax.set_xlabel('cost per year, Rs crore (line Rs 1,356/km; burning Rs 120/ha, inferred)'); ax.set_ylabel('thousand forest ha per year')
ax.set_title('What each programme size buys (held-out seasons 2022-25)'); ax.grid(alpha=0.3); ax.legend(fontsize=8, loc='upper left')
plt.tight_layout(); plt.savefig(FIG + 'r30_fig4_frontier.png', dpi=160); plt.close()

# fig 5: divisions under S3
d = d3.head(25).iloc[::-1]
fig, ax = plt.subplots(figsize=(10, 9))
y = np.arange(len(d)); ax.barh(y, d.saved_outside, color='#d7301f', label='stopped outside burnt patches')
ax.barh(y, d.saved_lines, left=d.saved_outside, color='#08306b', label='saved by fire breaks')
ax.barh(y, d.converted, left=d.saved_outside + d.saved_lines, color='#fdd49e', label='patch ha turned into February cool burns')
ax.set_yticks(y); ax.set_yticklabels([s.replace('_', ' ') for s in d.division], fontsize=8); ax.set_xlabel('forest ha per year, held out 2022-25')
ax.set_title('First programme (100k ha burnt + lines): the 25 divisions with the most to gain'); ax.legend(fontsize=8, loc='lower right'); ax.grid(axis='x', alpha=0.3)
plt.tight_layout(); plt.savefig(FIG + 'r30_fig5_divisions_bar.png', dpi=160); plt.close()

# fig 6: season calendar with the work plan
w = pd.read_csv(SC + 'control_burn/out/cb3_weekly.csv'); wk = w.groupby(['year', 'week']).ha_all.sum().groupby('week').mean()
fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw=dict(height_ratios=[2, 1.6]), sharex=True)
import datetime as dt
doy = [46 + 7 * k for k in wk.index]; a1.bar(doy, wk.values / 1000, width=6, color='#fc8d59')
a1.set_ylabel('burnt forest, thousand ha per week\n(mean 2017-25)'); a1.grid(axis='y', alpha=0.3)
a1.set_title('The season and the work plan: lines first, burns in the fortnight before the fires, watchers through the peak')
acts = [('clear and re-clear the practical lines (boundaries and breaks)', 1, 45, '#08306b'), ('burn the repeat patches, block by block, 15-28 Feb', 46, 59, '#7f0000'),
        ('patrol the burnt patches for escapes and re-lights', 60, 80, '#d7301f'), ('fire watchers on the ranked squares, 8 Mar-25 Apr (84% of burning)', 67, 115, '#fdd49e'),
        ('live alerts and 2-day watch list, whole season', 46, 166, '#999999')]
for i, (lab, s, e, c) in enumerate(acts):
    a2.barh(len(acts) - i, e - s, left=s, color=c, height=0.6)
    if e - s > 100: a2.text(s + 2, len(acts) - i, lab, va='center', fontsize=7.5, color='white')
    else: a2.text(e + 1.5, len(acts) - i, lab, va='center', fontsize=7.5, color='black')
a2.set_yticks([]); ticks = [1, 32, 46, 60, 74, 91, 105, 121, 135, 152, 166]
a2.set_xticks(ticks); a2.set_xticklabels(['1 Jan', '1 Feb', '15 Feb', '1 Mar', '15 Mar', '1 Apr', '15 Apr', '1 May', '15 May', '1 Jun', '15 Jun'], fontsize=8)
a2.set_xlim(1, 200); a2.grid(axis='x', alpha=0.3)
plt.tight_layout(); plt.savefig(FIG + 'r30_fig6_calendar.png', dpi=160); plt.close()

# fig 7: big fires by where they start
B = pd.read_csv(OUT + 'j2_bigfires.csv'); order = ['burn set 25k', '25-50k', '50-100k', '100-200k', 'rest of tr3', 'outside patches']
pv = B.pivot(index='size', columns='start', values='forest_ha_per_yr').reindex(['<10', '10-50', '50-200', '200-500', '500-1000', '1000+'])[order].fillna(0) / 1000
fig, ax = plt.subplots(figsize=(9, 5.5)); left = np.zeros(len(pv)); cols = ['#7f0000', '#d7301f', '#fc8d59', '#fdd49e', '#bdbdbd', '#eeeeee']
for c, col in zip(order, cols): ax.barh(np.arange(len(pv)), pv[c], left=left, color=col, edgecolor='#666666', lw=0.3, label=c); left += pv[c].values
ax.set_yticks(np.arange(len(pv))); ax.set_yticklabels([f'{s} ha' for s in pv.index]); ax.set_xlabel('burnt forest, thousand ha per year (2022-25)')
ax.set_title('Burnt forest by fire size and where the fire started (inside which burn tier, or outside the repeat patches)'); ax.legend(fontsize=8, title='fire started in', loc='lower right'); ax.grid(axis='x', alpha=0.3)
plt.tight_layout(); plt.savefig(FIG + 'r30_fig7_bigfires.png', dpi=160); plt.close()
print('figs done')
