import math, os, json, urllib.request, pandas as pd, numpy as np, pyproj
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from matplotlib.path import Path
Z = 18; REL = 63116
URL = 'https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{r}/{z}/{y}/{x}'
def px(lon, lat):
    n = 2 ** Z * 256; x = (lon + 180) / 360 * n; s = math.sin(math.radians(lat)); return x, (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
def tile(x, y):
    f = f'tiles/{Z}_{x}_{y}.jpg'
    if not os.path.exists(f) or os.path.getsize(f) < 1000:
        for k in range(3):
            try: open(f, 'wb').write(urllib.request.urlopen(urllib.request.Request(URL.format(r=REL, z=Z, x=x, y=y), headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()); break
            except Exception: pass
    return f
tr = pyproj.Transformer.from_crs(32643, 4326, always_xy=True)
G = {f['properties']['cell_id']: f['properties'] for f in json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']}
S = pd.read_csv('vhr_sample_all.csv')
def one(r):
    p = G[r.cell_id]; m = 250
    inner = [px(*tr.transform(p['x0'] + dx, p['y0'] + dy)) for dx, dy in ((0, 0), (500, 0), (500, 500), (0, 500))]
    (x0, y1), (x1, y0) = px(*tr.transform(p['x0'] - m, p['y0'] - m)), px(*tr.transform(p['x0'] + 500 + m, p['y0'] + 500 + m))
    tx0, tx1, ty0, ty1 = int(x0 // 256), int(x1 // 256), int(y0 // 256), int(y1 // 256)
    im = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), np.float32); ok = np.zeros(im.shape[:2], bool)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            try: a = np.asarray(Image.open(tile(tx, ty)).convert('RGB'), np.float32); im[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a; ok[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = True
            except Exception: pass
    yy, xx = np.mgrid[0:im.shape[0], 0:im.shape[1]]; X = xx + tx0 * 256 + 0.5; Y = yy + ty0 * 256 + 0.5
    inside = Path(inner).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape) & ok
    ring = (~inside) & ok & (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
    if inside.sum() < 1000 or ring.sum() < 1000: return None
    br = im.mean(2); rb = im[..., 0] - im[..., 2]
    q = np.percentile(br[ring], 20); qr = np.percentile(rb[ring], 20)
    return dict(cell_id=r.cell_id, br_in=br[inside].mean(), br_ring=br[ring].mean(), rb_in=rb[inside].mean(), rb_ring=rb[ring].mean(),
                dark_frac=(br[inside] < q).mean(), grey_frac=((br[inside] < q) & (rb[inside] < qr)).mean(),
                br_in_sd=br[inside].std())
with ThreadPoolExecutor(4) as ex: res = [x for x in ex.map(one, S.itertuples()) if x]
pd.DataFrame(res).merge(S, on='cell_id').to_csv('vhr_stats.csv', index=False); print('STATS_DONE', len(res))
