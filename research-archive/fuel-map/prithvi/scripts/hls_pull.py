"""Pull HLS v2.0 (S30 + L30) composites over the Ratapani box from NASA LP DAAC (proxy signs *.nasa.gov requests).
Grid: EPSG:32643, 30 m, X 739500..814500, Y 2524920..2558520 (2500 x 1120 px), aligned to HLS tile pixels.
Per season Y, 4 frames (pre-fire for fires after 15 Feb): F1 Apr (Y-1) leaf-off, F2 Nov (Y-1) full leaf, F3 5-28 Jan (Y), F4 1-14 Feb (Y).
Each frame = per-pixel median of up to K clear looks (Fmask cloud/adjacent/shadow/snow removed), bands B02 B03 B04 NIRn SWIR1 SWIR2 (x10000).
Out: hls/{Y}_F{k}.npy int16 (6, 1120, 2500), -9999 no clear look; hls/{Y}_meta.json"""
import os, sys, json, time, requests, numpy as np, rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from rasterio.warp import reproject
os.environ['CURL_CA_BUNDLE'] = os.environ['GDAL_CURL_CA_BUNDLE'] = '/root/.ccr/ca-bundle.crt'
os.environ['GDAL_HTTP_COOKIEFILE'] = '/tmp/gdal_cookies.txt'; os.environ['GDAL_HTTP_COOKIEJAR'] = '/tmp/gdal_cookies.txt'
os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'; os.environ['CPL_VSIL_CURL_ALLOWED_EXTENSIONS'] = '.tif'
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
X0, Y1, W, H, S = 739500.0, 2558520.0, 2500, 1120, 30.0
X1, Y0 = X0 + W * S, Y1 - H * S
TR = rasterio.transform.from_origin(X0, Y1, S, S)
BANDS = {'HLSS30': ['B02', 'B03', 'B04', 'B8A', 'B11', 'B12'], 'HLSL30': ['B02', 'B03', 'B04', 'B05', 'B06', 'B07']}
K = 3
def windows(Y):
    return [(f'{Y-1}-04-01', f'{Y-1}-04-30'), (f'{Y-1}-11-01', f'{Y-1}-11-30'), (f'{Y}-01-05', f'{Y}-01-28'), (f'{Y}-02-01', f'{Y}-02-14')]
def granules(t0, t1):
    out = []
    for sn in BANDS:
        r = requests.get('https://cmr.earthdata.nasa.gov/search/granules.json', params={'short_name': sn, 'version': '2.0',
            'bounding_box': '77.38,22.82,78.13,23.14', 'temporal': f'{t0}T00:00:00Z,{t1}T23:59:59Z', 'page_size': 200}, timeout=60)
        for e in r.json()['feed']['entry']:
            tile = e['title'].split('.')[2]
            if tile not in ('T43QGF', 'T43QHF'): continue
            links = {l['href'].split('.')[-2]: l['href'] for l in e['links'] if l['href'].startswith('https://data.lpdaac') and l['href'].endswith('.tif')}
            out.append(dict(sn=sn, title=e['title'], tile=tile, cc=float(e.get('cloud_cover') or 100), links=links, t=e['time_start']))
    return out
def read(url):
    for k in range(5):
        try:
            with rasterio.open('/vsicurl/' + url) as src:
                dst = np.full((H, W), -9999 if 'Fmask' not in url else 255, np.int16)
                reproject(rasterio.band(src, 1), dst, src_nodata=src.nodata, dst_transform=TR, dst_crs='EPSG:32643', dst_nodata=dst[0, 0], resampling=Resampling.nearest)
                return dst
        except Exception as e:
            print('   retry', k, str(e)[:150], flush=True); time.sleep(5 * (k + 1))
    raise RuntimeError(url)
def frame(t0, t1):
    G = granules(t0, t1); used = []
    stack = []
    for tile in ('T43QGF', 'T43QHF'):
        g = sorted([x for x in G if x['tile'] == tile], key=lambda x: x['cc'])[:K]
        for x in g:
            fm = read(x['links']['Fmask'])
            ok = (fm != 255) & ((fm & 0b11110) == 0)
            if ok.mean() < 0.02: continue
            b = np.stack([read(x['links'][bn]) for bn in BANDS[x['sn']]]).astype(np.float32)
            b[:, ~ok] = np.nan; b[b == -9999] = np.nan
            stack.append(b); used.append((x['title'], x['cc'], round(float(ok.mean()), 3)))
    a = np.nanmedian(np.stack(stack), 0) if stack else np.full((6, H, W), np.nan)
    return np.where(np.isnan(a), -9999, np.round(a)).astype(np.int16), used
for Y in [int(v) for v in sys.argv[2:]]:
    meta = {}
    for k, (t0, t1) in enumerate(windows(Y), 1):
        f = f'{OUT}/{Y}_F{k}.npy'
        if os.path.exists(f): continue
        t = time.time(); a, used = frame(t0, t1); np.save(f, a)
        meta[f'F{k}'] = dict(window=[t0, t1], used=used, clear=float((a[0] != -9999).mean()))
        print(Y, k, t0, t1, len(used), 'looks', round(meta[f'F{k}']['clear'], 3), 'clear', f'{time.time()-t:.0f}s', flush=True)
    json.dump(meta, open(f'{OUT}/{Y}_meta.json', 'a'), indent=1)
