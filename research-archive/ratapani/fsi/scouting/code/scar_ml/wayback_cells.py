"""Esri Wayback post-fire image (0.3-0.5 m) for each Wayback test chip, 1 km square around the chip centre (same
window and zoom as fire-alert-scars/wayback/render.py), averaged onto the chip's 20 m cells.
Out: scratch/wb/<chip>.npz with bright (mean RGB), grey (max-min), n (image pixels per cell); NaN outside the window."""
import math, os, urllib.request, numpy as np, pandas as pd
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from pyproj import Transformer
from lib import SCR, CODE, chip_grid, RES
TD = SCR + 'wbtiles/'; os.makedirs(TD, exist_ok=True); os.makedirs(SCR + 'wb', exist_ok=True)
URL = 'https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{r}/{z}/{y}/{x}'
BK = Transformer.from_crs(32643, 4326, always_xy=True); TO = Transformer.from_crs(4326, 32643, always_xy=True)


def wpx(lon, lat, z):
    n = 2 ** z * 256; s = np.sin(np.radians(lat))
    return (lon + 180) / 360 * n, (0.5 - np.log((1 + s) / (1 - s)) / (4 * np.pi)) * n


def unwpx(px, py, z):
    n = 2 ** z * 256; lon = px / n * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py / n)))); return lon, lat


def tile(r, z, x, y):
    f = f'{TD}{r}_{z}_{x}_{y}.jpg'
    if not os.path.exists(f) or os.path.getsize(f) < 500:
        for k in range(3):
            try:
                open(f, 'wb').write(urllib.request.urlopen(urllib.request.Request(URL.format(r=r, z=z, x=x, y=y), headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()); break
            except Exception:
                pass
    try:
        return Image.open(f).convert('RGB')
    except Exception:
        return None


def one(r):
    out = f"{SCR}wb/{r['chip']}.npz"
    if os.path.exists(out): return
    lon, lat = BK.transform(r['x'], r['y']); z = int(r['zoom']); rel = int(r['release'])
    cx, cy = wpx(lon, lat, z); mpp = 156543.03 * math.cos(math.radians(lat)) / 2 ** z; h = 500 / mpp
    x0, y0, x1, y1 = cx - h, cy - h, cx + h, cy + h
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    can = Image.new('RGB', ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256)); bad = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            t = tile(rel, z, tx, ty)
            if t is None: bad += 1; continue
            can.paste(t, ((tx - tx0) * 256, (ty - ty0) * 256))
    im = can.crop((int(x0 - tx0 * 256), int(y0 - ty0 * 256), int(x1 - tx0 * 256), int(y1 - ty0 * 256))).resize((420, 420))
    im.save(f"{SCR}wb/{r['chip']}.jpg", quality=80)
    a = np.asarray(im, np.float32); br = a.mean(2).ravel(); gr = (a.max(2) - a.min(2)).ravel()
    k = (x1 - x0) / 420; u, v = np.meshgrid(np.arange(420) + 0.5, np.arange(420) + 0.5)
    lo, la = unwpx(x0 + u.ravel() * k, y0 + v.ravel() * k, z); X, Y = TO.transform(lo, la)
    tr, n = chip_grid(r['x'], r['y'], r['half'])
    c = ((X - tr.c) / RES).astype(int); rr = ((tr.f - Y) / RES).astype(int); ok = (c >= 0) & (c < n) & (rr >= 0) & (rr < n)
    lin = rr[ok] * n + c[ok]
    cnt = np.bincount(lin, minlength=n * n).astype(float)
    with np.errstate(invalid='ignore'):
        B = np.bincount(lin, br[ok], n * n) / cnt; G = np.bincount(lin, gr[ok], n * n) / cnt
    B[cnt < 20] = np.nan; G[cnt < 20] = np.nan
    np.savez_compressed(out, bright=B.reshape(n, n).astype(np.float32), grey=G.reshape(n, n).astype(np.float32), cnt=cnt.reshape(n, n), bad_tiles=bad)


if __name__ == '__main__':
    C = pd.read_csv(CODE + 'chips.csv'); C = C[C.kind.isin(['wb_real', 'wb_decoy'])]
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(one, C.to_dict('records')))
    print('done', len(C))
