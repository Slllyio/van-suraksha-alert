"""Richer input for the neural net (Akkshay 17 Oct 06:22Z "use more data input then"): instead of a few summary columns per
sector, give the net a MAP PATCH around each fire step: 3 km x 3 km at 60 m (51 x 51 pixels), 15 layers.
  0 height relative to the fire (km)   1 slope (/20 deg)   2 canopy (/100)   3 litter v3 (/3 t/ha)   4 grass v3 (/2 t/ha)
  5 tree cover   6 open ground (shrub/grass)   7 non-fuel (crop/built/water/bare)   8 burnt seasons before this one (/5)
  9 burnt earlier this season (labels start before this step)   10 the fire's own trail: any earlier detection within 400 m
  11 trail recency: exp(-(hours since that detection)/12)   12 latest pass only (within 400 m)   13 distance to buildings (/3 km)
  14 distance to road (/3 km)
Steps are the same pass-to-pass steps as b14 (every fire with 3+ timed passes, any sensor). Target = sector (0 = N ... 7 = NW)
of the new burning. Saved to the scratchpad (big, rebuildable).
"""
import os, sys
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(__file__)); import feats as FT
R = '/mnt/project-files/research/big-fires/results'
OUT = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/patches.npz'
P = pd.read_csv(f'{R}/passes.csv', parse_dates=['t']); DT = pd.read_csv(f'{R}/detections.csv', parse_dates=['t']); F = pd.read_csv(f'{R}/fires.csv').set_index('fire')
npass = P.groupby('fire').t.nunique(); SELF = npass[npass >= 3].index
N = 51; RES = 60.0; off = (np.arange(N) - N // 2) * RES
GX, GY = np.meshgrid(off, -off)  # row 0 = north
def comp(dx, dy): return np.degrees(np.arctan2(dx, dy)) % 360
def season_of(t): return t.year if t.month >= 10 else t.year - 1
X, meta = [], []
for fid in SELF:
    d = DT[DT.fire == fid].sort_values('t'); f = F.loc[fid]
    big = int(f.area_ha >= 200 and f.n_looks >= 4 and f.n_viirs >= 10 and not f.still_at_edge)
    t0 = d.t.min(); season = season_of(t0); year = t0.year if t0.month < 10 else t0.year + 1
    seen = d.iloc[:0]; prev_b = None; k = 0; last = None
    for pid, g in d.groupby('pass_id', sort=False):
        if len(seen):
            dist = cKDTree(seen[['x', 'y']].values).query(g[['x', 'y']].values)[0]; new = g[dist > 400]
            if len(new):
                k += 1; cx, cy = seen.x.mean(), seen.y.mean(); b = comp(new.x.mean() - cx, new.y.mean() - cy); tn = g.t.min()
                gap = (tn - seen.t.max()).total_seconds() / 3600
                px, py = (cx + GX).ravel(), (cy + GY).ravel()
                wc = FT.s20(FT.WC, px, py); bs = FT.s20(FT.BURN[year].astype(np.float32), px, py) if year in FT.BURN else np.zeros(len(px))
                bp = np.sum([FT.s20((FT.BURN[y_] > 0).astype(np.float32), px, py) for y_ in range(2017, year)], axis=0) if year > 2017 else np.zeros(len(px))
                tr = cKDTree(seen[['x', 'y']].values); dd, ii = tr.query(np.c_[px, py]); near = dd < 400
                # recency: best (most recent) earlier detection within 400 m
                rec = np.zeros(len(px)); sh = ((tn - seen.t).dt.total_seconds().values / 3600)
                for j in np.where(near)[0]:
                    m_ = np.hypot(seen.x.values - px[j], seen.y.values - py[j]) < 400; rec[j] = np.exp(-sh[m_].min() / 12)
                lastpass = seen[seen.pass_id == seen.pass_id.iloc[-1]]; lp = cKDTree(lastpass[['x', 'y']].values).query(np.c_[px, py])[0] < 400
                ch = np.stack([(FT.s20(FT.ELEV, px, py) - FT.s20(FT.ELEV, [cx], [cy])[0]) / 1000, FT.s20(FT.SLOPE, px, py) / 20, FT.s10('canopy', px, py) / 100,
                               FT.s10('litter_v3', px, py) / 3, FT.s10('grass_v3', px, py) / 2, (wc == 10) * 1.0, np.isin(wc, [20, 30]) * 1.0, np.isin(wc, [40, 50, 60, 80]) * 1.0,
                               bp / 5, ((bs > 0) & (bs < tn.dayofyear - 1)) * 1.0, near * 1.0, rec, lp * 1.0, FT.cell(px, py, 'd_ob') / 3000, FT.cell(px, py, 'dist_road') / 3000]).reshape(15, N, N)
                X.append(np.nan_to_num(ch).astype(np.float16))
                meta.append(dict(fire=fid, big=big, season=season, k=k, sensor=g.sensor.iloc[0], gap_h=gap, night=int((g.daynight == 'N').any()), bearing_deg=b,
                                 sector=int(((b + 22.5) % 360) // 45), prev_sector=int(((prev_b + 22.5) % 360) // 45) if prev_b is not None else -1, n_seen=len(seen)))
                prev_b = b
        seen = pd.concat([seen, g])
X = np.stack(X); M = pd.DataFrame(meta)
np.savez_compressed(OUT, X=X); M.to_csv(f'{R}/ml/patch_steps.csv', index=False)
print('patches', X.shape, 'steps', len(M), 'fires', M.fire.nunique())
