"""Render a season's burn map (colour = month of burn) and false-colour (SWIR2/NIR/red) scenes."""
import sys, os
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch
I = fetch.INSIDE


def full(a, fill=0):
    f = np.full(I.shape, fill, a.dtype); f[I] = a; return f


def falsecolor(fn):
    z = np.load(fn)
    rgb = np.stack([full(z['swir2']), full(z['nir']), full(z['red'])], -1).astype(float) / 10000
    rgb = np.clip(rgb / np.array([0.35, 0.45, 0.2]), 0, 1); rgb[~full(z['valid'], False)] = 0
    return (rgb * 255).astype(np.uint8)


def burnmap(fn):
    b = np.load(fn); e = full(b['end'], -999)
    cm = np.zeros(I.shape + (3,), np.uint8); cm[I] = 60
    for a, c, col in [(-40, 31, (255, 255, 0)), (31, 59, (255, 150, 0)), (59, 90, (255, 0, 0)),
                      (90, 120, (200, 0, 200)), (120, 200, (0, 150, 255))]:
        cm[(e >= a) & (e < c) & (e > -999)] = col
    return cm  # yellow Jan, orange Feb, red Mar, purple Apr, blue May-Jun


if __name__ == "__main__":
    kind, src, dst = sys.argv[1:4]
    img = burnmap(src) if kind == "burn" else falsecolor(src)
    if len(sys.argv) > 4:
        img = img[tuple(slice(*map(int, s.split(':'))) for s in sys.argv[4:6])]
    Image.fromarray(img).save(dst)
