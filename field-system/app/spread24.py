"""Where a fire is likely to have burned 24 h after its latest VIIRS look: a map for the officials' card (spread thread's final
recipe, ratapani/spread/unseen_validation/README.md sections 17-18; built 19 Oct 2026 on the coordinator's relay of Akkshay's
"do all things possible").

The map is the 265 m blocks around every VIIRS dot of the fire so far, plus a LEARNED amount of extra area, filled
nearest-first around the dots (so it is a buffer of the dots at the radius that gives that area). The extra area is a
LightGBM on what is known at the look (dots, fronts, FRP, fire age, gap since the previous look, spread of the dots, time,
satellites), evaluated in numpy. Two versions (Akkshay 19 Oct "train on all over mp", docs/spread24/MP_RETRAIN.md):
  - outside Ratapani: trained on Ratapani + 2,600 MP fires (600 of 200 ha+, 2,000 of 20-200 ha), data/models/spread24_area_mp.json.
    Unseen MP fires (season and division held out): big 0.535 vs 0.528 Ratapani-only vs 0.490 rule; small 0.466 vs 0.461 vs 0.457.
  - inside Ratapani (+5 km): the Ratapani-only model, data/models/spread24_area.json, which is 0.003 better there.

Unseen-fire overlap with the burn scar 24 h later (mean per fire, season held out): today's rule (24.1 ha per active front,
nearest-first) 0.447, this map 0.460 (better on 456 fires, worse on 238). The spread thread's best map adds a Prithvi fill
order (0.487), but its Prithvi and ground layers exist for Ratapani only, so it is not used here. A clear same-day Sentinel-2
scene beats both (~0.53, section 18); that is the 30 m arrow's job (app/direction.py) and not drawn here.
Replay (docs/spread24/replay.json): 45% of the map burns, it covers 61% of what burns. It never changes the alert, its beats or the search area."""
import json, math
from datetime import timedelta
import numpy as np

from . import config

MODELS = {"ratapani": config.BASE / "data/models/spread24_area.json", "mp": config.BASE / "data/models/spread24_area_mp.json"}
AOI = config.BASE / "data/models/ratapani_aoi.geojson"
BLOCK, LINK, GAP_H, MED_HA = 265.0, 750.0, 2.0, 24.1
COLS = ["doy", "hour", "n_dots", "n_last", "n_prev", "n_fronts", "n_act", "age_h", "gap_h", "frp_last", "frp_max", "frp_all",
        "ext_x", "ext_y", "foot_ha", "day", "sats_last"]
NOTE = ("Likely burnt ground 24 h after the latest VIIRS look. On past fires about 45% of this area had burned by then, and it "
        "covered about 60% of what burned. Planning aid only: guards search as usual.")
_M = {}


def _model(which):
    if which not in _M:
        d = json.load(open(MODELS[which]))
        assert d["cols"] == COLS, "spread24 model columns changed"
        _M[which] = [t["tree_structure"] for t in d["tree_info"]]
    return _M[which]


def region(xy):
    """'ratapani' when the dots' centre is within 5 km of the Ratapani AOI, else 'mp'."""
    if "aoi" not in _M:
        from pyproj import Transformer
        from shapely.geometry import shape
        from shapely.ops import transform, unary_union
        to43 = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
        _M["aoi"] = transform(to43, unary_union([shape(f["geometry"]) for f in json.load(open(AOI))["features"]])).buffer(5000)
    from shapely.geometry import Point
    return "ratapani" if _M["aoi"].contains(Point(*np.asarray(xy).mean(0))) else "mp"


def predict(X, which="mp"):
    """Sum of the trees (log1p extra ha), as lightgbm's Booster.predict."""
    from .runway import _tree
    X = np.asarray(X, float)
    out = np.zeros(len(X))
    for t in _model(which):
        _tree(t, X, out, np.arange(len(X)))
    return out


def clusters(xy):
    """Fronts: dots linked within 750 m."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    if len(xy) == 1:
        return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0:
        return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]


def looks(t):
    """VIIRS look index per dot (t sorted, hours): a gap over 2 h starts a new look."""
    return np.concatenate([[0], np.cumsum(np.diff(t) > GAP_H)]).astype(int)


def _discs(xy, r):
    from shapely.geometry import MultiPoint
    return MultiPoint([tuple(p) for p in xy]).buffer(r, 32)


def features(dots):
    """dots: list of dict(t=aware/naive UTC datetime, x, y (EPSG:32643 m), frp, sat, day) of one fire, up to the issue look.
    Returns (feature dict in COLS order, xy array, the 265 m blocks)."""
    dots = sorted(dots, key=lambda d: d["t"])
    t0 = dots[0]["t"]
    th = np.array([(d["t"] - t0).total_seconds() / 3600 for d in dots])
    lk = looks(th)
    k = lk[-1]
    xy = np.array([[d["x"], d["y"]] for d in dots])
    frp = np.array([d["frp"] or 0.0 for d in dots])
    lab = clusters(xy)
    last, prev = lk == k, lk == k - 1
    tk = dots[-1]["t"]
    blocks = _discs(xy, BLOCK)
    f = dict(doy=tk.timetuple().tm_yday, hour=tk.hour, n_dots=len(xy), n_last=int(last.sum()), n_prev=int(prev.sum()),
             n_fronts=len(set(lab)), n_act=len(set(lab[lk >= k - 1])), age_h=th[-1],
             gap_h=th[-1] - th[prev].max() if prev.any() else -1, frp_last=frp[last].sum(), frp_max=frp[last].max(),
             frp_all=frp.sum(), ext_x=np.ptp(xy[:, 0]), ext_y=np.ptp(xy[:, 1]), foot_ha=blocks.area / 1e4,
             day=int(any(d["day"] for d, l in zip(dots, last) if l)), sats_last=len({d["sat"] for d, l in zip(dots, last) if l}))
    return f, xy, blocks


def extra_ha(f, which="mp"):
    return float(max(math.expm1(predict([[f[c] for c in COLS]], which)[0]), 0.0))


def fill(xy, blocks, extra):
    """Blocks plus `extra` ha filled nearest-first: the buffer of the dots whose area is blocks + extra (bisection on radius)."""
    target = blocks.area + extra * 1e4
    if extra <= 0:
        return blocks, BLOCK
    lo, hi = BLOCK, BLOCK + math.sqrt(target / math.pi) + 50
    for _ in range(25):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _discs(xy, mid).area < target else (lo, mid)
        if hi - lo < 2:
            break
    r = (lo + hi) / 2
    return _discs(xy, r), r


def compute(dots):
    f, xy, blocks = features(dots)
    which = region(xy)
    ex = extra_ha(f, which)
    shape, r = fill(xy, blocks, ex)
    return f, ex, shape, r, which


def for_incident(con, iid, now_utc):
    """GeoJSON Feature of the 24 h map from the fire's VIIRS dots up to now; None when its latest look is over 24 h old."""
    from . import firms
    from pyproj import Transformer
    rows = con.execute("""SELECT lat, lon, acq_utc, frp, satellite, daynight FROM detections WHERE incident_id=? AND instrument='VIIRS'
                          AND satellite<>'FSI' AND acq_utc <= ? ORDER BY acq_utc""", (iid, firms.iso(now_utc))).fetchall()
    if not rows:
        return None
    last = firms.parse_utc(rows[-1]["acq_utc"])
    if now_utc - last > timedelta(hours=24):
        return None
    to43 = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
    dots = []
    for r in rows:
        x, y = to43(r["lon"], r["lat"])
        dots.append(dict(t=firms.parse_utc(r["acq_utc"]), x=x, y=y, frp=r["frp"], sat=r["satellite"], day=r["daynight"] == "D"))
    f, ex, shape, r, which = compute(dots)
    from shapely.ops import transform
    back = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform
    geo = transform(back, shape.simplify(10))
    from shapely.geometry import mapping
    return {"type": "Feature", "geometry": mapping(geo),
            "properties": {"from_look_utc": rows[-1]["acq_utc"], "valid_until_utc": firms.iso(last + timedelta(hours=24)),
                           "area_ha": round(shape.area / 1e4, 1), "extra_ha": round(ex, 1), "radius_m": round(r),
                           "rule_extra_ha": round(MED_HA * f["n_act"], 1), "method": "learned 24 h area, nearest-first", "model": which,
                           "zero_frp_dots": sum(1 for d in dots if not d["frp"]), "note": NOTE}}
