"""Which side of a new fire is likely to burn farther: a hint for the officials' alert card (Akkshay asked for it on 18 Oct 2026
"after proper scientific research"; research/runway-statewide/README.md).

Statewide test, 4,104 fronts of tiger-reserve fires 2017-25, held out by reserve: the side this model picks burned farther than the
side it ranks last 67% of the time (66-69) with 8 compass sides, against 50% by chance and 58% for "the side with most forest";
the picked side burned past 500 m 20% of the time against 9% for the last side. Shuffled-front and rotated nulls give 46-50%.
It is not the VIIRS dot being off-centre: fronts whose dots sit within 150 m of the scar's centre score the same (69%).
What drives it: the lie of the land within 300 m (local height, slope direction), the side the front's hottest dots sit on,
then distance to the first road, forest edge, crop and valley floor along each direction.

Inputs at the first VIIRS look of a new fire, from its dot centre along 36 directions, 0-2 km (same as the research):
  ESA WorldCover 10 m 2021 and Copernicus DEM 30 m (public cloud files), roads from Overture 2026-09 (data/runway/mp_roads_40m.tif),
  and the front's own dots (FRP-weighted offset, long axis). The model (data/runway/model.json, LightGBM trees) is evaluated here
  in numpy. A hint only: it never changes the alert, its order or the search area; guards keep searching on all sides.
"""
import json, math, os
from datetime import timedelta
import numpy as np

from . import config

DIR = config.BASE / "data/runway"
ON = os.environ.get("FS_RUNWAY", "1") == "1"
STEP, PAD = 20.0, 3200.0
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
SEC = ((np.arange(36) * 10 + 22.5) // 45 % 8).astype(int)
WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{}_Map.tif"
DEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{0}_00_{1}_00_DEM/Copernicus_DSM_COG_10_{0}_00_{1}_00_DEM.tif"
NOTE = ("Hint only: on past MP fires the side named here burned farther than the least likely side about 2 times in 3. "
        "Keep searching on all sides.")
[os.environ.setdefault(k, os.environ["CURL_CA_BUNDLE"]) for k in ("GDAL_CURL_CA_BUNDLE", "PROJ_CURL_CA_BUNDLE") if os.environ.get("CURL_CA_BUNDLE")]
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
_M = {}


def _model():
    if not _M:
        d = json.load(open(DIR / "model.json"))
        _M["cols"], _M["trees"] = d["cols"], [t["tree_structure"] for t in d["tree_info"]]
    return _M


def _tree(node, X, out, idx):
    if "leaf_value" in node:
        out[idx] += node["leaf_value"]
        return
    x = X[idx, node["split_feature"]]
    nan = np.isnan(x)
    left = np.where(nan, node.get("default_left", True) if node.get("missing_type") == "NaN" else (0.0 <= node["threshold"]),
                    x <= node["threshold"])
    _tree(node["left_child"], X, out, idx[left])
    _tree(node["right_child"], X, out, idx[~left])


def predict(X):
    out = np.zeros(len(X))
    for t in _model()["trees"]:
        _tree(t, X, out, np.arange(len(X)))
    return out


def _grid(urls, tr, W, H, resampling, dtype):
    import rasterio
    from rasterio.vrt import WarpedVRT
    out = np.zeros((H, W), dtype)
    for u in urls:
        try:
            with rasterio.open(u) as src, WarpedVRT(src, crs="EPSG:32643", transform=tr, width=W, height=H, resampling=resampling, nodata=0) as v:
                a = v.read(1)
            out = np.where(a != 0, a, out).astype(dtype)
        except Exception as e:
            if "404" not in str(e) and "not recognized" not in str(e) and "No such file" not in str(e):
                raise
    return out


def features(front):
    """front: {x, y (EPSG:32643 m), hot_b, hot_m, ax, el, mom}. Returns the 36 x len(cols) feature matrix and the layers used."""
    from pyproj import Transformer
    from rasterio.transform import from_origin
    from rasterio.enums import Resampling
    from scipy.ndimage import uniform_filter, binary_dilation
    x0, y1 = math.floor((front["x"] - PAD) / STEP) * STEP, math.ceil((front["y"] + PAD) / STEP) * STEP
    W = H = int(2 * PAD / STEP)
    tr = from_origin(x0, y1, STEP, STEP)
    inv = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform
    lo, la = inv(np.array([x0, x0 + W * STEP]), np.array([y1 - H * STEP, y1]))
    wc = _grid({WC_URL.format(f"N{int(math.floor(a / 3) * 3):02d}E{int(math.floor(o / 3) * 3):03d}") for a in la for o in lo},
               tr, W, H, Resampling.nearest, np.uint8)
    el = _grid({DEM_URL.format(f"N{int(math.floor(a)):02d}", f"E{int(math.floor(o)):03d}") for a in la for o in lo},
               tr, W, H, Resampling.bilinear, np.float32).astype(float)
    import rasterio
    from rasterio.vrt import WarpedVRT
    with rasterio.open(DIR / "mp_roads_40m.tif") as src, WarpedVRT(src, transform=tr, width=W, height=H, resampling=Resampling.nearest) as v:
        rd = binary_dilation(v.read(1).astype(bool), iterations=1)     # within ~40 m, as in the research
    loc = el - uniform_filter(el, 51)
    gy, gx = np.gradient(el, STEP)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    tree, grass, crop = wc == 10, np.isin(wc, [20, 30]), wc == 40
    S = np.arange(20, 2001, 20.0)
    rows = []
    for j in range(36):
        az = math.radians(j * 10)
        X, Y = front["x"] + S * math.sin(az), front["y"] + S * math.cos(az)
        rr = np.clip(np.floor((y1 - Y) / STEP).astype(int), 0, H - 1); cc = np.clip(np.floor((X - x0) / STEP).astype(int), 0, W - 1)
        t_ = tree[rr, cc]
        nt3 = np.r_[[not t_[i:i + 3].any() for i in range(len(S) - 2)], False, False]
        fd = lambda m: float(S[np.argmax(m)]) if m.any() else 4000.0
        gr = np.gradient(el[rr, cc], STEP)
        rec = dict(d_road=fd(rd[rr, cc]), d_edge=fd(nt3), d_crop=fd(crop[rr, cc]), d_valley=fd(loc[rr, cc] < -10))
        for a, b in [(0, 300), (300, 1000)]:
            m = (S > a) & (S <= b)
            rec.update({f"tree_{a}_{b}": t_[m].mean(), f"grass_{a}_{b}": grass[rr, cc][m].mean(), f"crop_{a}_{b}": crop[rr, cc][m].mean(),
                        f"grade_{a}_{b}": gr[m].mean(), f"local_height_{a}_{b}": loc[rr, cc][m].mean(), f"slope_{a}_{b}": slope[rr, cc][m].mean()})
        d = j * 10
        rec["hot_side"] = math.cos(math.radians(d - front["hot_b"])) * min(front["hot_m"], 300) / 300
        rec["along_dots"] = abs(math.cos(math.radians(d - front["ax"]))) * math.log(front["el"]) if np.isfinite(front["ax"]) else 0.0
        rec["momentum"] = math.cos(math.radians(d - front["mom"])) if np.isfinite(front.get("mom", np.nan)) else np.nan
        rows.append(rec)
    cols = _model()["cols"]
    return np.array([[r[c] for c in cols] for r in rows], float), rows, bool(el.any()), bool(wc.any())


def front_of(dots):
    """dots: [(x, y, frp)] of the first look's front (EPSG:32643). Same summary as the research (r1_events.py)."""
    xy = np.array([(d[0], d[1]) for d in dots], float); w = np.array([max(d[2] or 0, .1) for d in dots])
    cx, cy = xy.mean(0)
    hx, hy = (w * xy[:, 0]).sum() / w.sum() - cx, (w * xy[:, 1]).sum() / w.sum() - cy
    if len(xy) >= 3:
        wv, vv = np.linalg.eigh(np.cov((xy - [cx, cy]).T)); ax = math.degrees(math.atan2(vv[0, 1], vv[1, 1])); el = math.sqrt(wv[1] / max(wv[0], 1))
    else:
        ax, el = float("nan"), 1.0
    return dict(x=cx, y=cy, hot_b=math.degrees(math.atan2(hx, hy)), hot_m=math.hypot(hx, hy), ax=ax, el=el, mom=float("nan"))


def _why(rows, k, open_side):
    """Plain words for a side from the ground along its rays."""
    r = [rows[j] for j in range(36) if SEC[j] == k]
    mean = lambda c: float(np.mean([x[c] for x in r]))
    words = []
    if open_side:
        if mean("tree_0_300") >= .6: words.append("forest")
        g = mean("grade_0_300")
        if g > .03: words.append("uphill")
        elif g < -.03: words.append("downhill")
    else:
        for c, name in [("d_road", "road"), ("d_crop", "farmland"), ("d_edge", "forest edge"), ("d_valley", "valley floor")]:
            d = min(x[c] for x in r)
            if d <= 600:
                words.append(f"{name} {int(round(d, -1))} m")
                break
    return ", ".join(words)


def compute(dots):
    """dots: [(x, y, frp)] of the first look's front. Returns {status, open, stop, sector scores, text}."""
    fr = front_of(dots)
    X, rows, dem_ok, wc_ok = features(fr)
    if not (dem_ok and wc_ok):
        return {"status": "no_ground_data"}
    p = predict(X)
    sp = np.array([p[SEC == k].mean() for k in range(8)])
    a, b = int(np.argmax(sp)), int(np.argmin(sp))
    wa, wb = _why(rows, a, True), _why(rows, b, False)
    text = f"Likely to burn farther toward the {COMPASS[a]}" + (f" ({wa})" if wa else "") + f"; least toward the {COMPASS[b]}" + (f" ({wb})" if wb else "")
    return {"status": "found", "open": COMPASS[a], "stop": COMPASS[b], "open_why": wa, "stop_why": wb,
            "sectors": {COMPASS[k]: round(float(sp[k]), 3) for k in range(8)}, "text": text}


# ---------- in the app ----------
def run_due(now_utc, limit=40, ids=None):
    """Score new fires' first VIIRS looks (big_fire.check's first look and new-fire rule) seen in the last 2 days, once each."""
    from . import db, firms, big_fire
    from pyproj import Transformer
    to43 = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
    with db.tx() as con:
        if ids is None:
            ids = [r["id"] for r in con.execute(
                """SELECT i.id FROM incidents i LEFT JOIN fire_runway f ON f.incident_id=i.id
                   WHERE COALESCE(i.kind,'alert')='alert' AND i.first_seen_utc >= ? AND i.first_seen_utc <= ?
                   AND (f.incident_id IS NULL OR (f.status='error' AND f.checked_utc <= ?))
                   ORDER BY f.incident_id IS NOT NULL, i.first_seen_utc DESC LIMIT ?""",
                (firms.iso(now_utc - timedelta(days=2)), firms.iso(now_utc - timedelta(minutes=30)),
                 firms.iso(now_utc - timedelta(hours=1)), limit))]   # an error (network) is retried hourly
    n = 0
    for iid in ids:
        try:          # one bad fire must not stop the others (it used to raise out of the loop, every loop)
            with db.tx() as con:
                inc = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
                look = first_look(con, inc, now_utc)
            res = {"status": "not_new_fire"} if look is None else compute([(*to43(d["lon"], d["lat"]), d["frp"]) for d in look])
        except Exception as e:
            res = {"status": "error", "error": str(e)[:200]}
        with db.tx() as con:
            con.execute("INSERT OR REPLACE INTO fire_runway VALUES (?,?,?,?)", (iid, firms.iso(now_utc), res["status"], json.dumps(res)))
        n += 1
    return n


def first_look(con, inc, now_utc):
    """The first-look dots of a NEW fire (same rules as big_fire.check), or None."""
    from . import big_fire, firms
    b = big_fire.check(con, inc, firms.iso(now_utc))
    if not b or not b.get("new_fire"):
        return None
    v = [dict(x) for x in con.execute("""SELECT satellite, lat, lon, acq_utc, frp FROM detections WHERE incident_id=? AND instrument='VIIRS'
                                         AND satellite<>'FSI' ORDER BY acq_utc LIMIT 1""", (inc["id"],))]
    t0 = firms.parse_utc(v[0]["acq_utc"]); dl = 6 / 111.32
    cand = [dict(x) for x in con.execute("""SELECT lat, lon, frp FROM detections WHERE satellite=? AND instrument='VIIRS' AND beat_uid IS NOT NULL
                                            AND acq_utc BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?""",
                                         (v[0]["satellite"], v[0]["acq_utc"], firms.iso(t0 + timedelta(minutes=10)),
                                          v[0]["lat"] - dl, v[0]["lat"] + dl, v[0]["lon"] - dl * 1.1, v[0]["lon"] + dl * 1.1))]
    first, rest = [v[0]], [p for p in cand if (p["lat"], p["lon"]) != (v[0]["lat"], v[0]["lon"])]
    grew = True
    while grew:                            # the research's front: dots linked within 750 m
        grew = False
        for p in rest[:]:
            if any(big_fire._m(p, q) <= 750 for q in first):
                first.append(p); rest.remove(p); grew = True
    return first


def for_incident(con, iid):
    if not ON:
        return None
    r = con.execute("SELECT status, data FROM fire_runway WHERE incident_id=?", (iid,)).fetchone()
    if not r or r["status"] != "found":
        return None
    d = json.loads(r["data"])
    return {"open": d["open"], "stop": d["stop"], "text": d["text"], "note": NOTE}
