"""'Likely control burn' tag for alerts of 15-28 Feb (rule from ratapani/fsi/scouting/code/early_burns/control_burn_rule.py,
note scouting/managed_early_burns.md; held-out test scouting/control_burn_heldout_test.md: about 52% precise, 30-70% by season,
and it also tags about 1 in 10 late-Feb wildfires). Akkshay's choice (16 Oct 2026): a tag on the
officials' dashboard and API only. It never changes an alert's order, due time or what guards see.

An alert is tagged when, on its fire-day (night points before 06:00 IST count for the day before):
  - all its points are daytime, there are at most 2, and the highest FRP is 5 MW or less;
  - no night point lies within 1.5 km that fire-day;
  - no other point lies within 1 km from 2 days before to 3 days after.
Until 3 days have passed the last test is incomplete, so the tag is provisional ("recheck after 3 days").
"""
import hashlib, math
from datetime import timedelta, timezone

from . import config, firms

IST = timezone(timedelta(hours=5, minutes=30))


def _km(a, b):
    return math.hypot((a["lat"] - b["lat"]) * 111.32, (a["lon"] - b["lon"]) * 111.32 * math.cos(math.radians(a["lat"])))


def _night(p, t):
    if p["daynight"] in ("D", "N"):
        return p["daynight"] == "N"
    return not 6 <= t.hour < 18          # FSI points carry no day/night field: use the IST clock


def check(con, inc, now_utc):
    """None (not a 15-28 Feb alert or not tagged) or {likely_control_burn, provisional, recheck_after_utc, note}."""
    if (inc["kind"] or "alert") != "alert":
        return None
    pts = [dict(x) for x in con.execute("SELECT source, lat, lon, acq_utc, frp, daynight FROM detections WHERE incident_id=?", (inc["id"],))]
    if not pts or len(pts) > 2:
        return None
    ts = [firms.parse_utc(p["acq_utc"]).astimezone(IST) for p in pts]
    first = min(ts)
    if first.month != 2 or not 15 <= first.day <= 28:
        return None
    if any(_night(p, t) for p, t in zip(pts, ts)):
        return None
    frp = [p["frp"] for p in pts if p["source"] != "FSI_PORTAL" and p["frp"] is not None]
    if not frp or max(frp) > 5:
        return None                      # FSI portal points carry no FRP (stored as 0): an FSI-only alert is not judged
    day0 = first.replace(hour=6, minute=0, second=0, microsecond=0)
    lo, hi = day0 - timedelta(days=2), day0 + timedelta(days=4)       # 2 days before to 3 days after the fire-day
    dlat = 1.6 / 111.32
    others = con.execute("""SELECT lat, lon, acq_utc, daynight FROM detections WHERE incident_id<>? AND acq_utc BETWEEN ? AND ?
                            AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?""",
                         (inc["id"], firms.iso(lo), firms.iso(hi), pts[0]["lat"] - dlat, pts[0]["lat"] + dlat,
                          pts[0]["lon"] - 2 * dlat, pts[0]["lon"] + 2 * dlat)).fetchall()
    fire_day = (day0, day0 + timedelta(days=1))
    for o in others:
        t = firms.parse_utc(o["acq_utc"]).astimezone(IST)
        d = min(_km(o, p) for p in pts)
        if d <= 1.0:
            return None
        if d <= 1.5 and fire_day[0] <= t < fire_day[1] and _night(o, t):
            return None
    recheck = firms.iso(hi)
    prov = now_utc < recheck
    return {"likely_control_burn": True, "provisional": prov, "recheck_after_utc": recheck if prov else None,
            "note": "Possible control burn: about half of such alerts are; about 1 in 10 late-Feb wildfires also gets this tag" + ("; recheck after 3 days" if prov else "")
                    + ". Shown to officials only; the alert is still sent to guards as usual."}


def cause_check(con, inc, now_utc):
    """Decide once, and store, whether the guard must give the likely cause for this alert (Akkshay, 17 Oct 2026).
    15-28 Feb alerts from config.CAUSE_FROM_YEAR: every tagged alert ('tagged'), plus untagged ones drawn at random so the
    two groups come out about the same size ('random', the comparison group; 'none' = not drawn). The draw uses a hash of
    the alert, with p = tagged so far / untagged so far this season (0.5 before any), stored as cause_p for weighting.
    The tag can still change in its first 3 days; the group is fixed at the first decision and the final tag is in the export.
    Guards see only cause_required, never the group, so they are not told which alerts the rule suspects."""
    if inc["cause_group"] is not None or (inc["kind"] or "alert") != "alert":
        return inc["cause_group"]
    first = firms.parse_utc(inc["first_seen_utc"]).astimezone(IST)
    if first.year < config.CAUSE_FROM_YEAR or first.month != 2 or not 15 <= first.day <= 28:
        return None
    if check(con, inc, now_utc):
        group, p = "tagged", None
    else:
        lo = f"{first.year}-02-14T00:00:00Z"
        n = dict(con.execute("""SELECT cause_group, count(*) FROM incidents WHERE first_seen_utc >= ? AND cause_group IS NOT NULL
                                GROUP BY cause_group""", (lo,)).fetchall())
        untagged = n.get("random", 0) + n.get("none", 0)
        p = min(1.0, n.get("tagged", 0) / untagged) if untagged and n.get("tagged") else 0.5
        u = int(hashlib.sha256(f"cause|{inc['id']}|{inc['first_seen_utc']}|{inc['lat']}|{inc['lon']}".encode()).hexdigest()[:8], 16) / 16 ** 8
        group = "random" if u < p else "none"
    con.execute("UPDATE incidents SET cause_group=?, cause_p=?, cause_required=? WHERE id=?",
                (group, p, int(group != "none"), inc["id"]))
    return group
