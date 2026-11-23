"""Does growing scars into ground that has dropped by the later check image fix the too-small outlines?
For the real "scar" outlines in the Wayback sample: rerun alert_scar with grow_to_check=True, then on the
Wayback image compare brightness of (a) the original scar, (b) the added ground, (c) a 150 m ring outside the
grown scar. Added ground as dark as the scar and darker than the ring = growth right. Out: grow_eval.csv"""
import json, sys, numpy as np, pandas as pd
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor as ProcessPoolExecutor
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
import render as RD, measure_helpers as MH
D = RD.D
TO = Transformer.from_crs(4326, 32643, always_xy=True); BK = Transformer.from_crs(32643, 4326, always_xy=True)
X = pd.read_csv(D + "sample.csv"); K = pd.read_csv(D + "key.csv")
X = X.join(K[["kind", "status"]]); X = X[(X.kind == "real") & (X.status == "scar")]
def one(t):
    i, r = t
    import alert_scar
    try:
        o = alert_scar.alert_scar(r.lat, r.lon, r.date, "modis" if str(r.sensor) == "modis" else "viirs",
                                  grow_to_check=True, radius_m=r.radius_m if r.src == "fsi" else None)
    except Exception as e:
        import traceback; return dict(chip=i, err=traceback.format_exc()[-300:])
    if "geometry" not in o:
        return dict(chip=i, err=o.get("status"))
    g0, g1 = shape(json.loads(r.scar_geom)), shape(o["geometry"])
    u = lambda g: transform(lambda x, y, z=None: TO.transform(x, y), g)
    b = lambda g: transform(lambda x, y, z=None: BK.transform(x, y), g)
    G0, G1 = u(g0), u(g1).buffer(0)
    add = G1.difference(G0.buffer(20)); ring = G1.buffer(150).difference(G1.buffer(20))
    band = G0.buffer(150).difference(G0.buffer(20)).difference(G1.buffer(20))   # next to the scar, not added
    im, to = RD.img(int(r.release), int(min(r.MaxMapLevel, 18)), r.lat, r.lon)
    a = np.asarray(im, np.float32).mean(2)
    res = dict(chip=i, ha0=G0.area / 1e4, ha1=G1.area / 1e4, age=r.age)
    for k, g in (("scar", g0), ("add", b(add)), ("ring", b(ring)), ("band", b(band))):
        m = MH.mask(g, to)
        res["br_" + k] = a[m].mean() if m.sum() >= 100 else np.nan
    return res
if __name__ == "__main__":
    with ProcessPoolExecutor(6) as ex:
        R = pd.DataFrame(list(ex.map(one, list(X.iterrows()))))
    R.to_csv(D + "grow_eval.csv", index=False)
    v = R.dropna(subset=["br_scar", "br_ring"])
    print(len(R), "rerun;", len(v), "measured; area median", v.ha0.median().round(1), "->", v.ha1.median().round(1))
    w = v.dropna(subset=["br_add"])
    print(len(w), "with added ground. median brightness scar / added / ring:",
          w.br_scar.median().round(1), w.br_add.median().round(1), w.br_ring.median().round(1))
    z = v.dropna(subset=["br_band"])
    print("control: ground next to the scar but NOT added, darker than ring:", (z.br_band < z.br_ring).mean().round(3), "median", z.br_band.median().round(1))
    print("added darker than ring:", (w.br_add < w.br_ring).mean().round(3),
          "| added within 3 units of scar or darker:", (w.br_add <= w.br_scar + 3).mean().round(3))
