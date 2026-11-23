"""Split merged scars so each fire event keeps only its own burned ground.

A scar from alert_scar.py is all burned ground connected to the alert between two clear images, so it
can take in neighbouring fires that burned in the same image gap. Here every scar pixel goes to the
nearest "fire seed" burning in that gap: FIRMS alerts of any event (alert points sit on the flame front:
spread thread, median 45 m from the mapped scar, no smoke offset) and Sentinel-2 / Landsat fire pixels.
An event keeps the pixels nearest its own alerts (and fire pixels within 1 km of them on its day).
Alerts and fire pixels are first chained into fires (within 1.5 km and 1 day of each other), so the
alerts of one fire on later days share its scar; only ground nearest a different fire's seeds is dropped.

Out: out/event_scars_split.csv (event_id, scar_ha_split, share_kept, n_rivals, geometry_split)
"""
import json, os, sys
import numpy as np, pandas as pd
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from scipy.spatial import cKDTree
from pyproj import Transformer
from concurrent.futures import ProcessPoolExecutor

R = "/mnt/project-files/fire-alert-scars/"
TO = Transformer.from_crs(4326, 32643, always_xy=True)
BACK = Transformer.from_crs(32643, 4326, always_xy=True)
PIX = 20.0

L = pd.read_csv(R + "alert_scar_lookup.csv", usecols=["event_id", "latitude", "longitude", "acq_date"])
L["x"], L["y"] = TO.transform(L.longitude.values, L.latitude.values)
L["d"] = pd.to_datetime(L.acq_date)
AF = pd.read_csv(R + "out/af/af_pixels_clean.csv", usecols=["lon", "lat", "date"])
AF["x"], AF["y"] = TO.transform(AF.lon.values, AF.lat.values)
AF["d"] = pd.to_datetime(AF.date)


def fires(D, link_m=1500, link_days=1):
    """Chain points into fires: within link_m and link_days of each other, transitively (union-find)."""
    D = D.reset_index(drop=True)
    par = np.arange(len(D))
    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    t = D.d.values.astype("datetime64[D]").astype(int)
    tree = cKDTree(D[["x", "y"]].values)
    for i, j in tree.query_pairs(link_m, output_type="ndarray"):
        if abs(t[i] - t[j]) <= link_days:
            a, b = find(i), find(j)
            if a != b:
                par[a] = b
    return np.array([find(i) for i in range(len(D))])


# seeds: alerts and fire pixels chained together into fires
_s = pd.concat([L[["x", "y", "d"]].assign(kind="alert", event_id=L.event_id.values),
                AF[["x", "y", "d"]].assign(kind="af", event_id=None)], ignore_index=True)
if os.environ.get("SPLIT_NO_AF"):
    _s = _s[_s.kind == "alert"].reset_index(drop=True)
_s["fire"] = fires(_s)
SEEDS = _s
E = pd.read_csv(R + "out/event_scars.csv")
E = E[E.geometry.notna() & E.status.astype(str).str.startswith("scar")].copy()


def tr(g):
    g = shape(json.loads(g)) if isinstance(g, str) else g
    from shapely.ops import transform
    return transform(lambda x, y, z=None: TO.transform(x, y), g)


def one(r):
    r = pd.Series(r)
    g = tr(r.geometry)
    d0, d1, day = pd.Timestamp(r.pre_date), pd.Timestamp(r.post_date), pd.Timestamp(r.date)
    x0, y0, x1, y1 = g.bounds
    W, H = int(np.ceil((x1 - x0) / PIX)) + 1, int(np.ceil((y1 - y0) / PIX)) + 1
    T = from_origin(x0, y1, PIX, PIX)
    m = rasterize([g], out_shape=(H, W), transform=T).astype(bool)
    if not m.any():
        return None
    rr, cc = np.nonzero(m)
    px = x0 + (cc + 0.5) * PIX; py = y1 - (rr + 0.5) * PIX
    pad = 1500
    a = SEEDS[(SEEDS.d >= d0) & (SEEDS.d <= d1) & SEEDS.x.between(x0 - pad, x1 + pad) & SEEDS.y.between(y0 - pad, y1 + pad)]
    myfires = set(SEEDS.fire[SEEDS.event_id == r.event_id])
    own = a[a.fire.isin(myfires)]
    if not len(own):
        return None
    rival = a[~a.fire.isin(myfires)]
    S_own = own[["x", "y"]].values
    S_riv = rival[["x", "y"]].values
    do = cKDTree(S_own).query(np.c_[px, py])[0]
    keep = do <= (cKDTree(S_riv).query(np.c_[px, py])[0] if len(S_riv) else np.inf)
    k = np.zeros_like(m); k[rr[keep], cc[keep]] = True
    # keep the connected part touching own seeds (drops islands claimed through a gap)
    from scipy.ndimage import label
    lab, n = label(k, structure=np.ones((3, 3)))
    sr = ((y1 - S_own[:, 1]) // PIX).astype(int); sc = ((S_own[:, 0] - x0) // PIX).astype(int)
    ok = (sr >= 0) & (sr < H) & (sc >= 0) & (sc < W)
    ids = set(lab[sr[ok], sc[ok]]) - {0}
    if not ids:   # seeds just outside the scar: keep the part nearest them
        dmin = {i: do[(lab[rr, cc] == i)].min() for i in range(1, n + 1) if (lab[rr, cc] == i).any()}
        ids = {min(dmin, key=dmin.get)} if dmin else set()
    k = np.isin(lab, list(ids))
    ha = k.sum() * PIX * PIX / 1e4
    geom = None
    if k.any():
        polys = [shape(s) for s, v in shapes(k.astype(np.uint8), mask=k, transform=T) if v == 1]
        from shapely.ops import transform
        geom = json.dumps(mapping(transform(lambda x, y, z=None: BACK.transform(x, y), unary_union(polys).simplify(10))))
    return dict(event_id=r.event_id, scar_ha=r.scar_ha, scar_ha_split=round(ha, 2), share_kept=round(k.sum() / m.sum(), 3),
                n_rival_alerts=int((rival.kind == "alert").sum()), n_rival_af=int((rival.kind == "af").sum()),
                n_rival_fires=rival.fire.nunique(), geometry_split=geom)


if __name__ == "__main__":
    with ProcessPoolExecutor(8) as ex:
        out = [x for x in ex.map(one, E.to_dict("records"), chunksize=50) if x]
    O = pd.DataFrame(out)
    O.to_csv(R + "out/event_scars_split.csv", index=False)
    print(len(O), "scars; median ha before", O.scar_ha.median(), "after", O.scar_ha_split.median())
    print("share kept quartiles", O.share_kept.quantile([.25, .5, .75]).round(2).tolist(),
          "scars with any rival", (O.n_rival_alerts + O.n_rival_af > 0).mean().round(3))
