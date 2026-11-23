"""HLS (Sentinel-2 + Landsat harmonised) 6-band composites on the Ratapani 500 m grid box at 31.25 m (16 px = one cell, Prithvi patch).
One composite per 10-day step: median of clear (Fmask) looks in the 15 days before each step date d, for d = Jan 22 ... Jun 21, seasons 2017-2026.
Bands in Prithvi order: Blue, Green, Red, NIR narrow, SWIR1, SWIR2 (reflectance x 10000, int16, -9999 = no clear look).
Output: hls/{season}_{MMDD}.npy (6, 1072, 2400)."""
import os, sys, time, numpy as np, pandas as pd, ee
ee.Initialize(project='van-suraksha-alert')
OUT = r'E:\FIRE\ratapani\prithvi_dyn\hls'; os.makedirs(OUT, exist_ok=True)
X0, Y1, W, H, S = 739500.0, 2558500.0, 150 * 16, 67 * 16, 31.25
CRS = 'EPSG:32643'
BOX = ee.Geometry.Rectangle([X0, Y1 - H * S, X0 + W * S, Y1], ee.Projection(CRS), False)
NAMES = ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2']
def clear(i):   # Fmask bits: 1 cloud, 2 adjacent, 3 shadow, 4 snow; keep only clear land/water
    q = i.select('Fmask'); m = q.bitwiseAnd(0b11110).eq(0)
    return i.updateMask(m)
s30 = ee.ImageCollection('NASA/HLS/HLSS30/v002').filterBounds(BOX).map(lambda i: clear(i).select(['B2', 'B3', 'B4', 'B8A', 'B11', 'B12'], NAMES))
l30 = ee.ImageCollection('NASA/HLS/HLSL30/v002').filterBounds(BOX).map(lambda i: clear(i).select(['B2', 'B3', 'B4', 'B5', 'B6', 'B7'], NAMES))
hls = s30.merge(l30)
def pull(d):
    f = os.path.join(OUT, d.strftime('%Y_%m%d') + '.npy')
    if os.path.exists(f): return 'skip'
    c = hls.filterDate(str((d - pd.Timedelta(days=15)).date()), str(d.date()))
    img = c.median().multiply(10000).round().toInt16().unmask(-9999)
    for k in range(5):
        try:
            a = ee.data.computePixels({'expression': img, 'fileFormat': 'NUMPY_NDARRAY',
                'grid': {'dimensions': {'width': W, 'height': H}, 'crsCode': CRS,
                         'affineTransform': {'scaleX': S, 'shearX': 0, 'translateX': X0, 'shearY': 0, 'scaleY': -S, 'translateY': Y1}}})
            arr = np.stack([a[n] for n in NAMES]).astype(np.int16); np.save(f, arr)
            return f'{(arr[0] != -9999).mean():.2f} clear'
        except Exception as e:
            print('  retry', k, str(e)[:200], flush=True); time.sleep(15 * (k + 1))
    return 'FAILED'
seasons = [int(v) for v in sys.argv[1:]] or list(range(2017, 2027))
for Y in seasons:
    for d in pd.date_range(f'{Y}-01-22', f'{Y}-06-21', freq='10D'):
        t = time.time(); r = pull(d); print(Y, d.date(), r, f'{time.time() - t:.0f}s', flush=True)
print('HLS_DONE')
