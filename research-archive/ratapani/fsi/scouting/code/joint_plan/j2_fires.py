"""Round r30, step 2. Which fires the combined programme touches: every scar fire 2017-25 by where it started (inside a tr3 patch
and which cb8 rank tier, or outside) and by size, and which fires' outlines a practical line crosses (held-out seasons 2022-25).
Out: out/j2_fires.csv (one row per fire: key, division, year, forest_ha, start_patch, tier of that patch, crosses_line),
     out/j2_bigfires.csv (summary by size class x start tier, 2022-25)."""
import os, sys, glob, pickle, time
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2/'); import m0 as M
K = M.K; HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
P = pd.read_csv(OUT + 'j1_patches.csv')
tier_of = {(k, p): (c, t) for k, p, c, t in zip(P.key, P.patch, P.cum_ha, P.tier)}
KEYS = sorted(p.split('fires_')[1][:-4] for p in glob.glob(M.SC26 + 'fires_*.pkl') if 'table' not in p)
rows = []; t0 = time.time()
for key in KEYS:
    L, FOR, Z = K.load_div(key); H, W = L['H'], L['W']; LAB = K.lab60(Z, 'tr3', H, W).ravel()
    for f in L['fires']:
        h, w = f['shape']; ig = f['ign'].astype(np.int64)
        Mm = np.unpackbits(f['M'])[:h * w].astype(bool); loc = np.nonzero(Mm)[0]; gl = (loc // w + f['r0']) * W + (loc % w + f['c0'])
        fha = FOR[gl].sum() * M.CELL_HA; tot = len(loc) * M.CELL_HA
        p = 0
        if len(ig):
            gi = (ig // w + f['r0']) * W + (ig % w + f['c0']); lb = LAB[gi]; lb = lb[lb > 0]
            if len(lb) and len(lb) * 2 >= len(ig): p = int(np.bincount(lb).argmax())
        inpatch = (LAB[gl] > 0) & FOR[gl]
        cum, tier = tier_of.get((key, p), (np.nan, 'outside'))
        rows.append(dict(key=key, division=L['div'], year=f['year'], t0=str(f['t0'])[:10], ha=tot, forest_ha=fha, in_patch_forest_ha=inpatch.sum() * M.CELL_HA,
                         start_patch=p, start_cum_ha=cum, start_tier=tier))
    print(key, len(L['fires']), round(time.time() - t0), flush=True)
D = pd.DataFrame(rows); D.to_csv(OUT + 'j2_fires.csv', index=False)
D['size'] = pd.cut(D.forest_ha, [-1, 10, 50, 200, 500, 1000, 1e9], labels=['<10', '10-50', '50-200', '200-500', '500-1000', '1000+'])
T = D[D.year >= 2022]
def tier_lab(c):
    if np.isnan(c): return 'outside patches'
    for n, l in ((25000, 'burn set 25k'), (50000, '25-50k'), (100000, '50-100k'), (200000, '100-200k')):
        if c <= n: return l
    return 'rest of tr3'
T = T.assign(start=T.start_cum_ha.map(tier_lab))
S = T.groupby(['size', 'start'], observed=True).agg(fires=('ha', 'size'), forest_ha=('forest_ha', 'sum')).reset_index()
S['fires_per_yr'] = S.fires / 4; S['forest_ha_per_yr'] = S.forest_ha / 4; S.to_csv(OUT + 'j2_bigfires.csv', index=False)
print(S.pivot(index='size', columns='start', values='forest_ha_per_yr').round(0))
print(S.pivot(index='size', columns='start', values='fires_per_yr').round(1))
