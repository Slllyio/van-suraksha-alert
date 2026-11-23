"""New question 2. Who is getting better or worse? Per division, burnt forest share per season 2017-25 (scars) and VIIRS points
per 100 km2 (S-NPP 2014-26), each relative to the state that season (log ratio to the all-MP value, which removes the weather year),
then the trend over the seasons. Significance by permutation of the season labels within the division (999 draws); a division
counts as moving only if both measures agree in sign and the scar trend has p < 0.05. Out: out/n2_trend.csv, figs_r30/r30_fig9_trend.png"""
import os, sys
import numpy as np, pandas as pd, geopandas as gpd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Patch
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'; FIG = '/mnt/project-files/ratapani/fsi/scouting/figs_r30/'
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn'); import cb0 as B
rng = np.random.default_rng(5)
Q = pd.read_parquet(B.OUT + 'cb3_squares.parquet'); Q['burnt'] = Q.ha_p1 + Q.ha_p2 + Q.ha_late
S = Q.groupby(['key', 'year']).agg(burnt=('burnt', 'sum'), forest=('forest_ha', 'sum')).reset_index(); S['share'] = S.burnt / S.forest
st = S.groupby('year').apply(lambda d: d.burnt.sum() / d.forest.sum()).rename('state'); S = S.merge(st, on='year'); S['rel'] = np.log((S.share + 1e-4) / S.state)
P = pd.read_parquet(B.VIIRS, columns=['Division', 'season', 'sat'])
P = P[P.sat == 'N'] if 'N' in set(P.sat.unique()) else P
V = P.groupby(['Division', 'season']).size().rename('pts').reset_index(); V = V[(V.season >= 2014) & (V.season <= 2026)]
key2div = {k: k for k in S.key.unique()}; key2div.update({'Obedullahganj': 'Obedullahganj (Ratapani)', 'Barghat_Project': 'Barghat Project', 'Kanha_Tiger_Reserve': 'Kanha Tiger Reserve', 'PTR_MP': 'PTR MP'})
vs = V.groupby('season').pts.sum().rename('state_pts'); V = V.merge(vs, on='season'); V['rel'] = np.log((V.pts + 1) / V.state_pts)

def trend(d, ycol, tcol, nperm=999):
    d = d.dropna(subset=[ycol]); t = d[tcol].values.astype(float); y = d[ycol].values
    if len(d) < 6: return np.nan, np.nan
    t = t - t.mean(); b = (t * y).sum() / (t * t).sum()
    perm = np.array([(t * rng.permutation(y)).sum() / (t * t).sum() for _ in range(nperm)])
    return b, (np.abs(perm) >= abs(b)).mean()

rows = []
for key, d in S.groupby('key'):
    b, p = trend(d, 'rel', 'year'); dv = key2div.get(key, key); v = V[V.Division == dv]; bv, pv = trend(v, 'rel', 'season')
    first = d[d.year <= 2019].share.mean(); last = d[d.year >= 2023].share.mean()
    rows.append(dict(key=key, division=dv, forest_ha=d.forest.iloc[0], burnt_share_2017_19=first, burnt_share_2023_25=last, scar_trend_per_yr=b, scar_p=p, viirs_trend_per_yr=bv, viirs_p=pv,
                     change_pct_per_yr_scar=100 * (np.exp(b) - 1), change_pct_per_yr_viirs=100 * (np.exp(bv) - 1) if not np.isnan(bv) else np.nan))
R = pd.DataFrame(rows); R['verdict'] = np.where((R.scar_p < 0.05) & (np.sign(R.scar_trend_per_yr) == np.sign(R.viirs_trend_per_yr)), np.where(R.scar_trend_per_yr < 0, 'improving', 'worsening'), 'no clear trend')
R = R.sort_values('scar_trend_per_yr'); R.to_csv(OUT + 'n2_trend.csv', index=False)
print(R.verdict.value_counts().to_dict()); print('expected false positives at p<0.05 among', len(R), ':', round(0.05 * len(R), 1))
print(R[R.verdict != 'no clear trend'][['division', 'forest_ha', 'burnt_share_2017_19', 'burnt_share_2023_25', 'change_pct_per_yr_scar', 'scar_p', 'change_pct_per_yr_viirs', 'viirs_p', 'verdict']].round(3).to_string(index=False))
DIV = gpd.read_file('/mnt/project-files/fire-alert-scars/mp/out/mp_divisions.geojson').merge(R, left_on='Division', right_on='division', how='left')
fig, ax = plt.subplots(figsize=(12, 10)); col = {'improving': '#1a9850', 'worsening': '#d73027', 'no clear trend': '#eeeeee'}
DIV.plot(ax=ax, color=DIV.verdict.map(col).fillna('#ffffff'), edgecolor='#888888', lw=0.4)
for _, d in DIV.iterrows():
    c = d.geometry.representative_point(); lab = d.Division.replace('_', ' ') + (f"\n{d.change_pct_per_yr_scar:+.0f}%/yr" if d.verdict in ('improving', 'worsening') else ''); ax.text(c.x, c.y, lab, fontsize=5.5, ha='center', color='#222222')
ax.set_axis_off(); ax.legend(handles=[Patch(color=col['improving'], label='burning falling relative to the state (scars p < 0.05, VIIRS agrees)'), Patch(color=col['worsening'], label='burning rising relative to the state'), Patch(color=col['no clear trend'], label='no clear trend')], loc='lower left', fontsize=9)
ax.set_title('Nine-season trend in burnt forest share, each division against the state that season (2017-25 scars; VIIRS 2014-26 as the check)', fontsize=11)
plt.tight_layout(); plt.savefig(FIG + 'r30_fig9_trend.png', dpi=160); plt.close(); print('fig done')
