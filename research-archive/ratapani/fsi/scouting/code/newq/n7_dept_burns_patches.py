"""Department burning seen from orbit, per repeat patch and season. Pre-15 Feb VIIRS burn-day clusters (early_burns table,
flag = control-like: day-only, single-day, <=2 points, FRP <= 5 MW) inside each tr3 patch -> per patch-season: early clusters,
flagged clusters. Then the held-out question: in seasons when a patch got department-like early burning, how much of it burnt
later (15 Feb+) that season, against the same patch's other seasons and the division-season (two-way FE on patch-seasons).
Out: out/n7_patch_seasons.csv, out/n7_effect.csv"""
import os, re, sys, numpy as np, pandas as pd, geopandas as gpd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/control_burn/'); import cb0 as B
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
src = open('/mnt/project-files/ratapani/fsi/scouting/code/early_burns/b3_features.py').read(); CRS = re.search(r'^CRS\s*=\s*(.+)$', src, re.M).group(1).strip()
CRS = eval(CRS) if CRS[0] in '0123456789"\'' else CRS; print('cluster CRS', CRS)
C = pd.read_parquet('/mnt/project-files/ratapani/fsi/scouting/code/early_burns/out/clusters_oct_to_15mar.parquet')
C['date'] = pd.to_datetime(C.date); C = C[(C.date.dt.month <= 2) & ~((C.date.dt.month == 2) & (C.date.dt.day >= 15))]   # Jan - 14 Feb (Oct-Dec kept too: pre-season)
C = C[C.season.between(2017, 2025)]
G = gpd.GeoDataFrame(C, geometry=gpd.points_from_xy(C.x, C.y), crs=CRS).to_crs(32643)
P = gpd.read_file('/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/j1_patches.geojson').to_crs(32643)[['key', 'patch', 'pid', 'forest_ha', 'geometry']]
J = gpd.sjoin(G, P, how='inner', predicate='within')
ps = J.groupby(['key', 'patch', 'season']).agg(early_clusters=('cid', 'size'), flagged=('flag', 'sum'), early_points=('n', 'sum')).reset_index()
# later burnt share per patch-season from the scar rasters (burn day >= 15 Feb) and early scar share (< 15 Feb)
rows = []
for key in B.KEYS:
    L, FOR = B.load_div(key); Z = np.load(B.SC26 + f'patches_{key}.npz'); lab = Z['lab_tr3']
    if lab.max() == 0: continue
    lab60 = np.repeat(np.repeat(lab, 2, 0), 2, 1)[:L['H'], :L['W']]
    if lab60.shape != FOR.shape:
        pad = np.zeros(FOR.shape, lab.dtype); pad[:lab60.shape[0], :lab60.shape[1]] = lab60[:FOR.shape[0], :FOR.shape[1]]; lab60 = pad
    ids = np.arange(1, lab.max() + 1); fcount = np.bincount(lab60[FOR], minlength=lab.max() + 1)[1:]
    for y in B.YEARS:
        D = B.burn_day(L, y); late = (D < 9999) & (D >= 46) & FOR; early = (D < 46) & FOR
        lc = np.bincount(lab60[late], minlength=lab.max() + 1)[1:]; ec = np.bincount(lab60[early], minlength=lab.max() + 1)[1:]
        for i in ids:
            if fcount[i - 1] > 0: rows.append(dict(key=key, patch=int(i), season=y, forest_ha=fcount[i - 1] * B.CELL_HA, late_share=lc[i - 1] / fcount[i - 1], early_scar_share=ec[i - 1] / fcount[i - 1]))
    print(key, flush=True)
S = pd.DataFrame(rows).merge(ps, on=['key', 'patch', 'season'], how='left').fillna({'early_clusters': 0, 'flagged': 0, 'early_points': 0})
S['dept_burn'] = (S.flagged > 0).astype(int); S['any_early'] = ((S.early_clusters > 0) | (S.early_scar_share > 0.05)).astype(int)
S.to_csv(OUT + 'n7_patch_seasons.csv', index=False)
print('patch-seasons', len(S), 'with flagged early burn', S.dept_burn.sum(), 'with any early burning', S.any_early.sum())
print(S.groupby('season')[['dept_burn', 'any_early']].mean().round(3).T)
# two-way FE: patch FE + division-season FE, weighted by forest ha
def twfe(df, x):
    d = df.copy(); d['ds'] = d.key + '_' + d.season.astype(str); y = d.late_share.values; X = d[x].values.astype(float); w = d.forest_ha.values
    for _ in range(30):
        for col in ('ds', 'patchid'):
            m = pd.DataFrame({'y': y, 'x': X}).groupby(d[col].values).transform('mean'); y = y - m.y.values; X = X - m.x.values
    b = (w * X * y).sum() / (w * X * X).sum(); return b
S['patchid'] = S.key + '_' + S.patch.astype(str)
res = []
rng = np.random.default_rng(0); keys = S.key.unique()
for x, nm in (('dept_burn', 'flagged control-like burn before 15 Feb'), ('any_early', 'any early burning (cluster or 5%+ scar) before 15 Feb')):
    b = twfe(S, x); bs = []
    for _ in range(100):
        pick = rng.choice(keys, len(keys)); bs.append(twfe(pd.concat([S[S.key == k] for k in pick]), x))
    base = S[S[x] == 0].late_share.mean()
    res.append(dict(treatment=nm, patch_seasons_treated=int(S[x].sum()), later_burnt_share_untreated=base, effect_points=b, ci_lo=np.percentile(bs, 2.5), ci_hi=np.percentile(bs, 97.5), relative=b / base))
R = pd.DataFrame(res); R.to_csv(OUT + 'n7_effect.csv', index=False); print(R.round(4).to_string(index=False))
