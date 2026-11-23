"""Phenology cover classes from monthly S2 NDVI (Sep-May, 2023-24 + 2024-25) + S2 canopy cover. Rule-based, unvalidated.
1 deciduous tree, 2 evergreen/semi-evergreen tree or green understorey under canopy, 3 shrub candidate (open, green in dry season),
4 grass (open, green after monsoon, cures early), 5 sparse/bare, 0 outside forest."""
import numpy as np
S = np.load('/tmp/claude-0/fuel/static10.npz'); ins = S['inside'].astype(bool); f = ins & np.isin(S['wc'], [10, 20, 30])
cov = np.load('/tmp/claude-0/fuel/canopy_s2.npz')['s2']
M = {m: np.load(f'/tmp/claude-0/fuel/monthly/m{m:02d}.npz')['ndvi'].astype('float32') for m in [10, 11, 12, 1, 2, 3, 4, 5]}
peak = np.nanmax(np.stack([M[10], M[11]]), 0)
dry = np.nanmax(np.stack([M[3], M[4]]), 0)        # greenest of Mar-Apr (May has teak leaf flush): robust to a burn in one month
dec = M[12]
c = np.zeros(f.shape, np.uint8)
openc = cov < 0.30
green_dry = dry >= 0.25
c[f & ~openc] = 1
c[f & ~openc & green_dry] = 2
c[f & openc & green_dry] = 3
grass = f & openc & ~green_dry & (peak >= 0.35) & ((peak - dec) >= 0.10)
c[grass] = 4
c[f & openc & ~green_dry & ~grass] = 5
c[f & (peak < 0.22)] = 5
np.savez_compressed('/tmp/claude-0/fuel/phenoclass.npz', c=c, peak=peak, dry=dry, dec=dec)
n = f.sum(); print({k: round(100 * (c[f] == k).mean(), 1) for k in range(1, 6)})
