"""All-MP per-cell fuel dryness from HLS (Sentinel-2 + Landsat harmonised), 500 m grid in EPSG:32643 aligned with the
Ratapani grid (X0 399000, Y1 2996000, 1829 x 1332 cells; cell = row * 1829 + col). For each 10-day step d (Jan 2 ... Jun 21,
seasons 2017-2026): per clear look (Fmask bits 1-4 off) NDVI, NDMI, NBR, median over the 15 days before d, read at 120 m
(EE pyramid; 30 m was too slow for all MP) and averaged over each 500 m cell, plus the share of the cell with a clear look.
Only the 105 tiles of 128 x 128 cells that hold beat cells are pulled.
Output: tiles/{season}_{MMDD}_{tr}_{tc}.npy int16 (4, 128, 128): ndvi, ndmi, nbr x 10000, clear % ; -9999 = no clear look.
Usage: python mp_dry_pull.py [seasons...]   (skips files that exist; 6 parallel requests)"""
import os, sys, time, json, numpy as np, pandas as pd, ee
from concurrent.futures import ThreadPoolExecutor
ee.Initialize(project='van-suraksha-alert')
HERE = r'E:\FIRE\mp'; OUT = HERE + r'\tiles'; os.makedirs(OUT, exist_ok=True)
X0, Y1, S, T = 399000.0, 2996000.0, 500.0, 128
CRS = 'EPSG:32643'
TILES = json.load(open(HERE + r'\mp_tiles.json'))
PIN = ee.Projection(CRS).atScale(int(os.environ.get('MP_SCALE', '120')))
MP = ee.Geometry.Rectangle([X0, Y1 - 1332 * S, X0 + 1829 * S, Y1], ee.Projection(CRS), False)
def prep(i, nir, red, sw1, sw2):
    m = i.select('Fmask').bitwiseAnd(0b11110).eq(0)
    n, r, s1, s2 = i.select(nir), i.select(red), i.select(sw1), i.select(sw2)
    return ee.Image.cat(n.subtract(r).divide(n.add(r)).rename('ndvi'), n.subtract(s1).divide(n.add(s1)).rename('ndmi'),
                        n.subtract(s2).divide(n.add(s2)).rename('nbr')).updateMask(m)
def window(a, b):   # filter first, then map (mapping the whole global HLS archive first stalls the request)
    s30 = ee.ImageCollection('NASA/HLS/HLSS30/v002').filterDate(a, b).filterBounds(MP).map(lambda i: prep(i, 'B8A', 'B4', 'B11', 'B12'))
    l30 = ee.ImageCollection('NASA/HLS/HLSL30/v002').filterDate(a, b).filterBounds(MP).map(lambda i: prep(i, 'B5', 'B4', 'B6', 'B7'))
    return s30.merge(l30)
def image(d):
    med = window(str((d - pd.Timedelta(days=15)).date()), str(d.date())).median().setDefaultProjection(PIN)
    clr = med.select('ndvi').mask().rename('clear').setDefaultProjection(PIN)
    idx = med.reduceResolution(ee.Reducer.mean(), maxPixels=4096).multiply(10000)
    cl = clr.unmask(0).reduceResolution(ee.Reducer.mean(), maxPixels=4096).multiply(100)
    return idx.addBands(cl).round().toInt16().unmask(-9999)
NAMES = ['ndvi', 'ndmi', 'nbr', 'clear']
def pull(d, img, tr, tc):
    f = os.path.join(OUT, f"{d.strftime('%Y_%m%d')}_{tr:02d}_{tc:02d}.npy")
    if os.path.exists(f): return 'skip'
    for k in range(5):
        try:
            a = ee.data.computePixels({'expression': img, 'fileFormat': 'NUMPY_NDARRAY',
                'grid': {'dimensions': {'width': T, 'height': T}, 'crsCode': CRS,
                         'affineTransform': {'scaleX': S, 'shearX': 0, 'translateX': X0 + tc * T * S, 'shearY': 0, 'scaleY': -S, 'translateY': Y1 - tr * T * S}}})
            np.save(f, np.stack([a[n] for n in NAMES]).astype(np.int16)); return 'ok'
        except Exception as e:
            msg = str(e)[:300]; print('  retry', k, msg, flush=True); time.sleep(10 * (k + 1))
    print('  FAILED', f, msg, flush=True); return 'FAILED'
if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == 'test':   # one tile (holds Ratapani), one date
        d = pd.Timestamp('2024-03-21'); t0 = time.time(); print(pull(d, image(d), 6, 5), f'{time.time() - t0:.0f}s', flush=True)
        print(np.load(os.path.join(OUT, '2024_0321_06_05.npy'))[:, 60:63, 60:63]); sys.exit()
    seasons = [int(v) for v in args] or list(range(2017, 2027))
    with ThreadPoolExecutor(6) as ex:
        for Y in seasons:
            for d in pd.date_range(f'{Y}-01-02', f'{Y}-06-21', freq='10D'):
                t0 = time.time(); img = image(d)
                res = list(ex.map(lambda t: pull(d, img, t[0], t[1]), TILES))
                print(Y, d.date(), {r: res.count(r) for r in set(res)}, f'{time.time() - t0:.0f}s', flush=True)
    print('MP_DRY_DONE')
