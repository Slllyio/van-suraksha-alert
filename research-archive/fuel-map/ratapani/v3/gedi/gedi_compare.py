"""Within the same canopy band, does the fuel map rank shots like GEDI's 0-5 m density (pavd_z0)? Leaf-off shots (Feb-May) see the floor layer best."""
import numpy as np, pandas as pd, rasterio
from pyproj import Transformer
from scipy.stats import spearmanr
from scipy.ndimage import uniform_filter
V = '/mnt/project-files/fuel-map/ratapani/v3/'; W = '/mnt/project-files/fuel-map/ratapani/work/'
g = pd.read_csv(V + 'gedi/gedi_l2b_ratapani.csv'); x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(g.longitude.values, g.latitude.values)
S = np.load(W + 'static10.npz'); TR = rasterio.Affine(*S['transform']); r, c = rasterio.transform.rowcol(TR, x, y); r, c = np.array(r), np.array(c)
ok = (r >= 0) & (r < int(S['H'])) & (c >= 0) & (c < int(S['W'])); g, r, c = g[ok].copy(), r[ok], c[ok]
cov = np.clip(uniform_filter(np.load(W + 'canopy_s2.npz')['s2'], 3) / 0.7, 0, 1)
def rd(f): a = rasterio.open(V + f).read(1).astype('float32'); return np.where(a == 65535, np.nan, a / 100)
g['lit'] = rd('litter_potential_central_10m.tif')[r, c]; g['tot'] = rd('fuel_total_potential_central_10m.tif')[r, c]; g['cv'] = cov[r, c]
g = g.dropna(subset=['lit', 'pavd_z0']); g['mo'] = g.month.str[5:7].astype(int); g['leafoff'] = g.mo.between(2, 5)
for name, d in (('all', g), ('leaf-off Feb-May', g[g.leafoff])):
    d = d.copy(); d['cb'] = pd.qcut(d.cv.rank(method='first'), 10, labels=False)
    print(name, len(d), 'pavd_z0 vs cover', round(spearmanr(d.pavd_z0, d.cv)[0], 2), 'vs litter', round(spearmanr(d.pavd_z0, d.lit)[0], 2),
          'within cover: litter', round(np.nanmean([spearmanr(q.pavd_z0, q.lit)[0] for _, q in d.groupby('cb')]), 2),
          'total', round(np.nanmean([spearmanr(q.pavd_z0, q.tot)[0] for _, q in d.groupby('cb')]), 2))
