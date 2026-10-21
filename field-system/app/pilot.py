"""Forecast-led patrol pilot (research/reframe/pilot/PROTOCOL.md): check tasks for predicted 500 m cells,
chance finds, crew-day log, auto-links from a found fire to recent alerts, and the post-season report.

Task kinds on the incidents table:
  alert     - satellite fire alert (FIRMS / FSI), as before
  predicted - a model-picked 500 m cell to check within its 2-day window
  chance    - a fire staff came across with no task, reported at the phone's position
"""
import csv, json, math, os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from shapely.geometry import Point, shape, mapping, box
from shapely.ops import nearest_points

from . import config, firms
from .geo import haversine_km

IST = timezone(timedelta(hours=5, minutes=30))
FIRE_OUTCOMES = ("active_fire", "burnt_out", "controlled_burn")
LINK_KM, LINK_DAYS = 1.5, 3          # protocol: "near active fire" = a VIIRS point within 1.5 km in the last 3 days
BURN_AGE = {"now": "Burning now", "1_2_days": "Burnt 1-2 days ago", "older": "Older burn"}
CROSSED = ("yes", "no", "unknown")
SUPPRESSION = {"none": "None", "fire_line": "Fire line", "beating": "Beating", "water": "Water", "counter_fire": "Counter-fire"}
# Protocol v2 (research/reframe/pilot/PROTOCOL.md section 0): two streams, scored separately.
#   ignition - predicted-cell tasks; cells with a satellite point within 1.5 km in the 3 days before issue are never sent
#   response - satellite-alert visits, the same in every arm
# The recent-fire ranker runs in shadow mode only: its list is stored (shadow_lists), never sent.
STREAM_OF = {"predicted": "ignition", "alert": "response"}
# Reproducibility record required on every task list.
VERSION_KEYS = ("model_hash", "code_commit", "config_hash", "data_cutoff_utc")
# Protocol v3 (sections 0.2, 0.3, 0.6)
GAP_MIN = 30            # phone positions further apart than this leave the time uncovered ("no_positions")
MOVE_KMH = 1.0          # between two fixes off site: moving at least this fast is travel, slower is idle / waiting
DEDUP_KM, DEDUP_DAYS = 0.5, 2   # field reports this close with no satellite event are one fire
COMPONENTS = ("travel", "on_site", "idle", "no_positions")
CLASSES = ("confirmed_start", "continuation", "older_burn", "unclassifiable")
GROUPINGS = ("no_satellite_event", "same_fire_as_alert", "separate_fire")
# Protocol 0.9 (exploratory, recorded not tested): people met and enforcement on each inspection
ENFORCEMENT = {"none": "None", "warning": "Warning given", "fir_por": "FIR / POR registered"}
CELL_KM2 = 0.25         # beat forest area = its 500 m cells in beat_arms.csv (`cells`) x 0.25 km2, unless forest_km2 is given


# ---------- where a task is ----------
class Place:
    """The spot a visit must reach: satellite points (alert), a 500 m cell (predicted) or a phone fix (chance)."""

    def __init__(self, dets=None, geom=None):
        self.dets = dets or []
        self.geom = geom

    @classmethod
    def of(cls, con, inc):
        dets = [dict(x) for x in con.execute("SELECT lat, lon, instrument FROM detections WHERE incident_id=?", (inc["id"],))]
        geom = shape(json.loads(inc["cell_geom"])) if inc["cell_geom"] else None
        if not dets and geom is None:   # chance find: its own position, judged like a VIIRS point
            dets = [{"lat": inc["lat"], "lon": inc["lon"], "instrument": "VIIRS"}]
        return cls(dets, geom)

    def km(self, lat, lon):
        """Distance in km from the place; 0 anywhere inside a cell."""
        if lat is None or lon is None:
            return None
        if self.geom is not None:
            p = Point(lon, lat)
            if self.geom.contains(p):
                return 0.0
            q = nearest_points(self.geom, p)[0]
            return haversine_km(lat, lon, q.y, q.x)
        return min(haversine_km(lat, lon, d["lat"], d["lon"]) for d in self.dets)

    @property
    def photo_km(self):
        """Photos farther than this are flagged."""
        if self.geom is not None:
            return config.CELL_MARGIN_KM
        return max(config.MAX_PHOTO_KM.get(d["instrument"], 1.0) for d in self.dets)

    @property
    def report_km(self):
        return config.CELL_MARGIN_KM if self.geom is not None else config.REPORT_KM

    def reached(self, lat, lon):
        """Protocol: a cell counts as reached only from inside it; a fire point from within FS_ARRIVE_KM."""
        k = self.km(lat, lon)
        return k is not None and (k == 0.0 if self.geom is not None else k <= config.ARRIVE_KM)


# ---------- grids and arms ----------
@lru_cache(maxsize=1)
def _ratapani_cells():
    try:
        fc = json.load(open(config.RATAPANI_GRID, encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {str(f["properties"]["cell_id"]): f["geometry"] for f in fc["features"]}


@lru_cache(maxsize=1)
def _ratapani_beat():
    """Ratapani cell -> beat by majority area (ratapani/beats/cell_beat.csv), as the model and scoring use."""
    try:
        with open(config.RATAPANI_CELL_BEAT, newline="") as f:
            return {r["cell_id"]: r["beat_uid"] for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=1)
def _mp_grid():
    g = json.load(open(config.MP_GRID, encoding="utf-8"))
    from pyproj import Transformer
    return g, Transformer.from_crs(32643, 4326, always_xy=True)


def cell_polygon(grid, cell_id):
    """GeoJSON polygon of a 500 m cell: 'ratapani' (ratapani/grid_500m.geojson) or 'mp' (ratapani/mp_grid, row * W + col)."""
    if grid == "ratapani":
        g = _ratapani_cells().get(str(int(cell_id)))
        if g is None:
            raise ValueError(f"unknown cell_id {cell_id} for grid ratapani")
        return g
    if grid == "mp":
        g, tr = _mp_grid()
        row, col = divmod(int(cell_id), g["W"])
        x0, y0 = g["X0"] + col * g["S"], g["Y1"] - (row + 1) * g["S"]
        ring = [tr.transform(x, y) for x, y in ((x0, y0), (x0 + g["S"], y0), (x0 + g["S"], y0 + g["S"]), (x0, y0 + g["S"]), (x0, y0))]
        return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring]]}
    raise ValueError("grid must be 'ratapani' or 'mp'")


_arms = {"stamp": None, "map": {}, "block": {}, "km2": {}}


def _load_arms():
    p = config.BEAT_ARMS
    st = os.path.getmtime(p) if os.path.exists(p) else None
    if st != _arms["stamp"]:
        m, b, k = {}, {}, {}
        if st:
            with open(p, newline="") as f:
                for r in csv.DictReader(f):
                    m[r["beat_uid"]] = r["arm"]
                    b[r["beat_uid"]] = r.get("block") or ""
                    k[r["beat_uid"]] = float(r.get("forest_km2") or float(r.get("cells") or 0) * CELL_KM2)
        _arms.update(stamp=st, map=m, block=b, km2=k)
    return _arms


def arms():
    """beat_uid -> arm (fixed / calendar / forecast) from research/reframe/pilot/beat_arms.csv."""
    return _load_arms()["map"]


def forest_km2():
    """beat_uid -> forest area in km2 (protocol 0.9 effort per km2)."""
    return _load_arms()["km2"]


def blocks():
    """beat_uid -> randomisation block (1-32), the `block` column of beat_arms.csv (protocol v3)."""
    return _load_arms()["block"]


def window(issue_date):
    """Protocol due window: issued the evening of day t, valid t+1 06:00 to t+2 19:30 IST."""
    t = datetime.strptime(issue_date, "%Y-%m-%d").replace(tzinfo=IST)
    return t + timedelta(days=1, hours=6), t + timedelta(days=2, hours=19, minutes=30)


def recent_alerts(con, lat, lon, until_utc, geom=None, km=LINK_KM, days=LINK_DAYS, exclude=None):
    """Satellite alerts with a point within km of the spot (or of the cell's edge) in the days before until_utc."""
    lo = firms.iso(firms.parse_utc(until_utc) - timedelta(days=days))
    dlat = km / 111.32 + 0.006
    dlon = dlat / max(math.cos(math.radians(lat)), 0.2)
    place = Place([{"lat": lat, "lon": lon, "instrument": "VIIRS"}], shape(geom) if geom else None)
    out = set()
    for x in con.execute("""SELECT x.incident_id, x.lat, x.lon FROM detections x JOIN incidents i ON i.id = x.incident_id
                            WHERE x.acq_utc >= ? AND x.acq_utc <= ? AND x.lat BETWEEN ? AND ? AND x.lon BETWEEN ? AND ?""",
                         (lo, until_utc, lat - dlat, lat + dlat, lon - dlon, lon + dlon)):
        if x["incident_id"] != exclude and place.km(x["lat"], x["lon"]) <= km:
            out.add(x["incident_id"])
    return sorted(out)


# ---------- predicted-cell tasks ----------
def add_tasks(con, beats, body):
    """Create ignition-stream check tasks for predicted cells. body: issue_date, grid ('ratapani' | 'mp'),
    model_version {model_hash, code_commit, config_hash, data_cutoff_utc, ...}, tasks: [{cell_id, geometry?, beat_uid?,
    arm?, score?, rank?, near_active_fire?}]. Re-sending the same list changes nothing (task_ref).
    Cells near a recent fire are never created (they are the response stream's); they come back in excluded_near_active.
    shadow: true stores the list for scoring after the season (e.g. the recent-fire ranker) and creates no tasks."""
    issue = body["issue_date"]
    ver = dict(body.get("model_version") or {})
    missing = [k for k in VERSION_KEYS if not ver.get(k)]
    if missing:
        raise ValueError(f"model_version needs {list(VERSION_KEYS)}; missing {missing}")
    if body.get("stream", "ignition") != "ignition":
        raise ValueError("only ignition-stream tasks are sent; send other lists with shadow: true")
    if body.get("shadow"):
        name = body.get("list_name") or "shadow"
        con.execute("""INSERT INTO shadow_lists (issue_date, list_name, model_version, cells, received_utc) VALUES (?,?,?,?,?)
                       ON CONFLICT(issue_date, list_name) DO NOTHING""",
                    (issue, name, json.dumps(ver, sort_keys=True), json.dumps(body.get("tasks", [])),
                     firms.iso(datetime.now(timezone.utc))))
        return {"shadow": True, "list_name": name, "cells": len(body.get("tasks", [])), "created": []}
    start, end = window(issue)
    grid = body.get("grid") or "ratapani"
    issued_utc = body.get("issued_utc") or firms.iso(datetime.strptime(issue, "%Y-%m-%d").replace(hour=18, tzinfo=IST))
    made, skipped, excluded, errors = [], 0, [], []
    for t in body.get("tasks", []):
        try:
            cid = str(t["cell_id"])
            ref = t.get("task_ref") or f"{issue}:{grid}:{cid}"
            if con.execute("SELECT 1 FROM incidents WHERE task_ref=?", (ref,)).fetchone():
                skipped += 1
                continue
            g = t.get("geometry") or cell_polygon(grid, cid)
            c = shape(g).centroid
            uid = (t.get("beat_uid") or (grid == "ratapani" and _ratapani_beat().get(cid))
                   or beats.locate(c.y, c.x) or next(iter(beats.touching(c.y, c.x, 0.36)), None))
            if not uid:
                raise ValueError("cell is outside every beat")
            arm = t.get("arm") or arms().get(uid)
            # Decided at issue time and never recomputed (protocol section 4).
            naf = t.get("near_active_fire")
            if naf is None:
                naf = bool(recent_alerts(con, c.y, c.x, issued_utc, geom=g))
            if naf:
                excluded.append(t["cell_id"])
                continue
            cur = con.execute(
                """INSERT INTO incidents (kind, task_ref, stream, beat_uid, lat, lon, first_seen_utc, last_seen_utc, n_detections,
                   sensors, due_utc, due_from_utc, issue_date, cell_id, cell_geom, arm, model_hash, model_version,
                   near_active_fire, score) VALUES ('predicted',?,'ignition',?,?,?,?,?,0,'MODEL',?,?,?,?,?,?,?,?,0,?)""",
                (ref, uid, round(c.y, 6), round(c.x, 6), issued_utc, issued_utc, firms.iso(end), firms.iso(start), issue,
                 f"{grid}:{cid}", json.dumps(g), arm, ver["model_hash"], json.dumps(ver, sort_keys=True),
                 None if t.get("score") is None else float(t["score"])))   # a number, never text (rendered in the control room)
            con.execute("INSERT OR IGNORE INTO incident_beats VALUES (?,?)", (cur.lastrowid, uid))
            made.append(cur.lastrowid)
        except Exception as e:
            errors.append({"cell_id": t.get("cell_id"), "error": str(e)[:200]})
    return {"created": made, "already_there": skipped, "excluded_near_active": excluded, "errors": errors,
            "valid_from_utc": firms.iso(start), "due_utc": firms.iso(end)}


def inspection(con, inc, staff_id, photo_pts, until_utc):
    """Protocol v2: an inspection is completed only by a report with at least 2 geotagged, timestamped photos inside
    the cell, at least FS_INSPECT_SPREAD_M apart (and not taken before the window opened). Otherwise 'arrived' (the
    phone was inside the cell) or 'not_shown'. Arrivals are counted apart and are not credited as checks."""
    place = Place(geom=shape(json.loads(inc["cell_geom"])))
    lo = inc["due_from_utc"]
    inside = [(p["lat"], p["lon"]) for p in photo_pts
              if p["lat"] is not None and p["utc"] and p["utc"] >= lo and place.km(p["lat"], p["lon"]) == 0]
    spread = max((haversine_km(*a, *b) for k, a in enumerate(inside) for b in inside[k + 1:]), default=0) * 1000
    if len(inside) >= 2 and spread >= config.INSPECT_SPREAD_M:
        return "completed", round(spread)
    pos = con.execute("""SELECT lat, lon FROM positions WHERE staff_id=? AND utc BETWEEN ? AND ?""",
                      (staff_id, lo, until_utc)).fetchall()
    if inside or inc["arrived_utc"] or any(place.km(r["lat"], r["lon"]) == 0 for r in pos):
        return "arrived", round(spread)
    return "not_shown", 0


# ---------- chance finds ----------
def add_chance(con, beats, staff, lat, lon, ts):
    """A fire found with no task: a 'chance' incident at the phone's position, in the beat it falls in."""
    uid = beats.locate(lat, lon) or staff.get("beat_uid") or ""
    cur = con.execute(
        """INSERT INTO incidents (kind, beat_uid, lat, lon, first_seen_utc, last_seen_utc, n_detections, sensors, due_utc,
           arrived_utc, arrived_by, arm) VALUES ('chance',?,?,?,?,?,0,'FIELD',?,?,?,?)""",
        (uid, lat, lon, ts, ts, ts, ts, staff["id"], arms().get(uid)))
    if uid:
        con.execute("INSERT OR IGNORE INTO incident_beats VALUES (?,?)", (cur.lastrowid, uid))
    return con.execute("SELECT * FROM incidents WHERE id=?", (cur.lastrowid,)).fetchone()


# ---------- crew-day log ----------
def shift_start(con, staff_id, f, ts):
    open_ = con.execute("SELECT id FROM shifts WHERE staff_id=? AND end_utc IS NULL", (staff_id,)).fetchone()
    if open_:   # forgot to end yesterday: close it at the last phone position, marked as auto-closed
        shift_end(con, staff_id, {}, None, auto=True)
    # Person-hours = shift length x crew size, so one phone logs the crew. A member who logs a shift of their own
    # enters crew size 1; the shakedown report flags overlapping crews in one beat.
    cur = con.execute("""INSERT INTO shifts (staff_id, start_utc, crew_size, start_lat, start_lon, device_id, notes, crew_logged)
                         VALUES (?,?,?,?,?,?,?,?)""",
                      (staff_id, f.get("start_utc") or ts, max(1, int(f.get("crew_size") or 1)), f.get("lat"), f.get("lon"),
                       f.get("device_id"), f.get("notes"), int(bool(f.get("crew_size")))))
    return dict(con.execute("SELECT * FROM shifts WHERE id=?", (cur.lastrowid,)).fetchone())


def shift_end(con, staff_id, f, ts, auto=False):
    s = con.execute("SELECT * FROM shifts WHERE staff_id=? AND end_utc IS NULL ORDER BY id DESC LIMIT 1", (staff_id,)).fetchone()
    if not s:
        return None
    if auto:   # last position seen during the shift, else start + 8 h
        p = con.execute("SELECT max(utc) FROM positions WHERE staff_id=? AND utc >= ?", (staff_id, s["start_utc"])).fetchone()[0]
        ts = p or firms.iso(firms.parse_utc(s["start_utc"]) + timedelta(hours=8))
    con.execute("""UPDATE shifts SET end_utc=?, end_lat=?, end_lon=?, crew_size=coalesce(?, crew_size), auto_closed=?,
                   crew_logged=max(crew_logged, ?) WHERE id=?""",
                (f.get("end_utc") or ts, f.get("lat"), f.get("lon"), f.get("crew_size"), int(auto), int(bool(f.get("crew_size"))), s["id"]))
    refresh_sites(con, staff_id, s["start_utc"], f.get("end_utc") or ts)
    return dict(con.execute("SELECT * FROM shifts WHERE id=?", (s["id"],)).fetchone())


def shift_hours(s, now_utc):
    end = s["end_utc"] or now_utc
    return max(0.0, (firms.parse_utc(end) - firms.parse_utc(s["start_utc"])).total_seconds() / 3600)


# ---------- time on site (protocol v3 section 0.3) ----------
def _t(s):
    return firms.parse_utc(s)


def site_times(con, rep, inc):
    """Cell (or fire-point) entry and exit for one report: the run of the reporter's phone positions on site, with no
    gap over GAP_MIN, that contains the visit time or ends / starts within GAP_MIN of it. (None, None) if no fix on site."""
    v = rep["visited_utc"] or rep["submitted_utc"]
    lo, hi = firms.iso(_t(v) - timedelta(hours=12)), firms.iso(_t(v) + timedelta(hours=12))
    place = Place.of(con, inc)
    pts = con.execute("SELECT utc, lat, lon FROM positions WHERE staff_id=? AND utc BETWEEN ? AND ? ORDER BY utc",
                      (rep["staff_id"], lo, hi)).fetchall()
    runs, cur, prev = [], None, None
    for p in pts:
        on = place.reached(p["lat"], p["lon"])
        gap = prev is not None and (_t(p["utc"]) - _t(prev)).total_seconds() > GAP_MIN * 60
        if on and cur and not gap:
            cur[1] = p["utc"]
        elif on:
            cur = [p["utc"], p["utc"]]
            runs.append(cur)
        else:
            cur = None
        prev = p["utc"]
    tv, near = _t(v), timedelta(minutes=GAP_MIN)
    best = None
    for r0, r1 in runs:
        if _t(r0) - near <= tv <= _t(r1) + near:
            d = 0 if r0 <= v <= r1 else min(abs((_t(r0) - tv).total_seconds()), abs((_t(r1) - tv).total_seconds()))
            if best is None or d < best[0]:
                best = (d, r0, r1)
    return (best[1], best[2]) if best else (None, None)


def refresh_sites(con, staff_id, t0, t1):
    """Recompute stored entry / exit for a staff member's task reports between t0 and t1 (positions can arrive late
    from a phone's offline queue, so this runs on new positions, at shift end and before the season report)."""
    lo, hi = firms.iso(_t(t0) - timedelta(hours=12)), firms.iso(_t(t1) + timedelta(hours=12))
    for r in con.execute("""SELECT r.*, i.id AS i_id FROM reports r JOIN incidents i ON i.id=r.incident_id
                            WHERE r.staff_id=? AND r.stream IS NOT NULL AND coalesce(r.visited_utc, r.submitted_utc) BETWEEN ? AND ?""",
                         (staff_id, lo, hi)).fetchall():
        inc = con.execute("SELECT * FROM incidents WHERE id=?", (r["i_id"],)).fetchone()
        e0, e1 = site_times(con, r, inc)
        if (e0, e1) != (r["site_entry_utc"], r["site_exit_utc"]):
            con.execute("UPDATE reports SET site_entry_utc=?, site_exit_utc=? WHERE id=?", (e0, e1, r["id"]))


# ---------- person-hours (protocol v3 section 0.3) ----------
def _gap_pieces(g0, g1, pos):
    """Split an off-site stretch into travel / idle / no_positions from the phone fixes in it."""
    if g1 <= g0:
        return []
    lim = timedelta(minutes=GAP_MIN)
    before = next((p for p in reversed(pos) if p[0] <= g0), None)
    after = next((p for p in pos if p[0] >= g1), None)
    seq = [(g0, before[1:] if before and g0 - before[0] <= lim else None)]
    seq += [(p[0], p[1:]) for p in pos if g0 < p[0] < g1]
    seq.append((g1, after[1:] if after and after[0] - g1 <= lim else None))
    out = []
    for (ta, la), (tb, lb) in zip(seq, seq[1:]):
        dt = (tb - ta).total_seconds()
        if dt <= 0:
            continue
        if dt > GAP_MIN * 60:
            c = "no_positions"
        elif la is None or lb is None:
            c = "idle"
        else:
            c = "travel" if haversine_km(*la, *lb) / (dt / 3600) >= MOVE_KMH else "idle"
        out.append((ta, tb, c))
    return out


def shift_timeline(con, sh, now_utc):
    """One logged shift as (start, end, stream, component) pieces. Time on site goes to the task's stream; travel and
    waiting go to the stream of the next task reached; the trip back to the last task's stream; a shift with no task
    report is all 'unassigned'. Chance finds don't split a shift. Returns pieces and the share covered by positions."""
    S, E = _t(sh["start_utc"]), _t(sh["end_utc"] or now_utc)
    pos = [(_t(p["utc"]), p["lat"], p["lon"]) for p in con.execute(
        "SELECT utc, lat, lon FROM positions WHERE staff_id=? AND utc BETWEEN ? AND ? ORDER BY utc",
        (sh["staff_id"], firms.iso(S - timedelta(minutes=GAP_MIN)), firms.iso(E + timedelta(minutes=GAP_MIN))))]
    sites = []
    for r in con.execute("""SELECT coalesce(visited_utc, submitted_utc) AS t, stream, site_entry_utc, site_exit_utc FROM reports
                            WHERE staff_id=? AND stream IS NOT NULL AND coalesce(visited_utc, submitted_utc) BETWEEN ? AND ?
                            ORDER BY t""", (sh["staff_id"], sh["start_utc"], firms.iso(E))):
        a = _t(r["site_entry_utc"]) if r["site_entry_utc"] else _t(r["t"])
        b = _t(r["site_exit_utc"]) if r["site_exit_utc"] else a
        a, b = max(S, min(a, E)), max(S, min(b, E))
        sites.append([a, max(a, b), r["stream"]])
    sites.sort(key=lambda s: s[0])
    for k in range(1, len(sites)):                    # overlapping visits: the earlier one keeps the time
        sites[k][0] = max(sites[k][0], sites[k - 1][1])
        sites[k][1] = max(sites[k][1], sites[k][0])
    pieces, cur = [], S
    for k, (a, b, st) in enumerate(sites):
        pieces += [(x, y, st, c) for x, y, c in _gap_pieces(cur, a, pos)]   # travel to this task
        if b > a:
            pieces.append((a, b, st, "on_site"))
        cur = max(cur, b)
    tail = sites[-1][2] if sites else "unassigned"
    pieces += [(x, y, tail, c) for x, y, c in _gap_pieces(cur, E, pos)]
    ts = [S] + [p[0] for p in pos if S < p[0] < E] + [E]
    dur = (E - S).total_seconds()
    covered = sum(d for d in ((b - a).total_seconds() for a, b in zip(ts, ts[1:])) if d <= GAP_MIN * 60)
    return pieces, (covered / dur if dur > 0 else 1.0)


def person_hours(con, s0, s1, now_utc):
    """Person-hours per (beat of the staff member, stream, component), plus per-shift log quality for the shakedown.
    Person-hours = shift length x crew size (one phone logs the crew)."""
    staff_beat = {r["id"]: r["beat_uid"] for r in con.execute("SELECT id, beat_uid FROM staff")}
    out, shifts = {}, []
    for sh in con.execute("SELECT * FROM shifts WHERE start_utc BETWEEN ? AND ?", (s0, s1)).fetchall():
        pieces, cov = shift_timeline(con, sh, now_utc)
        crew, beat = sh["crew_size"] or 1, staff_beat.get(sh["staff_id"])
        un = 0.0
        for a, b, st, c in pieces:
            h = (b - a).total_seconds() / 3600 * crew
            out[(beat, st, c)] = out.get((beat, st, c), 0.0) + h
            un += h if st == "unassigned" else 0
        total = shift_hours(sh, now_utc) * crew
        shifts.append({"shift_id": sh["id"], "staff_id": sh["staff_id"], "beat_uid": beat, "start_utc": sh["start_utc"],
                       "end_utc": sh["end_utc"], "crew_size": crew, "person_hours": total, "unassigned_hours": un,
                       "coverage": cov, "complete": bool(sh["end_utc"] and not sh["auto_closed"] and sh["crew_logged"])})
    return out, shifts


def stream_hours(con, s0, s1, now_utc):
    """Person-hours per (beat, stream), components summed."""
    out = {}
    for (beat, st, _), h in person_hours(con, s0, s1, now_utc)[0].items():
        out[(beat, st)] = out.get((beat, st), 0.0) + h
    return out


def shakedown(con, start, end, now_utc):
    """Launch gate (protocol v3 section 0.3), per arm: shifts with start, end and crew size >= 95%; on-duty time
    covered by phone positions with gaps under 30 min >= 90%; unassigned person-hours <= 5%."""
    A = arms()
    s0, s1 = f"{start}T00:00:00Z", f"{end}T23:59:59Z"
    _, shifts = person_hours(con, s0, s1, now_utc)
    by = {a: [] for a in sorted(set(A.values()))}
    for s in shifts:
        if A.get(s["beat_uid"]) in by:
            by[A[s["beat_uid"]]].append(s)
    # Two people in one beat on overlapping shifts, at least one logging a crew > 1: the same people may be counted twice.
    overlaps = []
    for k, x in enumerate(shifts):
        for y in shifts[k + 1:]:
            if (x["beat_uid"] == y["beat_uid"] and x["staff_id"] != y["staff_id"] and max(x["crew_size"], y["crew_size"]) > 1
                    and x["start_utc"] < (y["end_utc"] or now_utc) and y["start_utc"] < (x["end_utc"] or now_utc)):
                overlaps.append({"beat_uid": x["beat_uid"], "shifts": [x["shift_id"], y["shift_id"]]})
    out = {}
    for a, ss in by.items():
        ph = sum(s["person_hours"] for s in ss)
        dur = sum(s["person_hours"] / s["crew_size"] for s in ss)
        m = {"shifts": len(ss), "beats_logging": len({s["beat_uid"] for s in ss}), "beats": sum(1 for v in A.values() if v == a),
             "person_hours": round(ph, 1),
             "complete_share": round(sum(s["complete"] for s in ss) / len(ss), 3) if ss else None,
             "position_coverage_share": round(sum(s["coverage"] * s["person_hours"] / s["crew_size"] for s in ss) / dur, 3) if dur else None,
             "unassigned_share": round(sum(s["unassigned_hours"] for s in ss) / ph, 3) if ph else None}
        m["pass"] = {"complete": m["complete_share"] is not None and m["complete_share"] >= 0.95,
                     "coverage": m["position_coverage_share"] is not None and m["position_coverage_share"] >= 0.90,
                     "unassigned": m["unassigned_share"] is not None and m["unassigned_share"] <= 0.05}
        m["gate_passed"] = all(m["pass"].values())
        out[a] = m
    return {"start": start, "end": end, "arms": out, "gate_passed": bool(out) and all(m["gate_passed"] for m in out.values()),
            "possible_double_count": overlaps,
            "shifts_incomplete": [{k: s[k] for k in ("shift_id", "staff_id", "beat_uid", "start_utc", "end_utc", "crew_size")}
                                  for s in shifts if not s["complete"]][:500],
            "notes": ["Complete = ended by the user (not auto-closed) and crew size entered.",
                      f"Coverage = on-duty time between phone fixes no more than {GAP_MIN} min apart, weighted by shift length.",
                      "Unassigned = shifts with no task report, as a share of person-hours."]}


# ---------- unique fires (protocol v3 section 0.2) ----------
def _rep_point(r):
    if r["device_lat"] is not None:
        return r["device_lat"], r["device_lon"]
    return r["i_lat"], r["i_lon"]


def assign_fire(con, rid):
    """Give a fire report its fire_id (provisional until the post-season grouping). A fire on or next to a satellite
    event takes that event's id (S + the earliest alert); otherwise reports within 500 m and 2 days are one fire (F + id)."""
    r = con.execute("""SELECT r.*, i.kind, i.lat AS i_lat, i.lon AS i_lon FROM reports r JOIN incidents i ON i.id=r.incident_id
                       WHERE r.id=?""", (rid,)).fetchone()
    sat = json.loads(r["linked_alerts"] or "[]") + ([r["incident_id"]] if (r["kind"] or "alert") == "alert" else [])
    lat, lon = _rep_point(r)
    v = r["visited_utc"] or r["submitted_utc"]
    fid = None
    if sat:
        fid = f"S{min(sat)}"
    else:
        lo, hi = firms.iso(_t(v) - timedelta(days=DEDUP_DAYS)), firms.iso(_t(v) + timedelta(days=DEDUP_DAYS))
        for x in con.execute("""SELECT r.fire_id, r.device_lat, r.device_lon, i.lat AS i_lat, i.lon AS i_lon
                                FROM reports r JOIN incidents i ON i.id=r.incident_id JOIN fires f ON f.fire_id=r.fire_id
                                WHERE r.fire_id LIKE 'F%' AND f.merged_into IS NULL AND r.id<>?
                                AND coalesce(r.visited_utc, r.submitted_utc) BETWEEN ? AND ?
                                ORDER BY coalesce(r.visited_utc, r.submitted_utc)""", (rid, lo, hi)):
            if haversine_km(lat, lon, *_rep_point(x)) <= DEDUP_KM:
                fid = x["fire_id"]
                break
        fid = fid or f"F{rid}"
    con.execute("INSERT OR IGNORE INTO fires (fire_id, created_utc, lat, lon) VALUES (?,?,?,?)", (fid, v, lat, lon))
    con.execute("UPDATE reports SET fire_id=? WHERE id=?", (fid, rid))
    refresh_fire(con, fid)
    return fid


def _verdict(con, fid):
    """Two reviewers; a third settles a split. Returns (class or None while pending, reason)."""
    vs = con.execute("SELECT verdict, reason FROM fire_verdicts WHERE fire_id=? ORDER BY id", (fid,)).fetchall()
    if len(vs) < 2:
        return None, None
    if vs[0]["verdict"] == vs[1]["verdict"]:
        return vs[0]["verdict"], f"2 of 2 reviewers: {vs[0]['reason']} | {vs[1]['reason']}"
    if len(vs) < 3:
        return None, "split: waiting for a third reviewer"
    c = [x["verdict"] for x in vs[:3]]
    top = max(set(c), key=c.count)
    if c.count(top) < 2:
        return "unclassifiable", "3 reviewers, 3 different verdicts"
    return top, "2 of 3 reviewers: " + " | ".join(x["reason"] for x in vs[:3] if x["verdict"] == top)


def refresh_fire(con, fid):
    """Credit the fire to its first completed inspection (ignition) or first visit / chance find (other streams) and
    classify it by the table in protocol v3 section 0.2. Rows 2 and 3 (field and satellite disagree) go to review."""
    f = con.execute("SELECT * FROM fires WHERE fire_id=?", (fid,)).fetchone()
    reps = con.execute("""SELECT r.*, i.kind, i.first_seen_utc AS i_first FROM reports r JOIN incidents i ON i.id=r.incident_id
                          WHERE r.fire_id=? AND r.outcome IN (?,?,?) ORDER BY coalesce(r.visited_utc, r.submitted_utc), r.id""",
                       (fid,) + FIRE_OUTCOMES).fetchall()
    cred = next((r for r in reps if (r["kind"] or "alert") != "predicted" or r["inspection"] == "completed"), None)
    cls, queue, why, disc, stream = None, 0, None, None, None
    if cred:
        disc = cred["visited_utc"] or cred["submitted_utc"]
        stream = STREAM_OF.get(cred["kind"] or "alert", "chance")
        linked = bool(json.loads(cred["linked_alerts"] or "[]"))
        first = f["fire_first_utc"]
        if not f["grouping_utc"] and fid.startswith("S"):   # provisional: the satellite event's first detection
            first = (con.execute("SELECT first_seen_utc FROM incidents WHERE id=?", (int(fid[1:]),)).fetchone() or [None])[0]
        older = bool(first) and _t(disc) - _t(first) > timedelta(days=2)
        if cred["evidence"] == "none" or not cred["burn_age"]:
            cls = "unclassifiable"
        elif cred["burn_age"] == "older":
            cls = "older_burn"
        elif not linked:
            if older and f["grouping"] != "no_satellite_event":
                cls, queue, why = "continuation", 1, "field says fresh; satellite fire first seen more than 2 days earlier"
            else:
                cls = "confirmed_start"
        elif f["grouping"] == "separate_fire":
            cls, queue, why = "confirmed_start", 1, "field says fresh; grouping says a separate fire next to a recent alert"
        else:
            cls = "continuation"
    if (f["queue_reason"] or "").startswith("manual"):
        queue, why = 1, f["queue_reason"]
    final, reason = (cls, None)
    if queue:
        final, reason = _verdict(con, fid)
    con.execute("""UPDATE fires SET credited_report_id=?, discovered_utc=?, credited_stream=?, class_auto=?, queued=?,
                   queue_reason=?, class_final=?, final_reason=? WHERE fire_id=?""",
                (cred and cred["id"], disc, stream, cls, queue, why, final, reason, fid))


def import_grouping(con, rows, now_utc):
    """Post-season grouping from the FSI thread's locked code: [{fire_id, grouping, fire_first_utc?, est_ignition_utc?,
    merge_into?, chips?: [{label, url}]}]. merge_into joins two provisional fires (the reports move to the target)."""
    done, errors = 0, []
    for g in rows:
        fid = g.get("fire_id")
        if not con.execute("SELECT 1 FROM fires WHERE fire_id=?", (fid,)).fetchone():
            errors.append({"fire_id": fid, "error": "unknown fire_id"})
            continue
        if g.get("grouping") and g["grouping"] not in GROUPINGS:
            errors.append({"fire_id": fid, "error": f"grouping must be one of {list(GROUPINGS)}"})
            continue
        tgt = g.get("merge_into")
        if tgt:
            if not con.execute("SELECT 1 FROM fires WHERE fire_id=?", (tgt,)).fetchone():
                errors.append({"fire_id": fid, "error": "unknown merge_into"})
                continue
            con.execute("UPDATE reports SET fire_id=? WHERE fire_id=?", (tgt, fid))
            con.execute("UPDATE fires SET merged_into=?, queued=0, class_final=NULL WHERE fire_id=?", (tgt, fid))
            refresh_fire(con, tgt)
            done += 1
            continue
        con.execute("""UPDATE fires SET grouping=coalesce(?, grouping), fire_first_utc=coalesce(?, fire_first_utc),
                       est_ignition_utc=coalesce(?, est_ignition_utc), chips=coalesce(?, chips), grouping_utc=? WHERE fire_id=?""",
                    (g.get("grouping"), g.get("fire_first_utc"), g.get("est_ignition_utc"),
                     json.dumps(g["chips"]) if g.get("chips") else None, now_utc, fid))
        refresh_fire(con, fid)
        done += 1
    return {"updated": done, "errors": errors}


def add_verdict(con, fid, reviewer_id, verdict, reason, now_utc):
    if verdict not in CLASSES:
        raise ValueError(f"verdict must be one of {list(CLASSES)}")
    if not (reason or "").strip():
        raise ValueError("a reason is required")
    f = con.execute("SELECT queued FROM fires WHERE fire_id=? AND merged_into IS NULL", (fid,)).fetchone()
    if not f or not f["queued"]:
        raise ValueError("this fire is not in the review queue")
    n = con.execute("SELECT count(*) FROM fire_verdicts WHERE fire_id=?", (fid,)).fetchone()[0]
    done = _verdict(con, fid)[0]
    if done:
        raise ValueError("this fire is already decided")
    if n >= 2 and con.execute("SELECT 1 FROM fire_verdicts WHERE fire_id=? AND reviewer_id=?", (fid, reviewer_id)).fetchone():
        raise ValueError("verdicts are locked once two reviewers have answered; a third reviewer settles a split")
    con.execute("""INSERT INTO fire_verdicts (fire_id, reviewer_id, verdict, reason, utc) VALUES (?,?,?,?,?)
                   ON CONFLICT(fire_id, reviewer_id) DO UPDATE SET verdict=excluded.verdict, reason=excluded.reason, utc=excluded.utc""",
                (fid, reviewer_id, verdict, reason.strip(), now_utc))
    refresh_fire(con, fid)
    return dict(con.execute("SELECT fire_id, class_final, final_reason FROM fires WHERE fire_id=?", (fid,)).fetchone()) | {
        "verdicts": con.execute("SELECT count(*) FROM fire_verdicts WHERE fire_id=?", (fid,)).fetchone()[0]}


def review_queue(con, reviewer_id, scars=None):
    """Blind cases: no arm, beat, task source or other reviewers' verdicts. Photos, phone times, burn age, nearby alerts,
    the satellite fire's first detection, the burn scar for those alerts and any before/after chips."""
    out = []
    for f in con.execute("SELECT * FROM fires WHERE queued=1 AND merged_into IS NULL ORDER BY fire_id").fetchall():
        if _verdict(con, f["fire_id"])[0]:
            continue
        mine = con.execute("SELECT verdict, reason FROM fire_verdicts WHERE fire_id=? AND reviewer_id=?",
                           (f["fire_id"], reviewer_id)).fetchone()
        nv = con.execute("SELECT count(*) FROM fire_verdicts WHERE fire_id=?", (f["fire_id"],)).fetchone()[0]
        reps, sat = [], set()
        for r in con.execute("""SELECT * FROM reports WHERE fire_id=? ORDER BY coalesce(visited_utc, submitted_utc)""", (f["fire_id"],)):
            sat.update(json.loads(r["linked_alerts"] or "[]"))
            reps.append({"visited_utc": r["visited_utc"], "submitted_utc": r["submitted_utc"], "outcome": r["outcome"],
                         "burn_age": r["burn_age"], "lat": r["device_lat"], "lon": r["device_lon"], "evidence": r["evidence"],
                         "photos": [{"id": p["id"], "taken_utc": p["taken_utc"], "dev_utc": p["dev_utc"],
                                     "lat": p["exif_lat"] if p["exif_lat"] is not None else p["dev_lat"],
                                     "lon": p["exif_lon"] if p["exif_lon"] is not None else p["dev_lon"]}
                                    for p in con.execute("SELECT * FROM photos WHERE report_id=?", (r["id"],))]})
        if f["fire_id"].startswith("S"):
            sat.add(int(f["fire_id"][1:]))
        alerts = []
        for iid in sorted(sat):
            pts = [dict(x) for x in con.execute("SELECT lat, lon, acq_utc, instrument, satellite FROM detections WHERE incident_id=?", (iid,))]
            sc = scars.for_points(pts, with_geometry=True) if scars and pts else None
            alerts.append({"points": pts, "scar": sc})
        out.append({"case": f["fire_id"], "lat": f["lat"], "lon": f["lon"], "discovered_utc": f["discovered_utc"],
                    "satellite_fire_first_utc": f["fire_first_utc"], "grouping": f["grouping"], "question": f["queue_reason"],
                    "chips": json.loads(f["chips"] or "[]"), "reports": reps, "nearby_alerts": alerts,
                    "verdicts_in": nv, "needs": "your verdict" if not mine else "other reviewers",   # never tells a voter the others disagreed
                    "my_verdict": dict(mine) if mine else None})
    return out


# ---------- post-season report ----------
def _boot_ratio(per_beat, arm, ref, n=2000, seed=20261015):
    """Rate ratio (fires per ignition-hour, arm vs ref) with a 95% bootstrap over beats within each arm."""
    import numpy as np
    a, b = np.array(per_beat.get(arm, []), float).reshape(-1, 2), np.array(per_beat.get(ref, []), float).reshape(-1, 2)
    if not len(a) or not len(b) or a[:, 1].sum() == 0 or b[:, 1].sum() == 0 or b[:, 0].sum() == 0:
        return None
    est = (a[:, 0].sum() / a[:, 1].sum()) / (b[:, 0].sum() / b[:, 1].sum())
    rng, vals = np.random.default_rng(seed), []
    for _ in range(n):
        x, y = a[rng.integers(0, len(a), len(a))], b[rng.integers(0, len(b), len(b))]
        if x[:, 1].sum() and y[:, 1].sum() and y[:, 0].sum():
            vals.append((x[:, 0].sum() / x[:, 1].sum()) / (y[:, 0].sum() / y[:, 1].sum()))
    lo, hi = np.percentile(vals, [2.5, 97.5]) if vals else (None, None)
    return {"ratio": round(float(est), 2), "ci95": [round(float(lo), 2), round(float(hi), 2)] if vals else None}


def report(con, beats, start, end, now_utc, scars=None):
    """Season report per arm (protocol v3). Primary: unique confirmed starts credited to completed ignition-stream
    inspections and accepted by the range officer, per 100 ignition-stream person-hours. Fires are the unique fires of section 0.2 (fires table),
    classified by its table and, where field and satellite disagree, by the blind review. Where first-day fires were
    found: (a) ignition, (b) response, (c) chance, (d) total. The rate ratio here is a quick look (beat bootstrap);
    the locked analysis (block randomisation) runs on the per-beat CSV. The v2 counts are kept under ignition / response."""
    A = arms()
    s0, s1 = f"{start}T00:00:00Z", f"{end}T23:59:59Z"
    for st in con.execute("SELECT DISTINCT staff_id FROM shifts WHERE start_utc BETWEEN ? AND ?", (s0, s1)).fetchall():
        refresh_sites(con, st[0], s0, s1)     # positions that arrived after the report
    out = {a: {"beats": 0, "staff_hours": {"ignition": 0.0, "response": 0.0, "unassigned": 0.0},
               "ignition": {"tasks": 0, "inspected": 0, "inspected_in_window": 0, "arrived_not_inspected": 0, "not_shown": 0,
                            "not_reported": 0, "nothing_found": 0, "fires_found": 0, "fires_verified": 0,
                            "fires_verified_no_recent_viirs": 0, "fires_new": 0},
               "response": {"alerts": 0, "visited_2d": 0, "pending": 0, "missed": 0, "missed_with_scar": 0, "fires_found": 0},
               "chance_finds": 0, "chance_no_recent_viirs": 0, "chance_near_recent_viirs": 0,
               "spillover": [], "fires_crossing_beats": 0, "fires_suppressed": 0} for a in sorted(set(A.values()))}
    for a in A.values():
        out[a]["beats"] += 1
    per_beat_n = {}
    missed = []
    dose = {a: {"inspections": 0, "on_site_min": [], "people_met": 0, "warnings": 0, "fir_por": 0} for a in out}
    for d in con.execute("""SELECT i.arm, i.beat_uid, r.site_entry_utc, r.site_exit_utc, r.people_met, r.enforcement FROM reports r
                            JOIN incidents i ON i.id=r.incident_id WHERE i.kind='predicted' AND r.inspection='completed'
                            AND i.first_seen_utc BETWEEN ? AND ?""", (s0, s1)):
        a = d["arm"] or A.get(d["beat_uid"])
        if a in dose:
            x = dose[a]
            x["inspections"] += 1
            if d["site_entry_utc"] and d["site_exit_utc"]:
                x["on_site_min"].append((_t(d["site_exit_utc"]) - _t(d["site_entry_utc"])).total_seconds() / 60)
            x["people_met"] += d["people_met"] or 0
            x["warnings"] += d["enforcement"] == "warning"
            x["fir_por"] += d["enforcement"] == "fir_por"
    rows = con.execute("""SELECT i.*, r.outcome AS r_outcome, r.linked_alerts, r.visited_utc AS r_visited, r.inspection,
                          r.evidence, r.burn_age, r.crosses_beat_boundary, r.beats_touched, r.suppression, r.suppression_utc
                          FROM incidents i LEFT JOIN reports r ON r.id = (SELECT max(id) FROM reports WHERE incident_id=i.id)
                          WHERE i.first_seen_utc BETWEEN ? AND ?""", (s0, s1)).fetchall()
    for r in rows:
        arm = r["arm"] or A.get(r["beat_uid"])
        if arm not in out:
            continue
        o = out[arm]
        kind = r["kind"] or "alert"
        fire = r["r_outcome"] in FIRE_OUTCOMES
        linked = bool(json.loads(r["linked_alerts"] or "[]"))
        if fire:
            o["fires_crossing_beats"] += r["crosses_beat_boundary"] == "yes"
            o["fires_suppressed"] += (r["suppression"] or "none") != "none"
            if r["crosses_beat_boundary"] == "yes" or (r["suppression"] or "none") != "none":
                o["spillover"].append({"incident_id": r["id"], "kind": kind, "beat_uid": r["beat_uid"],
                                       "crosses_beat_boundary": r["crosses_beat_boundary"], "beats_touched": r["beats_touched"],
                                       "suppression": r["suppression"], "suppression_utc": r["suppression_utc"]})
        if kind == "predicted":
            b = o["ignition"]
            b["tasks"] += 1
            if not r["r_outcome"]:
                b["not_reported"] += 1
                continue
            ins = r["inspection"] or "not_shown"
            b["inspected" if ins == "completed" else "arrived_not_inspected" if ins == "arrived" else "not_shown"] += 1
            if ins != "completed":
                continue                       # an arrival is not credited as a check
            b["inspected_in_window"] += bool(r["r_visited"] and r["due_from_utc"] <= r["r_visited"] <= r["due_utc"])
            b["nothing_found"] += r["r_outcome"] == "nothing_found"
            b["fires_found"] += fire
            ok = fire and r["status"] == "verified" and r["evidence"] == "strong"
            b["fires_verified"] += ok
            b["fires_verified_no_recent_viirs"] += ok and not linked
            b["fires_new"] += ok and not linked and r["burn_age"] in ("now", "1_2_days")
            if ok and not linked:
                per_beat_n[r["beat_uid"]] = per_beat_n.get(r["beat_uid"], 0) + 1
        elif kind == "chance":
            o["chance_finds"] += 1
            o["chance_near_recent_viirs" if linked else "chance_no_recent_viirs"] += 1
        else:
            b = o["response"]
            b["alerts"] += 1
            b["fires_found"] += fire
            limit = firms.iso(firms.parse_utc(r["first_seen_utc"]) + timedelta(days=2))
            if r["first_report_utc"] and r["first_report_utc"] <= limit:
                b["visited_2d"] += 1
            elif limit > now_utc:
                b["pending"] += 1             # its 2 days are not over yet
            else:
                b["missed"] += 1
                sc = None
                if scars:
                    pts = con.execute("SELECT lat, lon, acq_utc FROM detections WHERE incident_id=?", (r["id"],)).fetchall()
                    sc = scars.for_points(pts)
                b["missed_with_scar"] += bool(sc and sc.get("scar_found") == "yes")
                missed.append({"arm": arm, "alert_id": r["id"], "beat_uid": r["beat_uid"], "beat": beats.name(r["beat_uid"]),
                               "first_seen_utc": r["first_seen_utc"], "lat": r["lat"], "lon": r["lon"], "large": r["large"],
                               "first_report_utc": r["first_report_utc"], "scar_found": sc and sc.get("scar_found"),
                               "scar_ha": sc and sc.get("scar_ha")})
    hours, _ = person_hours(con, s0, s1, now_utc)
    per_beat_h = {}
    for a, o in out.items():
        o["person_hours"] = {s: {c: 0.0 for c in COMPONENTS} for s in ("ignition", "response", "unassigned")}
    for (beat, stream, comp), h in hours.items():
        arm = A.get(beat)
        if arm in out:
            out[arm]["staff_hours"][stream] = out[arm]["staff_hours"].get(stream, 0.0) + h
            out[arm]["person_hours"].setdefault(stream, {c: 0.0 for c in COMPONENTS})[comp] += h
            if stream == "ignition":
                per_beat_h[beat] = per_beat_h.get(beat, 0.0) + h
    starts, fires_by_beat = fire_counts(con, s0, s1, A)
    per_beat_n = {b: v["ignition"] for b, v in fires_by_beat.items()}
    per_arm = {}
    for beat, arm in A.items():
        per_arm.setdefault(arm, []).append((per_beat_n.get(beat, 0), per_beat_h.get(beat, 0.0)))
    for a, o in out.items():
        o["staff_hours"] = {k: round(v, 1) for k, v in o["staff_hours"].items()}
        o["person_hours"] = {s: {c: round(v, 1) for c, v in d.items()} for s, d in o["person_hours"].items()}
        tot = sum(o["staff_hours"].values())
        o["unassigned_share"] = round(o["staff_hours"].get("unassigned", 0) / tot, 3) if tot else None
        o["fires"] = starts.get(a) or _empty_fires()
        km2 = sum(v for b_, v in forest_km2().items() if A.get(b_) == a)
        weeks = ((datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1) / 7
        x = dose[a]
        import statistics
        o["effort"] = {"forest_km2": round(km2, 1), "weeks": round(weeks, 1),
                       "person_hours_per_km2_per_week": round(tot / km2 / weeks, 3) if km2 and weeks > 0 else None,
                       "inspections": x["inspections"],
                       "median_minutes_on_site": round(statistics.median(x["on_site_min"]), 1) if x["on_site_min"] else None,
                       "people_met": x["people_met"], "warnings": x["warnings"], "fir_por": x["fir_por"],
                       "label": "exploratory dose measures (protocol 0.9), recorded not tested"}
        n, h = o["fires"]["confirmed_starts_accepted"]["ignition"], o["staff_hours"]["ignition"]
        n_any = o["fires"]["confirmed_starts"]["ignition"]
        assigned = o["staff_hours"]["ignition"] + o["staff_hours"]["response"]
        h_split = h + (o["staff_hours"].get("unassigned", 0) * h / assigned if assigned else 0)
        unc = o["fires"]["unclassifiable"]["ignition"]
        o["primary"] = {"confirmed_starts_ignition": n, "accepted_only": True, "ignition_person_hours": h,
                        "per_100_ignition_person_hours": round(100 * n / h, 2) if h else None,
                        "rate_ratio_vs_fixed": None if a == "fixed" else _boot_ratio(per_arm, a, "fixed"),
                        "rate_ratio_label": "beat bootstrap, not the locked analysis",
                        "sensitivity": {
                            "per_100_with_unassigned_split": round(100 * n / h_split, 2) if h_split else None,
                            "per_100_all_person_hours": round(100 * n / tot, 2) if tot else None,
                            "per_100_unclassifiable_as_starts": round(100 * (n + unc) / h, 2) if h else None,
                            "per_100_no_acceptance_required": round(100 * n_any / h, 2) if h else None}}
    secondary = {"forecast_vs_calendar": _boot_ratio(per_arm, "forecast", "calendar"),
                 "label": "beat bootstrap, not the locked analysis"}
    shadow = [dict(r) | {"cells": len(json.loads(r["cells"]))} for r in con.execute(
        "SELECT id, issue_date, list_name, model_version, cells FROM shadow_lists WHERE issue_date BETWEEN ? AND ?", (start, end))]
    return {"start": start, "end": end, "arms": out, "secondary": secondary, "missed": missed, "shadow_lists": shadow,
            "notes": ["Primary (v3): unique confirmed starts credited to completed ignition-stream inspections and accepted "
                      "by the range officer, per 100 "
                      "ignition-stream person-hours. Rate ratios here are a beat bootstrap, not the locked analysis "
                      "(block randomisation, run from the per-beat CSV).",
                      "Fires are deduplicated (500 m / 2 days with no satellite event) and credited to the first completed "
                      "inspection, or first visit / chance find in the other streams. Classes are provisional until the "
                      "post-season grouping is imported and disputed cases are reviewed.",
                      "Only completed inspections (2+ photos inside the cell, 100 m apart) count as checks.",
                      "Person-hours = shift length x crew size; components travel / on_site / idle / no_positions "
                      f"(phone fixes more than {GAP_MIN} min apart).",
                      "(d) is against fires found on the ground; all first-day fires in the post-season grouping come "
                      "from the FSI grouping on the analysis side.",
                      "Forecast vs calendar is reported, not claimed: one season cannot separate them."]}


def _empty_fires():
    z = lambda: {"ignition": 0, "response": 0, "chance": 0, "total": 0}
    return {"confirmed_starts": z(), "confirmed_starts_accepted": z(), "continuation": z(), "older_burn": z(), "unclassifiable": z(), "pending_review": z(),
            "found_not_credited": 0, "time_to_discovery_h": {"ignition": None, "response": None, "chance": None}}


def fire_counts(con, s0, s1, A):
    """Unique fires per arm and per beat, by class and by the stream that found them first (protocol v3 section 0.6).
    A fire belongs to the arm of the beat of its credited task. Time to discovery uses est_ignition_utc when imported."""
    import statistics
    by_arm, by_beat, ttd = {}, {}, {}
    for f in con.execute("""SELECT f.*, i.beat_uid, i.arm, i.status AS i_status FROM fires f LEFT JOIN reports r ON r.id=f.credited_report_id
                            LEFT JOIN incidents i ON i.id=r.incident_id
                            WHERE f.merged_into IS NULL AND f.created_utc BETWEEN ? AND ?""", (s0, s1)).fetchall():
        if not f["credited_report_id"]:
            beat = con.execute("""SELECT i.beat_uid FROM reports r JOIN incidents i ON i.id=r.incident_id WHERE r.fire_id=?
                                  ORDER BY r.id LIMIT 1""", (f["fire_id"],)).fetchone()
            arm = beat and A.get(beat[0])
            if arm:
                by_arm.setdefault(arm, _empty_fires())["found_not_credited"] += 1
            continue
        arm = f["arm"] or A.get(f["beat_uid"])
        if not arm:
            continue
        o = by_arm.setdefault(arm, _empty_fires())
        b = by_beat.setdefault(f["beat_uid"], {"ignition": 0, "response": 0, "chance": 0, "unclassifiable": 0, "pending_review": 0,
                                               "ignition_any": 0, "response_any": 0, "chance_any": 0})
        st = f["credited_stream"]
        cls = f["class_final"] or ("pending_review" if f["queued"] else f["class_auto"])
        key = {"confirmed_start": "confirmed_starts"}.get(cls, cls)
        o[key][st] += 1
        o[key]["total"] += 1
        if cls == "confirmed_start":
            # Primary counts only reports the range officer accepted (protocol v3 section 0.2); rejected ones
            # (sent back to revisit) never count; "no acceptance required" is a sensitivity.
            ok = f["i_status"] == "verified"
            o["confirmed_starts_accepted"][st] += ok
            o["confirmed_starts_accepted"]["total"] += ok
            b[st] += ok
            b[st + "_any"] += 1
            if f["est_ignition_utc"] and f["discovered_utc"]:
                ttd.setdefault((arm, st), []).append((_t(f["discovered_utc"]) - _t(f["est_ignition_utc"])).total_seconds() / 3600)
        elif cls in ("unclassifiable", "pending_review"):
            b[cls] += 1
    for (arm, st), v in ttd.items():
        by_arm[arm]["time_to_discovery_h"][st] = {"median": round(statistics.median(v), 1), "n": len(v)}
    return by_arm, by_beat


def beat_csv(con, start, end, now_utc):
    """Raw per-beat rows for the locked analysis: beat_uid, block, arm, starts by stream, person-hours by stream and component."""
    A, B = arms(), blocks()
    s0, s1 = f"{start}T00:00:00Z", f"{end}T23:59:59Z"
    for st in con.execute("SELECT DISTINCT staff_id FROM shifts WHERE start_utc BETWEEN ? AND ?", (s0, s1)).fetchall():
        refresh_sites(con, st[0], s0, s1)
    hours, _ = person_hours(con, s0, s1, now_utc)
    _, fb = fire_counts(con, s0, s1, A)
    tasks = {}
    for r in con.execute("""SELECT i.beat_uid, count(*) AS n, sum(r.inspection='completed') AS done FROM incidents i
                            LEFT JOIN reports r ON r.id=(SELECT max(id) FROM reports WHERE incident_id=i.id AND inspection='completed')
                            WHERE i.kind='predicted' AND i.first_seen_utc BETWEEN ? AND ? GROUP BY i.beat_uid""", (s0, s1)):
        tasks[r["beat_uid"]] = (r["n"], r["done"] or 0)
    rows = []
    for beat in sorted(A):
        f = fb.get(beat, {})
        row = {"beat_uid": beat, "block": B.get(beat, ""), "arm": A[beat],
               "starts_ignition": f.get("ignition", 0), "starts_response": f.get("response", 0), "starts_chance": f.get("chance", 0)}
        row["starts_total"] = row["starts_ignition"] + row["starts_response"] + row["starts_chance"]
        for s in ("ignition", "response", "chance"):     # sensitivity: range officer's accept not required
            row[f"starts_{s}_no_acceptance"] = f.get(s + "_any", 0)
        row["unclassifiable"], row["pending_review"] = f.get("unclassifiable", 0), f.get("pending_review", 0)
        row["ignition_tasks"], row["ignition_inspected"] = tasks.get(beat, (0, 0))
        tot = 0.0
        for s in ("ignition", "response", "unassigned"):
            st = 0.0
            for c in COMPONENTS:
                h = hours.get((beat, s, c), 0.0)
                row[f"ph_{s}_{c}"] = round(h, 2)
                st += h
            row[f"ph_{s}_total"] = round(st, 2)
            tot += st
        row["ph_total"] = round(tot, 2)
        rows.append(row)
    return rows
