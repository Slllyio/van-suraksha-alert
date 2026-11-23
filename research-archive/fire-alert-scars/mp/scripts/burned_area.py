"""Burned area without double counting: neighbouring fire events often share ground (their grown outlines overlap),
so summing scar_ha overstates the total. Here outlines are burned into a 20 m grid and burned pixels counted once.
burned_ha(geoms_wkt_or_shapely_in_4326) -> ha ; by_group(df, key) -> Series of ha per group."""
import numpy as np, shapely, geopandas as gpd, pandas as pd
from rasterio.features import rasterize
from rasterio.transform import from_origin

RES = 20.0


def burned_ha(geoms):
    g = gpd.GeoSeries([shapely.from_wkt(x) if isinstance(x, str) else x for x in geoms], crs=4326).to_crs(32643)
    g = g[~g.is_empty & g.notna()]
    if not len(g):
        return 0.0
    x0, y0, x1, y1 = g.total_bounds
    total = 0
    step = 40000.0   # tile 40 km so memory stays small for state-wide sets
    for tx in np.arange(x0, x1, step):
        for ty in np.arange(y0, y1, step):
            box = shapely.box(tx, ty, tx + step, ty + step)
            sub = g[g.intersects(box)]
            if not len(sub):
                continue
            w, h = int(np.ceil(step / RES)), int(np.ceil(step / RES))
            m = rasterize(((s, 1) for s in sub.intersection(box)), out_shape=(h, w),
                          transform=from_origin(tx, ty + step, RES, RES), fill=0, dtype="uint8")
            total += int(m.sum())
    return total * RES * RES / 1e4


def by_group(df, key, geom="geometry"):
    return df.groupby(key)[geom].apply(lambda s: burned_ha(list(s)))
