"""Chips for checking our scars by eye on Esri Wayback sub-metre imagery.
Each chip, 1 km square around the alert point: [pre-fire image] | post-fire image | same with our scar outline
(yellow) and the alert point (cyan cross). Out: chips/<n>.jpg + chips/index.csv"""
import json, math, os, sys, urllib.request
import numpy as np, pandas as pd
from PIL import Image, ImageDraw
from shapely.geometry import shape
from concurrent.futures import ThreadPoolExecutor
D = "/mnt/project-files/fire-alert-scars/wayback/"
TD = "/tmp/claude-0/-home-user/6ef53337-625f-5036-a7e0-c2b23906e620/scratchpad/wbtiles/"
os.makedirs(TD, exist_ok=True); os.makedirs(D + "chips", exist_ok=True)
URL = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{r}/{z}/{y}/{x}"
def wpx(lon, lat, z):
    n = 2 ** z * 256; s = math.sin(math.radians(lat))
    return (lon + 180) / 360 * n, (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
def tile(r, z, x, y):
    f = f"{TD}{r}_{z}_{x}_{y}.jpg"
    if not os.path.exists(f) or os.path.getsize(f) < 500:
        for k in range(3):
            try:
                open(f, "wb").write(urllib.request.urlopen(urllib.request.Request(URL.format(r=r, z=z, x=x, y=y), headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()); break
            except Exception:
                pass
    try:
        return Image.open(f).convert("RGB")
    except Exception:
        return Image.new("RGB", (256, 256), (40, 40, 40))
def img(r, z, lat, lon, half_m=500):
    cx, cy = wpx(lon, lat, z)
    mpp = 156543.03 * math.cos(math.radians(lat)) / 2 ** z
    h = half_m / mpp
    x0, y0, x1, y1 = cx - h, cy - h, cx + h, cy + h
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    can = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            can.paste(tile(r, z, tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    im = can.crop((int(x0 - tx0 * 256), int(y0 - ty0 * 256), int(x1 - tx0 * 256), int(y1 - ty0 * 256))).resize((420, 420))
    k = 420 / (x1 - x0)
    to = lambda lo, la: ((wpx(lo, la, z)[0] - x0) * k, (wpx(lo, la, z)[1] - y0) * k)
    return im, to
def draw(row, i):
    z = int(min(row["MaxMapLevel"], 18))
    post, to = img(int(row["release"]), z, row["lat"], row["lon"])
    lined = post.copy(); d = ImageDraw.Draw(lined)
    g = row.get("scar_geom")
    if isinstance(g, str):
        G = shape(json.loads(g))
        for p in (getattr(G, "geoms", None) or [G]):
            for ring in [p.exterior] + list(p.interiors):
                d.line([to(*c[:2]) for c in ring.coords], fill=(255, 230, 0), width=2)
    px, py = to(row["lon"], row["lat"])
    for dd in (d,):
        dd.line([(px - 9, py), (px + 9, py)], fill=(0, 255, 255), width=2); dd.line([(px, py - 9), (px, py + 9)], fill=(0, 255, 255), width=2)
    panels = []
    if isinstance(row.get("img_pre"), str) and not pd.isna(row.get("release_pre")):
        pre, _ = img(int(row["release_pre"]), int(min(row["MaxMapLevel_pre"], 18)), row["lat"], row["lon"]); panels.append(pre)
    panels += [post, lined]
    out = Image.new("RGB", (426 * len(panels), 420), (255, 255, 255))
    for j, p in enumerate(panels):
        out.paste(p, (426 * j, 0))
    out.save(f"{D}chips/{i:04d}.jpg", quality=85)
if __name__ == "__main__":
    M = pd.read_csv(sys.argv[1])
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda t: draw(t[1], t[0]), list(M.reset_index(drop=True).iterrows())))
    M.reset_index(drop=True).rename_axis("chip").to_csv(D + "chips/index.csv")
    print("chips", len(M))
