import numpy as np, requests, json, io, os
from pyproj import Transformer
from scipy.ndimage import minimum_filter, maximum_filter
from rasterio.transform import Affine
from concurrent.futures import ThreadPoolExecutor
S = np.load('static10.npz'); TR = Affine(*S['transform']); c = np.load('phenoclass.npz')['c']
same = (minimum_filter(c, 5) == c) & (maximum_filter(c, 5) == c)
tf = Transformer.from_crs(32643, 4326, always_xy=True); rng = np.random.default_rng(7)
MD = 'https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2026_r09/MapServer/{}/query'
def meta(lon, lat):
    for L in (4, 5, 6):
        try:
            r = requests.get(MD.format(L), params=dict(geometry=f'{lon},{lat}', geometryType='esriGeometryPoint', inSR=4326, outFields='SRC_DATE2,SRC_RES,NICE_DESC', returnGeometry='false', f='json'), timeout=60).json()
            if r.get('features'): a = r['features'][0]['attributes']; return a
        except Exception: pass
    return None
pts = []
for k in range(1, 6):
    yy, xx = np.nonzero(same & (c == k)); i = rng.choice(len(yy), 40, replace=False)
    for j in i:
        x, y = TR * (xx[j] + .5, yy[j] + .5); lon, lat = tf.transform(x, y); pts.append(dict(cls=k, lon=lon, lat=lat))
with ThreadPoolExecutor(8) as ex: ms = list(ex.map(lambda p: meta(p['lon'], p['lat']), pts))
import datetime
for p, m in zip(pts, ms):
    if m and m.get('SRC_DATE2'): d = datetime.datetime.utcfromtimestamp(m['SRC_DATE2'] / 1000); p['date'] = d.strftime('%Y-%m-%d'); p['res'] = m.get('SRC_RES')
json.dump(pts, open('vhr/pts.json', 'w'))
from collections import Counter
print(Counter((p['cls'], p.get('date', '')[5:7]) for p in pts))
