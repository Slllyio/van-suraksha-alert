"""HLS v2.0 (S30 + L30) frames for one statewide region box (mp/regions.json), same 4 frames per season as the Ratapani run
(Apr Y-1, Nov Y-1, 5-28 Jan Y, 1-14 Feb Y). Any MGRS tile touching the box; up to K clear looks per tile, per-pixel median.
Reads only the box through a warped VRT (proxy signs *.nasa.gov; no token in code). Out: mp/hls/{region}/{Y}_F{k}.npy int16 (6, H, W)"""
import os, sys, json, time, requests, numpy as np, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from pyproj import Transformer
os.environ['CURL_CA_BUNDLE'] = os.environ['GDAL_CURL_CA_BUNDLE'] = '/root/.ccr/ca-bundle.crt'
os.environ['GDAL_HTTP_COOKIEFILE'] = os.environ['GDAL_HTTP_COOKIEJAR'] = '/tmp/gdal_cookies.txt'
os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'; os.environ['CPL_VSIL_CURL_ALLOWED_EXTENSIONS'] = '.tif'
os.environ['GDAL_HTTP_MULTIRANGE'] = 'YES'; os.environ['GDAL_HTTP_MERGE_CONSECUTIVE_RANGES'] = 'YES'
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
REG = sys.argv[1]; g = json.load(open(f'{SP}/mp/regions.json'))[REG]
X0, Y1, W, H, S = g['X0'], g['Y1'], g['W'], g['H'], 30.0
TR = rasterio.transform.from_origin(X0, Y1, S, S)
inv = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform
lo = [inv(x, y) for x in (X0, X0 + W * S) for y in (Y1, Y1 - H * S)]
BB = f'{min(p[0] for p in lo):.4f},{min(p[1] for p in lo):.4f},{max(p[0] for p in lo):.4f},{max(p[1] for p in lo):.4f}'
OUT = f'{SP}/mp/hls/{REG}'; os.makedirs(OUT, exist_ok=True)
BANDS = {'HLSS30': ['B02', 'B03', 'B04', 'B8A', 'B11', 'B12'], 'HLSL30': ['B02', 'B03', 'B04', 'B05', 'B06', 'B07']}
K = 3
def windows(Y):
    return [(f'{Y-1}-04-01', f'{Y-1}-04-30'), (f'{Y-1}-11-01', f'{Y-1}-11-30'), (f'{Y}-01-05', f'{Y}-01-28'), (f'{Y}-02-01', f'{Y}-02-14')]
def granules(t0, t1):
    out = []
    for sn in BANDS:
        for k in range(5):
            try:
                r = requests.get('https://cmr.earthdata.nasa.gov/search/granules.json', params={'short_name': sn, 'version': '2.0',
                    'bounding_box': BB, 'temporal': f'{t0}T00:00:00Z,{t1}T23:59:59Z', 'page_size': 500}, timeout=60); ent = r.json()['feed']['entry']; break
            except Exception as ex:
                print('  cmr retry', k, str(ex)[:100], flush=True); time.sleep(10 * (k + 1))
        for e in ent:
            links = {l['href'].split('.')[-2]: l['href'] for l in e['links'] if l['href'].startswith('https://data.lpdaac') and l['href'].endswith('.tif')}
            out.append(dict(sn=sn, title=e['title'], tile=e['title'].split('.')[2], cc=float(e.get('cloud_cover') or 100), links=links))
    return out
def read(url, nod):
    for k in range(6):
        try:
            with rasterio.open('/vsicurl/' + url) as src:
                with WarpedVRT(src, crs='EPSG:32643', transform=TR, width=W, height=H, resampling=Resampling.nearest, nodata=nod) as v:
                    return v.read(1)
        except Exception as e:
            print('   retry', k, str(e)[:150], flush=True); time.sleep(5 * (k + 1))
    raise RuntimeError(url)
def frame(t0, t1):
    G = granules(t0, t1); used = []; stack = []
    for tile in sorted({x['tile'] for x in G}):
        n = 0
        for x in sorted([x for x in G if x['tile'] == tile], key=lambda x: x['cc']):
            if n >= K: break
            fm = read(x['links']['Fmask'], 255)
            ok = (fm != 255) & ((fm & 0b11110) == 0)
            if ok.mean() < 0.02: continue
            b = np.stack([read(x['links'][bn], -9999) for bn in BANDS[x['sn']]]).astype(np.float32)
            b[:, ~ok] = np.nan; b[b == -9999] = np.nan
            stack.append(b); used.append((x['title'], x['cc'], round(float(ok.mean()), 3))); n += 1
    cov = np.zeros((H, W), bool)
    for b in stack: cov |= ~np.isnan(b[0])
    tried = {u[0] for u in used}; extra = 0
    for x in sorted(G, key=lambda x: x['cc']):                 # top up gaps (partial-swath looks) until 97% clear
        if cov.mean() >= 0.97 or extra >= 12: break
        if x['title'] in tried: continue
        tried.add(x['title']); extra += 1
        fm = read(x['links']['Fmask'], 255); ok = (fm != 255) & ((fm & 0b11110) == 0)
        if (ok & ~cov).mean() < 0.01: continue
        b = np.stack([read(x['links'][bn], -9999) for bn in BANDS[x['sn']]]).astype(np.float32)
        b[:, ~ok] = np.nan; b[b == -9999] = np.nan
        stack.append(b); used.append((x['title'], x['cc'], round(float(ok.mean()), 3))); cov |= ~np.isnan(b[0])
    import warnings; warnings.filterwarnings('ignore')
    a = np.nanmedian(np.stack(stack), 0) if stack else np.full((6, H, W), np.nan)
    return np.where(np.isnan(a), -9999, np.round(a)).astype(np.int16), used
for Y in [int(v) for v in sys.argv[2:]]:
    meta = {}
    for k, (t0, t1) in enumerate(windows(Y), 1):
        f = f'{OUT}/{Y}_F{k}.npy'
        if os.path.exists(f) and (os.environ.get('REPAIR') is None or (np.load(f, mmap_mode='r')[0] != -9999).mean() >= 0.95): continue
        t = time.time(); a, used = frame(t0, t1); np.save(f + '.tmp.npy', a); os.rename(f + '.tmp.npy', f)
        meta[f'F{k}'] = dict(window=[t0, t1], used=used, clear=float((a[0] != -9999).mean()))
        print(REG, Y, k, len(used), 'looks', round(meta[f'F{k}']['clear'], 3), 'clear', f'{time.time()-t:.0f}s', flush=True)
    json.dump(meta, open(f'{OUT}/{Y}_meta.json', 'a'), indent=1)
