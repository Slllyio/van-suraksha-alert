"""Per-fire error bands for the v1 outlines from Esri Wayback sub-metre images (<= 15 days after the fire).
Eye-reading single points failed: at the scale needed to see a whole fire, burned litter under canopy can't be told
point by point. So each fire is split into zones and its brightness is unmixed between two references taken from the
same image:
  burned  = core of the outline (> 40 m inside the edge)
  unburned = far ring 400-700 m outside the outline (no other v1 scar of the season there)
Burned share of a zone = (B_unburned - B_zone) / (B_unburned - B_burned), clipped 0..1.
Zones: inner edge 0-40 m inside, outer bands 0-75 and 75-250 m. Missed area = sum of band area x burned share;
false area = inner-edge area x (1 - burned share) + whole outline if the core is not darker than the far ring.
The same is done on decoys (the outline moved 3 km into unburned forest) to show the noise level.
Out: check/zones.csv"""
import json, sys, numpy as np, pandas as pd
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from shapely.affinity import translate
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/wayback")
import render as RD, measure_helpers as MH
C = "/mnt/project-files/fire-alert-scars/reference/v1_2026-10-15/"
TO = Transformer.from_crs(4326, 32643, always_xy=True); BK = Transformer.from_crs(32643, 4326, always_xy=True)
u = lambda g: transform(lambda x, y, z=None: TO.transform(x, y), g)
b = lambda g: transform(lambda x, y, z=None: BK.transform(x, y), g)
M = pd.read_csv("/mnt/project-files/fire-alert-scars/wayback/matches.csv")
M = M[(M.src == "firms") & (M.age <= 15)].drop_duplicates("event_id")
FE = json.load(open(C + "firms_event_scars.geojson"))["features"]
F = {f["properties"]["event_id"]: f for f in FE}
M = M[M.event_id.isin(F) & M.event_id.map(lambda e: e in F and F[e]["properties"]["status"] == "scar")]
# other scars of the same season, to keep them out of the far ring
GEO = {e: u(shape(f["geometry"])).buffer(0) for e, f in F.items()}
SEAS = {e: f["properties"]["date"][:4] for e, f in F.items()}
rng = np.random.default_rng(5)
def one(r, decoy=False):
    G = GEO[r.event_id]
    if decoy:
        a = rng.uniform(0, 2 * np.pi); G = translate(G, 3000 * np.cos(a), 3000 * np.sin(a))
    others = unary_union([g for e, g in GEO.items() if SEAS[e] == r.date[:4] and e != r.event_id and g.distance(G) < 800] or [G.buffer(-1e6)])
    z = {"core": G.buffer(-40), "edge_in": G.difference(G.buffer(-40)), "out_0_75": G.buffer(75).difference(G),
         "out_75_250": G.buffer(250).difference(G.buffer(75)), "far": G.buffer(700).difference(G.buffer(400)).difference(others.buffer(50))}
    x0, y0, x1, y1 = G.buffer(720).bounds
    lo, la = BK.transform((x0 + x1) / 2, (y0 + y1) / 2)
    half = max(x1 - x0, y1 - y0) / 2
    zz = int(min(r.MaxMapLevel, 18, np.floor(np.log2(156543.03 * np.cos(np.radians(la)) * 2048 / (2 * half)))))   # canvas <= ~2k px
    im, to = RD.img(int(r.release), zz, la, lo, half_m=half)
    a = np.asarray(im, np.float32).mean(2)
    res = dict(event_id=r.event_id, decoy=decoy, year=int(r.date[:4]), age=r.age, scar_ha=G.area / 1e4, src_res=r.SRC_RES)
    for k, g in z.items():
        m = MH.mask(b(g), to) if not g.is_empty else np.zeros_like(a, bool)
        res["n_" + k] = int(m.sum()); res["br_" + k] = float(a[m].mean()) if m.sum() >= 30 else np.nan
        res["ha_" + k] = g.area / 1e4
    return res
if __name__ == "__main__":
    rows = list(M.itertuples())
    with ThreadPoolExecutor(3) as ex:
        R = list(ex.map(lambda r: one(r), rows)) + list(ex.map(lambda r: one(r, True), rows))
    pd.DataFrame(R).to_csv(C + "check/zones.csv", index=False)
    print(len(R))
