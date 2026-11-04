"""Before/after false-colour chips (SWIR2-NIR-red, leaf-on window) for visual interpretation."""
import io
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
from PIL import Image, ImageDraw

from common import *
from common import _landsat, _sentinel2

CHIP_PX, CHIP_M = 96, 2880      # 96 x 30 m view with a marked centre pixel


def rgb_year(year, roi):
    """Leaf-on true colour for chips, Landsat + S2 median. SWIR-NIR-red separates cleared ground from dry forest."""
    c = _landsat("LANDSAT/LC08/C02/T1_L2", year, WINDOW, roi, False)
    if year >= 2021:
        c = c.merge(_landsat("LANDSAT/LC09/C02/T1_L2", year, WINDOW, roi, False))
    if year <= 2016:
        c = c.merge(_landsat("LANDSAT/LE07/C02/T1_L2", year, WINDOW, roi, True))
    if year >= 2016:
        c = c.merge(_sentinel2(year, WINDOW, roi).map(lambda i: i.toFloat().copyProperties(i, ["system:time_start"])))
    return c.map(lambda i: i.toFloat().copyProperties(i, ["system:time_start"])).median().select(["swir2", "nir", "red"])


def chip_pair(s, out):
    """Montage of four years: two before and two after the mapped year (or fixed years for stable samples)."""
    f = out / f"{s.sample_id:04d}.png"
    if f.exists():
        return
    if s.map_year < 0:          # blind mode: same years for every point, so they reveal nothing about the map
        years = [2017, 2019, 2022, 2025]
    else:
        y = s.map_year if s.map_year > 0 else 2020
        years = [y - 2, y - 1, y, min(y + 2, 2025)]
    half = CHIP_M / 2
    roi = ee.Geometry.Rectangle([s.x - half, s.y - half, s.x + half, s.y + half], ee.Projection(WKT), False).transform("EPSG:4326", 10)
    tiles = []
    for yy in years:
        for attempt in range(3):
            try:
                img = rgb_year(yy, roi).visualize(min=[0.0, 0.05, 0.0], max=[0.30, 0.45, 0.18])
                raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(
                    dimensions=dict(width=CHIP_PX, height=CHIP_PX), crsWkt=WKT,
                    affineTransform=dict(scaleX=RES, shearX=0, translateX=s.x - half, shearY=0, scaleY=-RES, translateY=s.y + half))))
                a = np.load(io.BytesIO(raw))
                tiles.append(np.dstack([a["vis-red"], a["vis-green"], a["vis-blue"]]))
                break
            except Exception as e:
                if attempt == 2:
                    print("chip failed", s.sample_id, yy, str(e)[:120], flush=True)
                    tiles.append(np.zeros((CHIP_PX, CHIP_PX, 3), "uint8"))
    scale = 2
    W = CHIP_PX * scale
    canvas = Image.new("RGB", (W * 4 + 18, W + 18), "white")
    dr = ImageDraw.Draw(canvas)
    for i, (t, yy) in enumerate(zip(tiles, years)):
        canvas.paste(Image.fromarray(t.astype("uint8")).resize((W, W), Image.NEAREST), (i * (W + 6), 18))
        dr.text((i * (W + 6) + 2, 3), str(yy), fill="black")
        cx, cy = i * (W + 6) + W // 2, 18 + W // 2
        dr.rectangle([cx - 4, cy - 4, cx + 4, cy + 4], outline="yellow")
    canvas.save(f)


def make_chips(df, out):
    out.mkdir(parents=True, exist_ok=True)
    init()
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda s: chip_pair(s, out), df.itertuples()))
    print("chips in", out)


