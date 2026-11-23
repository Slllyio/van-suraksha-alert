import numpy as np
from PIL import Image, ImageDraw
def mask(poly, to, size=420):
    m = Image.new("L", (size, size), 0); d = ImageDraw.Draw(m)
    for p in (getattr(poly, "geoms", None) or [poly]):
        if p.is_empty or p.geom_type != "Polygon": continue
        d.polygon([to(*c[:2]) for c in p.exterior.coords], fill=1)
        for h in p.interiors: d.polygon([to(*c[:2]) for c in h.coords], fill=0)
    return np.asarray(m, bool)
