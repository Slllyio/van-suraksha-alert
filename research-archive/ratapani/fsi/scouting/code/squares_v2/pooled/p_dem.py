"""Terrain for all MP: public AWS Terrain Tiles (terrarium PNG, zoom 10, ~140 m, SRTM-based; no login, no key),
mosaicked in web-mercator. Slope and upslope azimuth from the elevation smoothed over ~300 m (fire/pixel scale).
Out (scratch): dem_mp.npz. sample(lat, lon) returns elevation, slope (deg), upslope azimuth (deg from N)."""
import glob, os, math
import numpy as np
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
Z = 10
def build():
    from PIL import Image
    from scipy.ndimage import gaussian_filter
    fs = sorted(glob.glob(f'{SC}/dem/10_*.png'))
    xs = sorted({int(os.path.basename(f).split('_')[1]) for f in fs}); ys = sorted({int(os.path.basename(f).split('_')[2][:-4]) for f in fs})
    E = np.full((256 * len(ys), 256 * len(xs)), np.nan, np.float32)
    for f in fs:
        _, x, y = os.path.basename(f)[:-4].split('_'); x, y = int(x), int(y)
        im = np.asarray(Image.open(f).convert('RGB')).astype(np.float32)
        e = im[..., 0] * 256 + im[..., 1] + im[..., 2] / 256 - 32768
        i, j = ys.index(y), xs.index(x); E[256 * i:256 * (i + 1), 256 * j:256 * (j + 1)] = e
    Es = gaussian_filter(E, 1.0)
    rows = np.arange(E.shape[0]) + 256 * ys[0] + .5
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * rows / (256 * 2 ** Z)))))
    res = 40075016.686 / (256 * 2 ** Z) * np.cos(np.radians(lat))[:, None]      # metres per pixel, both axes
    gy, gx = np.gradient(Es)                                                   # per pixel; gy positive = southward (row down)
    dzdx = gx / res; dzdn = -gy / res
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdn))).astype(np.float32)
    upaz = (np.degrees(np.arctan2(dzdx, dzdn)) % 360).astype(np.float32)        # direction of steepest ascent
    np.savez_compressed(f'{SC}/dem_mp.npz', elev=E, slope=slope, upaz=upaz, x0=xs[0], y0=ys[0])
_D = None
def sample(lat, lon):
    global _D
    if _D is None: _D = dict(np.load(f'{SC}/dem_mp.npz'))
    n = 256 * 2 ** Z
    px = (np.asarray(lon) + 180) / 360 * n - 256 * _D['x0']
    r = np.radians(np.asarray(lat)); py = (1 - np.log(np.tan(r) + 1 / np.cos(r)) / np.pi) / 2 * n - 256 * _D['y0']
    i = np.clip(py.astype(int), 0, _D['elev'].shape[0] - 1); j = np.clip(px.astype(int), 0, _D['elev'].shape[1] - 1)
    return _D['elev'][i, j], _D['slope'][i, j], _D['upaz'][i, j]
if __name__ == '__main__':
    build(); e, s, u = sample([22.95, 23.2], [77.6, 77.4]); print(e, s, u)
