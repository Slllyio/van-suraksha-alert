"""Teak-mixed vs other dry deciduous classifier. Weak labels: Roy et al. 2015 vegetation type map (60 m, ~2005-10 polygons):
class 25 teak mixed moist deciduous = 1; 26 dry deciduous + 23 moist deciduous = 0. Interior pixels only (>=180 m from a class edge).
Features: monthly S2 NDVI + NDMI Oct-May, red-edge/SWIR bands + NDRE for Oct Dec Feb Apr May (2023-25 medians), S2 canopy cover. Spatial block CV (4 km blocks)."""
import numpy as np, rasterio, lightgbm as lgb, json
from rasterio.warp import reproject, Resampling
from rasterio.transform import Affine
from scipy.ndimage import minimum_filter, maximum_filter
from sklearn.metrics import roc_auc_score
S = np.load('static10.npz'); W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform'])
f = S['inside'].astype(bool) & np.isin(S['wc'], [10, 20, 30]); cov = np.load('canopy_s2.npz')['s2']
r = rasterio.open('/mnt/project-files/ratapani/fsi/scouting/data/vtm_roy2015_ratapani_5kmbuf.tif'); v = r.read(1)
lab60 = np.full(v.shape, 255, np.uint8); lab60[v == 25] = 1; lab60[np.isin(v, [26, 23])] = 0
inter = (minimum_filter(lab60, 7) == maximum_filter(lab60, 7))
lab60 = np.where(inter, lab60, 255).astype(np.uint8)
lab = np.full((H, W), 255, np.uint8)
reproject(lab60, lab, src_transform=r.transform, src_crs=r.crs, dst_transform=TR, dst_crs='EPSG:32643', resampling=Resampling.nearest, src_nodata=255, dst_nodata=255)
names = []; F = []
for m in [10, 11, 12, 1, 2, 3, 4, 5]:
    z = np.load(f'monthly/m{m:02d}.npz')
    for b in ['ndvi', 'ndmi']: F.append(z[b]); names.append(f'{b}_{m:02d}')
for m in [10, 12, 2, 4, 5]:
    z = np.load(f'monthly_re/m{m:02d}.npz')
    for b in ['B05', 'B06', 'B8A', 'B11', 'B12']: F.append(z[b]); names.append(f'{b}_{m:02d}')
    F.append(((z['B8A'].astype('float32') - z['B05']) / (z['B8A'].astype('float32') + z['B05'] + 1e-6)).astype('float16')); names.append(f'ndre_{m:02d}')
F.append(cov.astype('float16')); names.append('cover')
use = f & (lab != 255) & (cov >= 0.25)
yy, xx = np.nonzero(use); rng = np.random.default_rng(0); k = rng.choice(len(yy), min(400000, len(yy)), replace=False); yy, xx = yy[k], xx[k]
X = np.stack([a[yy, xx].astype('float32') for a in F], 1); y = lab[yy, xx]
blk = (yy // 400) * 100 + (xx // 400); ub = np.unique(blk); fold = {b: i % 5 for i, b in enumerate(rng.permutation(ub))}; fo = np.array([fold[b] for b in blk])
print('pixels', len(y), 'teak share', round(y.mean(), 3), 'blocks', len(ub))
P = np.zeros(len(y)); prm = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbose=-1)
for i in range(5):
    tr, te = fo != i, fo == i
    b = lgb.train(prm, lgb.Dataset(X[tr], y[tr]), 300); P[te] = b.predict(X[te])
auc = roc_auc_score(y, P); acc = ((P > 0.5) == y).mean()
bal = 0.5 * (((P > 0.5) & (y == 1)).sum() / (y == 1).sum() + ((P <= 0.5) & (y == 0)).sum() / (y == 0).sum())
# block-level: share of pixels predicted teak vs label
print('pixel AUC', round(auc, 3), 'acc', round(acc, 3), 'balanced acc', round(bal, 3))
bm = lgb.train(prm, lgb.Dataset(X, y), 300)
imp = sorted(zip(bm.feature_importance('gain'), names), reverse=True)[:8]; print([(n, int(g)) for g, n in imp])
# phenology means by class
for c in (0, 1): print(c, 'NDVI Oct..May', np.round([np.nanmean(X[y == c, j]) for j in range(0, 16, 2)], 3))
# full map
out = np.full((H, W), np.nan, 'float32'); fy, fx = np.nonzero(f)
for s in range(0, len(fy), 2_000_000):
    a, bq = fy[s:s + 2_000_000], fx[s:s + 2_000_000]
    out[a, bq] = bm.predict(np.stack([q[a, bq].astype('float32') for q in F], 1))
np.save('teakprob2.npy', out)
json.dump(dict(pixels=int(len(y)), teak_share=float(y.mean()), auc=float(auc), acc=float(acc), balanced_acc=float(bal), top=[(n, int(g)) for g, n in imp]), open('teakclf2.json', 'w'))
