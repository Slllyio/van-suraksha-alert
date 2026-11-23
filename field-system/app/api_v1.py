"""Integration API (v1) for another platform's app and dashboard, e.g. eNetra.

Auth: header X-Api-Key with one of FS_SERVICE_KEYS. The platform keeps its own users; it passes
its user's ID as staff_external_id, and a matching staff record is created on first use.
"""
import math, time
from . import scars
import json
from datetime import timedelta
from typing import List, Optional

from fastapi import Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, db, firms, pilot, webhook
from .server import BEATS_REF, app, do_review, load_meta, read_photos, record_chance, record_positions, record_report, now
from .hint import safe


def service(x_api_key: str = Header(default="")):
    if not config.SERVICE_KEYS or x_api_key not in config.SERVICE_KEYS:
        raise HTTPException(401, "missing or wrong X-Api-Key")
    return True


def staff_id(con, external_id, name=None, beat_uid=None):
    r = con.execute("SELECT id FROM staff WHERE phone = ?", ("ext:" + external_id,)).fetchone()
    if r:
        return r["id"]
    cur = con.execute("INSERT INTO staff(name, role, beat_uid, phone, pin_hash) VALUES (?, 'guard', ?, ?, '!')",
                      (name or external_id, beat_uid, "ext:" + external_id))
    return cur.lastrowid


def burn_hint(pts):
    """'possible_controlled_burn' for Nov-Feb, daytime-only, low-heat fires (fire-line and early burning
    season), stronger when the pixels lie in a line. A hint for the queue, never a reason to skip a visit."""
    if not pts or not all(int(x["acq_utc"][5:7]) in (11, 12, 1, 2) for x in pts):
        return None
    if not all(x["daynight"] == "D" for x in pts) or max(x["frp"] or 0 for x in pts) > 10:
        return None
    linear = False
    if len(pts) >= 3:
        import numpy as np
        xy = np.array([[x["lon"] * math.cos(math.radians(x["lat"])), x["lat"]] for x in pts]) * 111
        ev = np.linalg.eigvalsh(np.cov((xy - xy.mean(0)).T))
        linear = ev[1] > 0.05 and ev[1] > 9 * max(ev[0], 1e-6)   # long axis 3x the short one, >~0.5 km long
    return "possible_controlled_burn_linear" if linear else "possible_controlled_burn"


def _search_m(con, iid):
    from .server import search_m
    return search_m(con, iid)


OFFICIALS_ONLY = ("cause_sample", "control_burn", "big_fire", "direction", "still_burning", "runway", "spread_24h", "burn_scar")


def alert_json(con, r, full=False, view="official"):
    """view='guard' leaves out the officials-only hints (for answers that go back to a guard's phone)."""
    out = _alert_json(con, r, full)
    if view == "guard":
        for k in OFFICIALS_ONLY:
            out.pop(k, None)
    return out


def _alert_json(con, r, full=False):
    B = BEATS_REF()
    beats = [x["beat_uid"] for x in con.execute("SELECT beat_uid FROM incident_beats WHERE incident_id=?", (r["id"],))]
    p = B.by_uid.get(r["beat_uid"], {})
    kind = r["kind"] or "alert"
    out = {
        "id": r["id"], "kind": kind, "stream": pilot.STREAM_OF.get(kind), "status": r["status"], "outcome": r["outcome"],
        "lat": r["lat"], "lon": r["lon"],
        "beat_uid": r["beat_uid"], "beat": p.get("beat"), "range": p.get("range"), "division": p.get("division"),
        "all_beat_uids": beats,                       # junction alerts go to every beat listed
        "first_seen_utc": r["first_seen_utc"], "last_seen_utc": r["last_seen_utc"], "due_utc": r["due_utc"],
        "n_points": r["n_detections"], "sensors": r["sensors"].split(","), "max_frp_mw": r["max_frp"],
        "large_fire": bool(r["large"]),
        "search_m": _search_m(con, r["id"]),   # search this far around the point, all sides (half pixel + 100 m)
        "reached_utc": r["arrived_utc"], "first_report_utc": r["first_report_utc"],
        "updated_utc": r["updated_utc"] or r["created_utc"],
    }
    if kind == "predicted":   # patrol pilot check task for one 500 m cell
        out["task"] = {"cell_id": r["cell_id"], "stream": r["stream"], "issue_date": r["issue_date"],
                       "valid_from_utc": r["due_from_utc"], "due_utc": r["due_utc"], "arm": r["arm"], "model_hash": r["model_hash"],
                       "model_version": json.loads(r["model_version"]) if r["model_version"] else None,
                       "near_active_fire": bool(r["near_active_fire"]), "score": r["score"],
                       "cell": json.loads(r["cell_geom"]) if r["cell_geom"] else None}
    elif kind == "chance":
        out["task"] = {"arm": r["arm"]}
    if kind == "alert":
        from . import control_burn
        g = control_burn.cause_check(con, r, firms.iso(now()))
        out["cause_required"] = g in ("tagged", "random")   # show to the guard: the report must carry a cause
        from . import big_fire
        out["big_fire_flag"] = big_fire.guard_flag(con, r, firms.iso(now()))   # show to the guard too (Akkshay, 18 Oct 2026)
        out["big_fire_text"] = big_fire.GUARD_TEXT if out["big_fire_flag"] else None
        # officials' view only from here: eNetra should not show these to guards
        out["cause_sample"] = {"group": g, "p": con.execute("SELECT cause_p FROM incidents WHERE id=?", (r["id"],)).fetchone()[0]} if g else None
        out["control_burn"] = safe(control_burn.check, con, r, firms.iso(now()))   # a broken hint is left off, never a 500
        out["big_fire"] = safe(big_fire.check, con, r, firms.iso(now()))
        from . import direction   # heading from a 30 m scene that caught the fire burning; null when none (hint only)
        out["direction"] = safe(direction.for_incident, con, r["id"], now())
        from . import still_burning   # chance a fire VIIRS stopped seeing is still burning; null under 6 h dark
        out["still_burning"] = safe(still_burning.check, con, r["id"], now())
        from . import runway   # which side of a new fire likely burns farther; null when not scored (hint only)
        out["runway"] = safe(runway.for_incident, con, r["id"])
        if full:   # likely burnt ground 24 h after the latest VIIRS look (GeoJSON Feature); null when that look is over 24 h old
            from . import spread24
            out["spread_24h"] = safe(spread24.for_incident, con, r["id"], now())
    pts = con.execute("""SELECT source, lat, lon, acq_utc, frp, daynight, fsi_division, fsi_range, fsi_beat, fsi_compartment
                         FROM detections WHERE incident_id=?""", (r["id"],)).fetchall()
    fsi = [x for x in pts if x["fsi_beat"]]
    tags = con.execute("""SELECT t.beat, t.compartment FROM fsi_tags t JOIN detections x ON x.id = t.detection_id
                          WHERE x.incident_id=?""", (r["id"],)).fetchall() if fsi else []   # every beat of a junction pixel
    out["fsi"] = {   # FSI's own tags for this fire (from FSI's portal); null when FSI has not sent it
        "division": fsi[0]["fsi_division"], "range": fsi[0]["fsi_range"],
        "beats": sorted({x["fsi_beat"] for x in fsi} | {t["beat"] for t in tags}),
        "compartments": sorted({x["fsi_compartment"] for x in fsi if x["fsi_compartment"]} | {t["compartment"] for t in tags if t["compartment"]}),
        "sent_by_fsi": True, "fsi_only": all(x["source"] == "FSI_PORTAL" for x in pts),
    } if fsi else None
    out["burn_hint"] = burn_hint(pts)
    # Burn scar from Sentinel-2/Landsat (burn-scar thread). none_visible is NOT a false alert:
    # small, litter-only or under-canopy fires leave no visible scar. Support for the visit only.
    out["burn_scar"] = safe(scars.for_points, pts, with_geometry=full)   # outline (GeoJSON) only on the detail call
    # Fire spreads into nearby unburned forest over the next days: in Ratapani 93% of first burns in
    # never-burned cells had a fire within 1 km in the 7 days before (FSI scouting, cold_start_cells.md).
    # watch_nearby: keep forest within 1 km on watch for 7 days. near_recent: earlier alerts within
    # 1 km in the 7 days before this one, i.e. this fire is likely spreading from them.
    until = firms.parse_utc(r["last_seen_utc"]) + timedelta(days=7)
    out["watch_nearby"] = {"radius_km": 1.0, "until_utc": firms.iso(until)}
    out["near_recent"] = firms.near_recent(con, r)
    if full:
        out["points"] = [dict(x) for x in con.execute(
            """SELECT source, satellite, lat, lon, acq_utc, confidence, frp, daynight, forest_share, fsi_beat, fsi_compartment
               FROM detections WHERE incident_id=? ORDER BY acq_utc""", (r["id"],))]
        reps = []
        for rp in con.execute("""SELECT r.*, s.name AS staff_name, substr(s.phone, 5) AS staff_external_id
                                 FROM reports r JOIN staff s ON s.id=r.staff_id WHERE incident_id=? ORDER BY r.id""", (r["id"],)):
            d = dict(rp)
            d["flags"] = json.loads(d["flags"] or "[]")
            d["linked_alerts"] = json.loads(d["linked_alerts"]) if d["linked_alerts"] else None
            d["photos"] = [{"id": ph["id"], "taken_utc": ph["taken_utc"], "distance_km": ph["distance_km"],
                            "flags": json.loads(ph["flags"] or "[]"), "url": f"/api/v1/photos/{ph['id']}"}
                           for ph in con.execute("SELECT * FROM photos WHERE report_id=?", (rp["id"],))]
            reps.append(d)
        out["reports"] = reps
    return out


@app.get("/api/v1/alerts", dependencies=[Depends(service)])
def v1_alerts(since: Optional[str] = None, division: Optional[str] = None, range_name: Optional[str] = None,
              beat_uid: Optional[str] = None, status: Optional[str] = None, kind: Optional[str] = None, limit: int = 1000,
              view: str = "official"):
    """Alerts changed since a time (pass the previous answer's generated_utc), newest first, filtered by area. Every
    change (new points, report, review, send-back, reached) moves updated_utc, so a poll misses none of them.
    kind: alert (satellite), predicted (pilot cell checks), chance (fires found with no task); default all.
    view=guard leaves out the officials-only hints, for lists shown on a guard's phone."""
    q, args = "SELECT i.* FROM incidents i WHERE 1=1", []
    if kind:
        q += " AND coalesce(i.kind, 'alert') = ?"
        args.append(kind)
    if since:
        q += " AND (i.last_seen_utc >= ? OR i.first_report_utc >= ? OR coalesce(i.updated_utc, i.created_utc) >= ?)"
        args += [since] * 3
    if status:
        q += " AND i.status = ?"
        args.append(status)
    if beat_uid:
        q += " AND i.id IN (SELECT incident_id FROM incident_beats WHERE beat_uid = ?)"
        args.append(beat_uid)
    if division or range_name:   # in SQL, before the LIMIT ('Division:Range' or a plain range name within `division`)
        if range_name and ":" in range_name:
            division, range_name = range_name.split(":", 1)
        uids = [p["beat_uid"] for p in BEATS_REF().props
                if (not division or p.get("division") == division) and (not range_name or p["range"] == range_name)]
        q += f" AND i.beat_uid IN ({','.join('?' * len(uids)) or 'NULL'})"
        args += uids
    with db.tx() as con:
        rows = con.execute(q + " ORDER BY i.first_seen_utc DESC LIMIT ?", args + [min(limit, 5000)]).fetchall()
        out = [alert_json(con, r, view=view) for r in rows]
    return {"type": "FeatureCollection", "generated_utc": firms.iso(now()), "features": [
        {"type": "Feature", "id": a["id"], "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]}, "properties": a}
        for a in out]}


@app.get("/api/v1/alerts/{iid}", dependencies=[Depends(service)])
def v1_alert(iid: int):
    with db.tx() as con:
        r = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
        if not r:
            raise HTTPException(404)
        return alert_json(con, r, full=True)


@app.post("/api/v1/alerts/{iid}/reports", dependencies=[Depends(service)])
async def v1_report(iid: int, staff_external_id: str = Form(...), staff_name: Optional[str] = Form(None),
                    report: str = Form(..., description="JSON: outcome, land_type, fire_type, area_ha, cause, action, crew, "
                                                         "notes, visited_utc, fire_out_utc, first_known_by, burn_age, crosses_beat_boundary, beats_touched, "
                                                         "suppression, suppression_utc, people_met, enforcement (none|warning|fir_por), device_id, "
                                                         "device_lat, device_lon, device_acc_m"),
                    photo_meta: str = Form("[]", description="JSON list, one per photo: dev_lat, dev_lon, dev_utc, mock_location"),
                    photos: List[UploadFile] = File(default=[])):
    raw = await read_photos(photos)
    f, meta = _report_json(report), load_meta(photo_meta)

    def go(con):   # retried on a locked database
        inc = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
        if not inc:
            raise HTTPException(404)
        sid = staff_id(con, staff_external_id, staff_name, inc["beat_uid"])
        return record_report(con, inc, sid, dict(f), raw, meta)
    res = db.write(go)
    with db.tx() as con:
        r = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
        res["alert"], hook = alert_json(con, r, view="guard"), alert_json(con, r)   # the answer goes to a guard's phone
    if not res.get("duplicate"):
        webhook.send("alert.reported", hook)
    return res


def _report_json(report):
    try:
        f = json.loads(report)
    except ValueError:
        raise HTTPException(400, "report must be JSON")
    if not isinstance(f, dict):
        raise HTTPException(400, "report must be a JSON object")
    return f


class V1Position(BaseModel):
    lat: float
    lon: float
    acc_m: Optional[float] = None
    utc: Optional[str] = None
    device_id: Optional[str] = None
    mock_location: Optional[bool] = None


class V1Positions(BaseModel):
    staff_external_id: str
    staff_name: Optional[str] = None
    beat_uids: List[str] = []          # the beats this person covers; empty = the beat on the staff record
    positions: List[V1Position]


@app.post("/api/v1/positions", dependencies=[Depends(service)])
def v1_positions(body: V1Positions):
    from .server import MAX_POSITIONS
    if len(body.positions) > MAX_POSITIONS:
        raise HTTPException(413, f"send at most {MAX_POSITIONS} positions per request")
    def go(con):   # retried on a locked database
        sid = staff_id(con, body.staff_external_id, body.staff_name)
        uids = body.beat_uids or [x for x in [con.execute("SELECT beat_uid FROM staff WHERE id=?", (sid,)).fetchone()[0]] if x]
        if not uids:   # one person's ping must never mark another beat's alert reached
            raise HTTPException(400, "beat_uids is required (the beats this person covers)")
        where = f"i.id IN (SELECT incident_id FROM incident_beats WHERE beat_uid IN ({','.join('?' * len(uids))}))"
        return record_positions(con, sid, where, list(uids), [p.dict() for p in body.positions])
    reached = db.write(go)
    with db.tx() as con:
        changed = [alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (i,)).fetchone()) for i in reached]
    for a in changed:
        webhook.send("alert.reached", a)
    return {"reached": reached}


class V1Review(BaseModel):
    reviewer_external_id: str
    reviewer_name: Optional[str] = None
    decision: str            # accept | revisit
    note: Optional[str] = None
    report_id: Optional[int] = None   # the report the reviewer looked at: 409 when a newer one came in


@app.post("/api/v1/alerts/{iid}/review", dependencies=[Depends(service)])
def v1_review(iid: int, body: V1Review):
    if body.decision not in ("accept", "revisit"):
        raise HTTPException(400, "decision must be accept or revisit")
    with db.tx() as con:
        inc = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
        if not inc:
            raise HTTPException(404)
        rid = staff_id(con, body.reviewer_external_id, body.reviewer_name)
        do_review(con, inc, rid, body.decision, body.note, body.report_id)   # same rules as the control room
        a = alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone())
    webhook.send("alert.reviewed", a)
    return a


@app.get("/api/v1/photos/{pid}", dependencies=[Depends(service)])
def v1_photo(pid: int, thumb: bool = False):
    with db.tx() as con:
        p = con.execute("SELECT * FROM photos WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404)
    return FileResponse(p["thumb"] if thumb else p["path"])


@app.get("/api/v1/beats/summary", dependencies=[Depends(service)])
def v1_beat_summary(days: float = 7, division: Optional[str] = None):
    """Per-beat accountability table: alerts, reached, visited, hours to reach and to report, what staff found."""
    B = BEATS_REF()
    since = firms.iso(now() - timedelta(days=days))
    rows = {}
    with db.tx() as con:
        for r in con.execute("SELECT * FROM incidents WHERE first_seen_utc >= ?", (since,)):
            p = B.by_uid.get(r["beat_uid"], {})
            if division and p.get("division") != division:
                continue
            b = rows.setdefault(r["beat_uid"], {"beat_uid": r["beat_uid"], "beat": p.get("beat"), "range": p.get("range"),
                                                "division": p.get("division"), "alerts": 0, "reached": 0, "reported": 0,
                                                "verified": 0, "overdue": 0, "large_fires": 0, "_reach": [], "_report": [],
                                                "outcomes": {}})
            t0 = firms.parse_utc(r["first_seen_utc"])
            b["alerts"] += 1
            b["large_fires"] += r["large"]
            b["verified"] += r["status"] == "verified"
            b["overdue"] += r["status"] in ("new", "revisit") and r["due_utc"] < firms.iso(now())
            if r["arrived_utc"]:
                b["reached"] += 1
                b["_reach"].append((firms.parse_utc(r["arrived_utc"]) - t0).total_seconds() / 3600)
            if r["first_report_utc"]:
                b["reported"] += 1
                b["_report"].append((firms.parse_utc(r["first_report_utc"]) - t0).total_seconds() / 3600)
            if r["outcome"]:
                b["outcomes"][r["outcome"]] = b["outcomes"].get(r["outcome"], 0) + 1
    for b in rows.values():
        for k in ("reach", "report"):
            h = sorted(b.pop("_" + k))
            b[f"median_hours_to_{k}"] = round(h[len(h) // 2], 1) if h else None
    return {"days": days, "beats": sorted(rows.values(), key=lambda b: -b["alerts"])}


@app.get("/api/v1/brief", dependencies=[Depends(service)])
def v1_brief(division: Optional[str] = None, day: Optional[str] = None):
    """Officials' daily brief as data (16:00 IST): one division, or every division with open fires when none is given."""
    from . import brief
    t = brief.clock_for(day, now())
    with db.tx() as con:
        if division:
            return brief.build(con, division, t, BEATS_REF())
        return {"clock_utc": firms.iso(t), "divisions": brief.statewide(con, t, BEATS_REF())}


@app.post("/api/v1/daily_scores", dependencies=[Depends(service)])
def v1_daily_scores(body: dict):
    """The day's division-model scores from the pipeline, turned into the officials' 2-day list (app/daily_list.py).
    JSON: issue_date, model_version, cell [mp_grid ids], pct [calibrated chance 0-1, previous season's calibration],
    score [raw score]; optional counts {division: n}, base_share {division: share}, rule. Sending a day again replaces it."""
    from . import daily_list
    try:
        with db.tx() as con:
            return daily_list.build(con, BEATS_REF(), body, now())
    except (KeyError, ValueError, TypeError, IndexError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/v1/daily_list", dependencies=[Depends(service)])
def v1_daily_list(division: str, day: Optional[str] = None):
    """One division's 2-day list: squares with %, beat, range and why each is on it (division / quiet square / statewide)."""
    from . import daily_list
    with db.tx() as con:
        day = day or (con.execute("SELECT max(issue_date) FROM daily_list_meta").fetchone()[0] or "")
        v = daily_list.division_view(con, day, division, BEATS_REF())
    if not v:
        raise HTTPException(404, "no list for that day")
    return _with_age(v, day)


@app.post("/api/v1/big_watch_scores", dependencies=[Depends(service)])
def v1_big_watch_scores(body: dict):
    """The day's big-fire watch list from research/large-fires/watch/big_watch.py (app/big_watch_list.py): issue_date,
    model_version, cell, division, rank_in_division, top1, top2. Separate from the 2-day list; sending a day again replaces it."""
    from . import big_watch_list
    try:
        with db.tx() as con:
            return big_watch_list.store(con, body, now())
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/v1/big_watch", dependencies=[Depends(service)])
def v1_big_watch(division: str, day: Optional[str] = None):
    """One division's big-fire watch list (top 1-2% of its squares, rank only, officials only)."""
    from . import big_watch_list
    with db.tx() as con:
        day = day or (con.execute("SELECT max(issue_date) FROM big_watch_meta").fetchone()[0] or "")
        v = big_watch_list.division_view(con, day, division, BEATS_REF())
    if not v:
        raise HTTPException(404, "no watch list for that day")
    return _with_age(v, day)


def _with_age(v, day):
    """days_old = IST days since the list was issued; the evening list is current while days_old <= 1.
    stale tells eNetra not to show it as today's list (the evening run missed a night)."""
    import datetime as _dt
    today = (now() + _dt.timedelta(hours=5, minutes=30)).date()
    v["days_old"] = (today - _dt.date.fromisoformat(day)).days
    v["stale"] = v["days_old"] > 1
    return v


@app.get("/api/v1/scar_check", dependencies=[Depends(service)])
def v1_scar_check(division: Optional[str] = None, day: Optional[str] = None):
    """Weekly scar check as data: per range, alerts, how many left a scar, hectares burnt (outlines merged)."""
    from . import scar_check
    day = day or (now() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    with db.tx() as con:
        return scar_check.week(con, BEATS_REF(), day, division)


# ---------- patrol pilot ----------
@app.post("/api/v1/tasks", dependencies=[Depends(service)])
def v1_tasks(body: dict):
    """Ignition-stream check tasks for predicted cells, sent each evening (protocol v2). JSON: issue_date (YYYY-MM-DD,
    day t), grid ('ratapani' or 'mp'), model_version {model_hash, code_commit, config_hash, data_cutoff_utc, ...},
    tasks: [{cell_id, beat_uid?, arm?, score?, near_active_fire?, geometry?}]. Valid t+1 06:00 to t+2 19:30 IST.
    arm defaults to the beat's arm. Cells with a satellite point within 1.5 km in the 3 days before issue are never
    created (returned in excluded_near_active). shadow: true + list_name stores a list (e.g. the recent-fire ranker)
    for scoring after the season and creates no tasks. Sending the same list twice creates nothing new."""
    try:
        with db.tx() as con:
            res = pilot.add_tasks(con, BEATS_REF(), body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with db.tx() as con:
        made = [alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (i,)).fetchone()) for i in res["created"]]
    for a in made:
        webhook.send("task.created", a)
    return res


@app.post("/api/v1/chance_finds", dependencies=[Depends(service)])
async def v1_chance(staff_external_id: str = Form(...), staff_name: Optional[str] = Form(None),
                    report: str = Form(..., description="JSON as for a report; device_lat and device_lon required"),
                    photo_meta: str = Form("[]"), photos: List[UploadFile] = File(default=[])):
    """A fire staff came across with no task: becomes a 'chance' alert at the phone's position, already visited."""
    raw = await read_photos(photos)
    f, meta = _report_json(report), load_meta(photo_meta)
    if f.get("device_lat") is None or f.get("device_lon") is None:
        raise HTTPException(400, "device_lat and device_lon are required")
    def go(con):   # retried on a locked database
        sid = staff_id(con, staff_external_id, staff_name)
        st = dict(con.execute("SELECT * FROM staff WHERE id=?", (sid,)).fetchone())
        return record_chance(con, st, dict(f), raw, meta)
    res = db.write(go)
    with db.tx() as con:
        r = con.execute("SELECT * FROM incidents WHERE id=?", (res["incident_id"],)).fetchone()
        res["alert"], hook = alert_json(con, r, view="guard"), alert_json(con, r)
    if not res.get("duplicate"):
        webhook.send("alert.reported", hook)
    return res


class V1Shift(BaseModel):
    staff_external_id: str
    staff_name: Optional[str] = None
    beat_uid: Optional[str] = None     # the beat this crew works (gives the pilot arm)
    action: str                        # start | end
    utc: Optional[str] = None
    crew_size: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    device_id: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/v1/shifts", dependencies=[Depends(service)])
def v1_shift(body: V1Shift):
    """Crew-day log: start and end of a working day with crew size, so staff-hours include travel and waiting."""
    if body.action not in ("start", "end"):
        raise HTTPException(400, "action must be start or end")
    with db.tx() as con:
        sid = staff_id(con, body.staff_external_id, body.staff_name, body.beat_uid)
        if body.beat_uid:
            con.execute("UPDATE staff SET beat_uid=? WHERE id=?", (body.beat_uid, sid))
        f = body.dict() | {"start_utc": body.utc, "end_utc": body.utc}
        s = (pilot.shift_start if body.action == "start" else pilot.shift_end)(con, sid, f, firms.iso(now()))
    if not s:
        raise HTTPException(400, "no day started")
    return s


@app.get("/api/v1/pilot/report", dependencies=[Depends(service)])
def v1_pilot_report(start: str, end: str):
    with db.tx() as con:
        return pilot.report(con, BEATS_REF(), start, end, firms.iso(now()), scars)


@app.get("/api/v1/pilot/shakedown", dependencies=[Depends(service)])
def v1_pilot_shakedown(start: str = "2027-01-25", end: str = "2027-02-07"):
    with db.tx() as con:
        return pilot.shakedown(con, start, end, firms.iso(now()))


@app.get("/api/v1/pilot/beats.csv", dependencies=[Depends(service)])
def v1_pilot_beats(start: str, end: str):
    from .server import _csv
    with db.tx() as con:
        return _csv(pilot.beat_csv(con, start, end, firms.iso(now())), f"pilot_beats_{start}_{end}.csv")


@app.post("/api/v1/pilot/grouping", dependencies=[Depends(service)])
def v1_pilot_grouping(body: List[dict]):
    with db.tx() as con:
        return pilot.import_grouping(con, body, firms.iso(now()))


@app.get("/api/v1/health", dependencies=[Depends(service)])
def v1_health():
    """Dead-man check for eNetra or a monitor: last good poll per source, last 2-day list and watch list.
    problems lists what is late: no good NASA FIRMS read in 3 h (an empty or HTML file counts as failed), no good
    Bhuvan / FSI read in 6 h (when on), a poll running over 30 min or none finished in 3 poll intervals, points kept
    unfiltered because WorldCover could not be read, or, in the list season (20 Feb-30 May), no list for
    today after 19:45 IST (the evening run is 17:15 IST with retries until 19:15)."""
    import datetime as _dt
    t = now()
    ist = t + _dt.timedelta(hours=5, minutes=30)
    today = ist.strftime("%Y-%m-%d")
    with db.tx() as con:
        polls = {s: u for s, u in con.execute(
            "SELECT source, max(utc) FROM ingest_log WHERE error IS NULL GROUP BY source").fetchall()}
        errs = con.execute("SELECT utc, source, error FROM ingest_log WHERE error IS NOT NULL AND utc >= ? "
                           "ORDER BY id DESC LIMIT 5", (firms.iso(t - _dt.timedelta(hours=24)),)).fetchall()
        unf = con.execute("SELECT coalesce(sum(forest_unknown), 0) FROM ingest_log WHERE utc >= ?",
                          (firms.iso(t - _dt.timedelta(hours=24)),)).fetchone()[0]
        dl = bw = None
        try:
            dl = con.execute("SELECT max(issue_date) FROM daily_list_meta").fetchone()[0]
            bw = con.execute("SELECT max(issue_date) FROM big_watch_meta").fetchone()[0]
        except Exception:
            pass
    problems = []
    live = config.POLL_MINUTES > 0 and not config.DEMO_NOW
    def newest(*pre):
        return max([u for s, u in polls.items() if s and u and s.startswith(pre)], default=None)
    nasa = newest("FIRMS", "VIIRS_", "MODIS", "demo_firms")
    if not nasa or nasa < firms.iso(t - _dt.timedelta(hours=3)):
        problems.append(f"no good NASA FIRMS read in the last 3 h (newest {nasa})")
    for on, src in ((config.BHUVAN, "BHUVAN"), (config.FSI_PORTAL, "FSI_PORTAL")):
        u = newest(src)
        if on and live and (not u or u < firms.iso(t - _dt.timedelta(hours=6))):
            problems.append(f"no good {src} read in the last 6 h (newest {u})")
    from .server import POLL
    w = time.time()
    running = POLL["started"] and (not POLL["finished"] or POLL["finished"] < POLL["started"])
    if running and w - POLL["started"] > 30 * 60:
        problems.append(f"poll running for {round((w - POLL['started']) / 60)} min (hung download?)")
    elif live and POLL["finished"] and w - POLL["finished"] > 3 * config.POLL_MINUTES * 60 + 30 * 60:
        problems.append("poll thread stopped: no poll finished in 3 intervals")
    if unf:
        problems.append(f"forest filter unavailable for {unf} points in 24 h (WorldCover not readable: farm fires become tasks)")
    in_season = "02-20" <= today[5:] <= "05-30"
    if in_season and ist.strftime("%H:%M") >= "19:45":
        if dl != today:
            problems.append(f"no 2-day list for {today} (newest {dl})")
        if bw != today:
            problems.append(f"no big-fire watch list for {today} (newest {bw})")
    return {"ok": not problems, "problems": problems, "now_utc": firms.iso(t), "last_good_poll": polls,
            "recent_errors": [dict(utc=u, source=s, error=e) for u, s, e in errs],
            "daily_list_newest": dl, "big_watch_newest": bw, "list_season": in_season,
            "poll": {"started_utc": POLL["started"] and firms.iso(_dt.datetime.fromtimestamp(POLL["started"], _dt.timezone.utc)),
                     "finished_utc": POLL["finished"] and firms.iso(_dt.datetime.fromtimestamp(POLL["finished"], _dt.timezone.utc)),
                     "running_s": round(w - POLL["started"]) if running else 0},
            "forest_unknown_24h": unf}
