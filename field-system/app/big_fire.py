"""Chance that a new alert becomes a 200 ha+ fire, from the research points table
(ratapani/fsi/scouting/big_fire_chance_at_alert.md section 6, code/big_fire_chance/b8_points.py; tables frozen in
data/big_fire/: fitted on all-MP scar truth 2017-24). Held out: AUC 0.77 scar truth; forward 2025 0.68 scar, 0.74 VIIRS;
on 2025 it said 8.9% and 9.6% happened.

Akkshay's choices: test it in replays first (17 Oct 2026; docs/big_fire_replay/README.md), then "rank only, no %"
(18 Oct 2026): on for officials, who see the points and the day's order but never a %. The % read about 2x high on
VIIRS truth in the replay and its scar-truth accuracy was not rechecked. Guards see nothing. FS_BIG_FIRE=0 turns it off.

It is scored on the first VIIRS look at a NEW fire: the alert's earliest VIIRS pass, when no VIIRS point lies within
1.2 km in the 30 h before it (the research linking rule). Later passes and continuing fires get no chance.
Items, as in the research:
  dots in the first look; their span (+ one block) 1 km or more; hottest dot 20 MW or more; any night dot;
  date band (UTC date, days since 15 Feb); division group (many / few big fires 2017-24);
  10+ VIIRS dots within 10 km in the 72 h before; over half farmland within 1 km.
Farmland differs from the research: it used the Roy et al. 60 m vegetation map (class 170) in a 1 km box; here ESA
WorldCover 10 m cropland in a 1 km circle. If WorldCover can't be read, that item is left out and said so.
"""
import csv, json, logging, math, os
from datetime import datetime, timedelta

from . import config, firms

DIR = config.BASE / "data/big_fire"
ON = os.environ.get("FS_BIG_FIRE", "1") == "1"
log = logging.getLogger("big_fire")
LINK_KM, LINK_H, NEAR_KM, NEAR_H = 1.2, 30, 10.0, 72
# Guards are told "may become a big fire" at this many points or more (Akkshay, 18 Oct 2026). In the 2025-26 replay,
# 12+ flagged 3-6 new fires a day statewide; about 1 in 4-5 of them passed 200 ha (VIIRS truth) against 2-4% of all
# new fires, and they held about a quarter of all big fires.
GUARD_POINTS = int(os.environ.get("FS_BIG_FIRE_GUARD_POINTS", "12"))
# officials' order of new fires: "combined" (points + size score from the big-fire watch run, app/big_watch_list.py) or
# "points" (FS_NEWFIRE_ORDER=points). Rank only: the combined value is never shown, like the chance.
ORDER = os.environ.get("FS_NEWFIRE_ORDER", "combined")
HIDDEN = ("chance", "order", "look", "order_night")
_T = {}


def _tables():
    if not _T:
        _T["pts"] = {r["item"]: int(r["points"]) for r in csv.DictReader(open(DIR / "points_table_S200.csv"))}
        _T["div"] = {r["Division"]: (3 if r["group"].startswith("many") else -3 if r["group"].startswith("few") else 0)
                     for r in csv.DictReader(open(DIR / "division_history_groups.csv"))}
        # chance per total: the research read it off a logistic on the total, so its logit is a straight line
        rows = [(int(r["points"]), float(r["chance_said"])) for r in csv.DictReader(open(DIR / "points_chance_S200.csv"))]
        xs, ys = [x for x, _ in rows], [math.log(p / (1 - p)) for _, p in rows]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        _T["ab"] = (my - b * mx, b)
    return _T


def chance(total):
    a, b = _tables()["ab"]
    return 1 / (1 + math.exp(-(a + b * total)))


def _m(a, b):
    return math.hypot((a["lat"] - b["lat"]) * 111320, (a["lon"] - b["lon"]) * 111320 * math.cos(math.radians(a["lat"])))


def score_look(pts, t0, division, near10_3d, crop_share):
    """pts: the first-look VIIRS dots (lat, lon, frp, daynight, scan, track). t0: UTC datetime of the look.
    Returns {points, chance, items: [[label, points]], farmland_checked}."""
    T = _tables()["pts"]
    items = []
    n = len(pts)
    dots = "2 dots" if n == 2 else "3-4 dots" if 3 <= n <= 4 else "5-8 dots" if 5 <= n <= 8 else "9+ dots" if n >= 9 else None
    if dots:
        items.append([f"{n} dots at the first look", T[dots]])
    blk = sum(math.sqrt(max(p["scan"] or 0.375, 0.01) * max(p["track"] or 0.375, 0.01)) * 1000 for p in pts) / n
    span = max((_m(p, q) for p in pts for q in pts), default=0) + blk
    if span >= 1000:
        items.append([f"dots spread over {span / 1000:.1f} km", T["dots spread over 1 km or more"]])
    fmax = max(p["frp"] or 0 for p in pts)
    if fmax >= 20:
        items.append([f"hottest dot {fmax:.0f} MW", T["hottest dot 20 MW or more"]])
    if any(p["daynight"] == "N" for p in pts):
        items.append(["first seen at night", T["first seen at night"]])
    ds = (t0 - datetime(t0.year, 2, 15, tzinfo=t0.tzinfo)).total_seconds() / 86400
    band = ("first seen 15 Mar - 15 Apr" if 28 <= ds < 60 else "first seen 16 Apr - 15 May" if 60 <= ds < 90
            else "first seen after 15 May" if ds >= 90 else None)
    if band:
        items.append([band.replace(" - ", "-"), T[band]])
    dv = _tables()["div"].get(division or "", 0)
    if dv:
        items.append([f"{division.replace('_', ' ')}: division with {'many' if dv > 0 else 'few'} big fires", dv])
    if near10_3d >= 10:
        items.append([f"{near10_3d} VIIRS dots within 10 km in the last 3 days", T["10+ VIIRS dots within 10 km in last 3 days"]])
    if crop_share is not None and crop_share > 0.5:
        items.append([f"mostly farmland around ({crop_share:.0%} within 1 km)", T["mostly farmland around (>50% within 1 km)"]])
    items = [i for i in items if i[1]]
    total = sum(p for _, p in items)
    return {"points": total, "chance": round(chance(total), 3), "items": items, "farmland_checked": crop_share is not None}


_WC = None


_CROP = {}


def _crop(lat, lon):
    global _WC
    k = (round(lat, 3), round(lon, 3))   # ~100 m: neighbouring alerts share one read
    if k in _CROP:
        return _CROP[k]
    try:
        from .landcover import WorldCover
        _WC = _WC or WorldCover()
        _CROP[k] = _WC.crop_share(lat, lon, 1.0)
        if len(_CROP) > 50000:
            _CROP.clear()
        return _CROP[k]
    except Exception:
        return None


_cache = {}


def check(con, inc, now_utc, beats=None, with_chance=False):
    """None (switched off, not an alert, or no VIIRS look yet) or {new_fire, points, items, ..., first_look_utc, note}.
    The % (chance) is left out unless with_chance (replay checks only)."""
    if not ON or (inc["kind"] or "alert") != "alert":
        return None
    key = (str(config.DB_PATH), inc["id"])
    if key not in _cache:
        r = con.execute("SELECT data FROM big_fire_score WHERE incident_id=?", (inc["id"],)).fetchone()
        if r:
            _cache[key] = json.loads(r["data"])
    if key in _cache:
        out = _cache[key]
        if ORDER == "combined" and out.get("new_fire") and out.get("order") is None and out.get("order_night") \
                and con.execute("SELECT 1 FROM size_score WHERE issue_date=? LIMIT 1", (out["order_night"],)).fetchone():
            _size_order(con, out)         # that night's run came after the fire was scored: use it now, and keep it
            if out.get("order") is not None:
                con.execute("INSERT OR REPLACE INTO big_fire_score VALUES (?,?)", (inc["id"], json.dumps(out)))
        return out if with_chance else {k: v for k, v in out.items() if k not in HIDDEN}
    v = [dict(x) for x in con.execute("""SELECT satellite, lat, lon, acq_utc, frp, daynight, scan, track, beat_uid FROM detections
                                         WHERE incident_id=? AND instrument='VIIRS' AND satellite<>'FSI' ORDER BY acq_utc""",
                                      (inc["id"],))]
    if not v:
        return None                       # MODIS- or FSI-only so far (FSI rows carry FIRMS values only once matched)
    t0 = firms.parse_utc(v[0]["acq_utc"])
    if not ((t0.month, t0.day) >= (2, 15) and (t0.month, t0.day) <= (6, 15)):
        return None                       # the table was built on 15 Feb-15 Jun alerts only
    # the first look: every in-beat dot of that pass joined to the alert's first dot by steps of 1.2 km (as in the
    # research, which counted all dots, also the low-confidence and non-forest ones the field task leaves out)
    dl = 6 / 111.32
    cand = [dict(x) for x in con.execute("""SELECT lat, lon, acq_utc, frp, daynight, scan, track, beat_uid FROM detections
                                            WHERE satellite=? AND instrument='VIIRS' AND beat_uid IS NOT NULL AND acq_utc BETWEEN ? AND ?
                                            AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?""",
                                         (v[0]["satellite"], v[0]["acq_utc"], firms.iso(t0 + timedelta(minutes=10)),
                                          v[0]["lat"] - dl, v[0]["lat"] + dl, v[0]["lon"] - dl * 1.1, v[0]["lon"] + dl * 1.1))]
    first, rest = [v[0]], [p for p in cand if (p["lat"], p["lon"]) != (v[0]["lat"], v[0]["lon"])]
    grew = True
    while grew:
        grew = False
        for p in rest[:]:
            if any(_m(p, q) <= LINK_KM * 1000 for q in first):
                first.append(p); rest.remove(p); grew = True
    lat = sum(p["lat"] for p in first) / len(first)
    lon = sum(p["lon"] for p in first) / len(first)
    dl = NEAR_KM / 111.32
    near = con.execute("""SELECT lat, lon, acq_utc FROM detections WHERE instrument='VIIRS' AND satellite<>'FSI'
                          AND beat_uid IS NOT NULL
                          AND acq_utc >= ? AND acq_utc < ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?""",
                       (firms.iso(t0 - timedelta(hours=NEAR_H)), firms.iso(t0 - timedelta(minutes=3)),
                        lat - dl, lat + dl, lon - dl * 1.1, lon + dl * 1.1)).fetchall()
    c = {"lat": lat, "lon": lon}
    lo30 = firms.iso(t0 - timedelta(hours=LINK_H))
    if any(r["acq_utc"] >= lo30 and min(_m(dict(r), p) for p in first) <= LINK_KM * 1000 for r in near):
        out = {"new_fire": False, "first_look_utc": v[0]["acq_utc"],
               "note": "Part of a fire already seen in the last 30 h: points are given only at a new fire's first look."}
    else:
        n10 = sum(1 for r in near if _m(dict(r), c) <= NEAR_KM * 1000)
        beats = beats or _beats()
        divs = [beats.by_uid.get(p["beat_uid"], {}).get("division") for p in first if p["beat_uid"]]
        division = max(set(divs), key=divs.count) if divs else None
        out = {"new_fire": True, "first_look_utc": v[0]["acq_utc"], "division": division,
               **score_look(first, t0, division, n10, _crop(lat, lon))}
        out["guard_flag"] = out["points"] >= GUARD_POINTS     # guards: points only, unchanged
        if ORDER == "combined":
            from . import big_watch_list
            day = (t0 + timedelta(hours=5, minutes=30) - timedelta(days=1)).strftime("%Y-%m-%d")   # the night before
            out["order_night"], out["look"] = day, [[round(p["lat"], 5), round(p["lon"], 5)] for p in first]
            _size_order(con, out)
        out["note"] = ("Big-fire points from the first look: the higher, the more likely this fire grows past 200 ha. "
                       "Use them to order the day's new fires, not as a %.")
    retry = out.get("farmland_checked") is False and now_utc < firms.iso(t0 + timedelta(hours=6))   # WorldCover was down
    if now_utc >= firms.iso(t0 + timedelta(minutes=30)) and not retry:
        _cache[key] = out                 # the first look is complete; nothing later changes it but a late size run
        con.execute("INSERT OR REPLACE INTO big_fire_score VALUES (?,?)", (inc["id"], json.dumps(out)))
    return out if with_chance else {k: v for k, v in out.items() if k not in HIDDEN}


def _size_order(con, out):
    """order from points + the size score of the first-look squares (3 x 3), when that night's run arrived."""
    from . import big_watch_list
    try:
        size = big_watch_list.size_at(con, [tuple(x) for x in out["look"]] or [], out["order_night"]) if out.get("look") else None
    except Exception:             # grid file unreadable, bad row: order by points, never fail the alert
        log.exception("size score for the new-fire order")
        size = None
    out["order"] = big_watch_list.order_value(out["points"], size)
    out["order_basis"] = "points + size score" if out["order"] is not None else "points (no size score that night)"


def score_new(now_utc, beats=None, days=2):
    """Score every alert of the last 2 days whose first look is complete and not yet kept (big_fire_score)."""
    if not ON:
        return 0
    from . import db
    with db.tx() as con:
        rows = con.execute("""SELECT i.* FROM incidents i LEFT JOIN big_fire_score b ON b.incident_id=i.id
                              WHERE b.incident_id IS NULL AND COALESCE(i.kind,'alert')='alert' AND i.first_seen_utc >= ?
                              AND i.first_seen_utc <= ?""",
                           (firms.iso(now_utc - timedelta(days=days)), firms.iso(now_utc - timedelta(minutes=30)))).fetchall()
        for r in rows:
            try:
                check(con, r, firms.iso(now_utc), beats)
            except Exception:
                log.exception("big-fire score for alert %s", r["id"])
            con.commit()      # release the write lock before the next alert's WorldCover read (network, up to 60 s)
    return len(rows)


_B = None


def _beats():
    global _B
    if _B is None:
        from .geo import Beats
        _B = Beats()
    return _B


GUARD_TEXT = "May become a big fire. Go with extra crew if you can, and tell your range officer when you reach it."


def guard_flag(con, inc, now_utc):
    """True when guards should be told this alert may become a big fire (they never see the points)."""
    from .hint import safe
    b = safe(check, con, inc, now_utc)   # the guard's list and card never fail on an officials' hint
    return bool(b and b.get("guard_flag"))


def order_key(con, inc, now_utc):
    """sort key for officials' new fires (lower first): combined order when a size score arrived, else points."""
    b = check(con, inc, now_utc, with_chance=True)
    if not b or not b.get("new_fire"):
        return (2, 0.0)
    if ORDER != "combined":
        return (1, -float(b.get("points") or 0))
    o = b.get("order")
    if o is None:     # no size score for its squares: the same logistic with logit(size) at that night's mean,
        from . import big_watch_list   # so a 20-point fire never sinks below every fire that happened to get a size score
        night = b.get("order_night") or (firms.parse_utc(b["first_look_utc"]) + timedelta(hours=5, minutes=30)
                                         - timedelta(days=1)).strftime("%Y-%m-%d")
        o = big_watch_list.order_value(float(b.get("points") or 0), None, big_watch_list.mean_logit(con, night))
        if o is None:     # no night ever received: every new fire falls back alike, by points
            o = big_watch_list.order_value(float(b.get("points") or 0), None, 0.0)
    return (0, -o)
