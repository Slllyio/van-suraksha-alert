"""Fire alert field system: live FIRMS alerts per beat, field visits with photo proof, supervisor review."""
import csv, hashlib, io, json, logging, random, secrets, sqlite3, threading, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, evidence, firms, pilot, scar_live
from .geo import Beats, haversine_km

log = logging.getLogger("server")
STATIC = Path(__file__).resolve().parent / "static"
OUTCOMES = {"active_fire", "burnt_out", "no_fire", "outside_forest", "controlled_burn",
            "nothing_found"}   # nothing_found: predicted-cell check with no fire and no fresh burn; never a false alert
app = FastAPI(title="Van Agni field checks")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
BEATS: Beats = None


@app.exception_handler(sqlite3.OperationalError)
async def db_busy(request: Request, e):
    """Still locked after the busy wait and retries: 503 (the field page keeps the report and sends it later), not 500."""
    if db.locked(e):
        log.error("database busy: %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "server busy, try again in a minute"}, status_code=503, headers={"Retry-After": "60"})
    raise e


@app.middleware("http")
async def refuse_early(request, call_next):
    """Check the service key and the body size before the body is read (FastAPI reads and parses a JSON body
    before it runs Depends(service), so a wrong key used to cost the full read and parse; uvicorn has no size limit)."""
    if request.url.path.startswith("/api/v1/") and (
            not config.SERVICE_KEYS or request.headers.get("x-api-key", "") not in config.SERVICE_KEYS):
        return JSONResponse({"detail": "missing or wrong X-Api-Key"}, status_code=401)
    n = request.headers.get("content-length")
    if n and n.isdigit() and int(n) > config.MAX_BODY:
        return JSONResponse({"detail": f"body over {config.MAX_BODY >> 20} MB"}, status_code=413)
    return await call_next(request)


def BEATS_REF():
    return BEATS


def now():
    # FS_DEMO_NOW replays a past day (e.g. 2026-04-15T12:30:00Z); never set it on a live server
    if config.DEMO_NOW:
        return datetime.strptime(config.DEMO_NOW, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def hash_pin(pin, salt=None):
    salt = salt or secrets.token_hex(8)
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pin.encode(), salt.encode(), 100_000).hex()}"


def pin_ok(pin, stored):
    salt = stored.split("$")[0]
    return secrets.compare_digest(hash_pin(pin, salt), stored)


@app.on_event("startup")
def startup():
    global BEATS
    db.init()
    BEATS = Beats()
    from . import scars
    scars.warm()   # burn-scar outlines for the map, built once in the background
    from . import webhook
    webhook.start()   # delivers queued events (also ones left from before a restart)
    if config.POLL_MINUTES > 0:
        if not config.DEMO_NOW:   # a demo replay must not pull today's live alerts
            threading.Thread(target=poller, daemon=True).start()
    from . import direction
    from . import runway
    if (direction.ON or runway.ON) and (config.POLL_MINUTES > 0 or config.DEMO_NOW):
        threading.Thread(target=direction_loop, daemon=True).start()


def direction_loop():
    """30 m direction hints (app/direction.py): slow (Planetary Computer reads), so on its own thread."""
    from . import direction, runway
    while True:
        n = 0
        try:
            n = direction.run_due(now()) if direction.ON else 0
        except Exception:
            log.exception("direction check failed")
        try:
            if runway.ON:
                n += runway.run_due(now())   # "which side runs farther" at a new fire's first look
        except Exception:
            log.exception("runway check failed")
        time.sleep(60 if n else 30 * 60)


POLL = {"started": None, "finished": None}   # heartbeat for GET /api/v1/health


def poller():
    first = True
    while True:
        POLL["started"] = time.time()
        try:
            firms.run_live(BEATS, "7d" if first else "24h")
            first = False
        except Exception:
            log.exception("poll failed")
        try:          # its own step: a failing hint must not stop the optimize and the daily scar run below
            from . import big_fire
            big_fire.score_new(now(), BEATS)   # so the officials' list and guard flags never score hundreds at once
        except Exception:
            log.exception("big-fire scoring failed")
        try:
            with db.tx() as con:
                con.execute("PRAGMA optimize")
            scar_live.run_if_due()   # once a day, in the background
        except Exception:
            log.exception("scar run failed")
        POLL["finished"] = time.time()
        time.sleep(config.POLL_MINUTES * 60)


# ---------- auth ----------
def current(fs_session: Optional[str] = Cookie(default=None)):
    if not fs_session:
        raise HTTPException(401, "login needed")
    with db.tx() as con:
        r = con.execute("""SELECT s.* FROM sessions x JOIN staff s ON s.id = x.staff_id
                           WHERE x.token = ? AND x.expires_utc > ? AND s.active = 1""",
                        (fs_session, firms.iso(now()))).fetchone()
    if not r:
        raise HTTPException(401, "login needed")
    return dict(r)


def supervisor(me=Depends(current)):
    if me["role"] not in ("ranger", "admin"):
        raise HTTPException(403, "supervisors only")
    return me


def scope_sql(me):
    """Which incidents a person sees: guard -> own beat, ranger -> own range, admin -> all."""
    if me["role"] == "guard":
        uids = [me["beat_uid"]]
    elif me["role"] == "ranger":
        uids = BEATS.in_range(me["range_name"])
    else:
        return "1=1", []
    return (f"i.id IN (SELECT incident_id FROM incident_beats WHERE beat_uid IN ({','.join('?' * len(uids)) or 'NULL'}))", uids)


class Login(BaseModel):
    staff_id: int
    pin: str


@app.get("/api/staff")
def staff_list(me=Depends(supervisor)):
    """Staff list for admins (sign-in asks for the staff number, so ids, roles and beats are not public)."""
    if me["role"] != "admin":
        raise HTTPException(403, "admins only")
    with db.tx() as con:
        rows = con.execute("""SELECT id, name, role, beat_uid, range_name FROM staff WHERE active=1 AND pin_hash <> '!'
                              ORDER BY role, name""").fetchall()   # '!' = eNetra users, who never sign in here
    return [dict(r, beat=BEATS.name(r["beat_uid"]) if r["beat_uid"] else r["range_name"] or "all") for r in rows]


_FAILS, _FAILS_LOCK = {}, threading.Lock()   # key -> (wrong PINs in a row, locked until); one server process


def _locked(key):
    with _FAILS_LOCK:
        return _FAILS.get(key, (0, 0))[1] > time.time()


def _fail(key, limit):
    with _FAILS_LOCK:
        n = _FAILS.get(key, (0, 0))[0] + 1
        _FAILS[key] = (n, time.time() + min(3600, 30 * 2 ** (n - limit)) if n >= limit else 0)
        if len(_FAILS) > 100_000:
            _FAILS.clear()


def check_pin_format(pin):
    if not (isinstance(pin, str) and pin.isdigit() and 4 <= len(pin) <= 12):
        raise HTTPException(400, "PIN must be 4 to 12 digits")


@app.post("/api/login")
def login(body: Login, response: Response, request: Request):
    keys = ((f"staff:{body.staff_id}", config.LOGIN_FAILS_ACCOUNT), (f"ip:{request.client.host if request.client else '?'}", config.LOGIN_FAILS_IP))
    if any(_locked(k) for k, _ in keys):
        raise HTTPException(429, "too many wrong PINs; wait a few minutes and try again")
    with db.tx() as con:
        s = con.execute("SELECT * FROM staff WHERE id=? AND active=1", (body.staff_id,)).fetchone()
        if not body.pin or not s or s["pin_hash"] == "!" or not pin_ok(body.pin, s["pin_hash"]):
            for k, lim in keys:
                _fail(k, lim)
            raise HTTPException(403, "wrong PIN")
        with _FAILS_LOCK:
            for k, _ in keys:
                _FAILS.pop(k, None)
        con.execute("DELETE FROM sessions WHERE expires_utc < ?", (firms.iso(now()),))
        tok = secrets.token_urlsafe(24)
        con.execute("INSERT INTO sessions VALUES (?,?,?)", (tok, s["id"], firms.iso(now() + timedelta(days=config.SESSION_DAYS))))
    response.set_cookie("fs_session", tok, max_age=config.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=config.SECURE_COOKIE)
    return {"ok": True, "staff_id": s["id"]}


@app.post("/api/logout")
def logout(response: Response, fs_session: Optional[str] = Cookie(default=None)):
    with db.tx() as con:
        con.execute("DELETE FROM sessions WHERE token=?", (fs_session,))
    response.delete_cookie("fs_session")
    return {"ok": True}


@app.get("/api/me")
def me_(me=Depends(current)):
    return {k: me[k] for k in ("id", "name", "role", "beat_uid", "range_name")} | {
        "beat": BEATS.name(me["beat_uid"]), "now_utc": firms.iso(now()), "demo": bool(config.DEMO_NOW)}


class NewStaff(BaseModel):
    name: str
    role: str
    pin: str
    beat_uid: Optional[str] = None
    range_name: Optional[str] = None
    phone: Optional[str] = None


@app.post("/api/staff")
def add_staff(body: NewStaff, me=Depends(supervisor)):
    if me["role"] != "admin" or body.role not in ("guard", "ranger", "admin"):
        raise HTTPException(403, "admins add staff; role must be guard, ranger or admin")
    check_pin_format(body.pin)
    staff_area_ok(body.role, body.beat_uid, body.range_name, lambda m: HTTPException(400, m))
    with db.tx() as con:
        cur = con.execute("INSERT INTO staff(name,role,beat_uid,range_name,phone,pin_hash) VALUES (?,?,?,?,?,?)",
                          (body.name, body.role, body.beat_uid, body.range_name, body.phone, hash_pin(body.pin)))
    return {"id": cur.lastrowid}


def staff_area_ok(role, beat_uid, range_name, err):
    """A guard needs a beat in the beat layer; a ranger a range that names one division ('Division:Range' when the name repeats)."""
    if role == "guard" and beat_uid not in BEATS.by_uid:
        raise err("unknown beat_uid")
    if role == "ranger" and len({BEATS.by_uid[u].get("division") for u in BEATS.in_range(range_name)}) != 1:
        raise err("range not found, or the name is used in more than one division: give it as 'Division:Range'")


# ---------- alerts ----------
def overdue(r):
    return r["status"] in ("new", "revisit") and r["due_utc"] < firms.iso(now())


def search_m(con, iid):
    """Where to search around the alert point: half the largest pixel of its latest pass (FIRMS scan/track, km) + 100 m
    (big-fires README 15d: the fire is anywhere inside its pixel; VIIRS pointing error is only ~75-150 m).
    About 300 m near the middle of a VIIRS pass, ~500 m at the swath edge. None if no FIRMS size is stored."""
    r = con.execute("""SELECT max(max(scan, track)) FROM detections WHERE incident_id=? AND scan > 0 AND acq_utc =
                       (SELECT max(acq_utc) FROM detections WHERE incident_id=? AND scan > 0)""", (iid, iid)).fetchone()[0]
    return round(r * 500 + 100) if r else None


def inc_row(r, con=None):
    d = dict(r)
    if con is not None:
        d["search_m"] = search_m(con, r["id"])
        d["beats"] = [BEATS.name(x["beat_uid"]) for x in con.execute(
            "SELECT beat_uid FROM incident_beats WHERE incident_id=?", (r["id"],))]
    d["beat"] = BEATS.name(r["beat_uid"])
    d["range"] = BEATS.by_uid.get(r["beat_uid"], {}).get("range", "")
    d["overdue"] = overdue(r)
    return d


def cause_fields(con, r, d, me):
    """2027 cause check: cause_required for everyone; which group (tagged / random) only for officials."""
    from . import control_burn
    g = control_burn.cause_check(con, r, firms.iso(now()))
    d["cause_required"] = g in ("tagged", "random")
    d["cause_group"] = g
    d["cause_p"] = con.execute("SELECT cause_p FROM incidents WHERE id=?", (r["id"],)).fetchone()[0] if g else None
    if me["role"] == "guard":
        d.pop("cause_group"); d.pop("cause_p")


@app.get("/api/incidents")
def incidents(days: float = 7, status: Optional[str] = None, me=Depends(current)):
    where, args = scope_sql(me)
    q = f"""SELECT i.*, (SELECT max(recheck) FROM reports WHERE incident_id=i.id) AS recheck
            FROM incidents i WHERE {where} AND i.first_seen_utc <= ?
            AND (i.last_seen_utc >= ? OR i.status IN ('new','revisit'))"""   # open work is always listed
    args += [firms.iso(now()), firms.iso(now() - timedelta(days=days))]   # replays: nothing after the replay clock
    if status:
        q += " AND i.status = ?"
        args.append(status)
    with db.tx() as con:
        rows = con.execute(q + " ORDER BY i.first_seen_utc DESC LIMIT 2000", args).fetchall()
        out = [inc_row(r, con) for r in rows]
        from . import big_fire
        for r, d in zip(rows, out):
            cause_fields(con, r, d, me)
            d["big_fire_flag"] = big_fire.guard_flag(con, r, firms.iso(now()))   # guards too (Akkshay, 18 Oct 2026); never raises
        from . import scars   # scar per alert; outlines too when the list is small enough for the map
        if me["role"] == "guard":   # burn scars are for officials to monitor, not a guard task
            return out
        geo = len(rows) <= 400
        from . import control_burn, direction, still_burning, runway
        from .hint import safe   # a broken hint is left off, the list is still shown
        nu = firms.iso(now())
        for r, d in zip(rows, out):
            d["control_burn"] = safe(control_burn.check, con, r, nu)
            d["big_fire"] = safe(big_fire.check, con, r, nu)    # officials: points and items, never a % (Akkshay, 18 Oct 2026)
            d["direction"] = safe(direction.for_incident, con, r["id"], now())   # 30 m scene arrow, officials only (18 Oct 2026)
            d["still_burning"] = safe(still_burning.check, con, r["id"], now())   # officials only (18 Oct 2026)
            d["runway"] = safe(runway.for_incident, con, r["id"])   # which side likely burns farther, officials only (18 Oct 2026)
        new = [(safe(big_fire.order_key, con, r, nu, default=(2, 0.0)), r["first_seen_utc"], d) for r, d in zip(rows, out)
               if d.get("big_fire") and d["big_fire"].get("new_fire")]
        for k, (_, _, d) in enumerate(sorted(new, key=lambda x: x[:2])):
            d["big_fire"] = dict(d["big_fire"], order_rank=k + 1)    # the brief's order (big_fire.order_key), as a rank only
        for d in out:
            pts = con.execute("SELECT lat, lon, acq_utc FROM detections WHERE incident_id=?", (d["id"],)).fetchall()
            d["burn_scar"] = safe(scars.for_points, pts, with_geometry=geo)
        return out


@app.get("/api/incidents/{iid}")
def incident(iid: int, me=Depends(current)):
    where, args = scope_sql(me)
    with db.tx() as con:
        r = con.execute(f"SELECT i.* FROM incidents i WHERE i.id=? AND {where}", [iid] + args).fetchone()
        if not r:
            raise HTTPException(404)
        arrived_by = con.execute("SELECT name FROM staff WHERE id=?", (r["arrived_by"],)).fetchone() if r["arrived_by"] else None
        dets = [dict(x) for x in con.execute("SELECT * FROM detections WHERE incident_id=? ORDER BY acq_utc", (iid,))]
        reps = []
        for rp in con.execute("""SELECT r.*, s.name AS staff_name, s.role AS staff_role FROM reports r
                                 JOIN staff s ON s.id=r.staff_id WHERE incident_id=? ORDER BY submitted_utc""", (iid,)):
            rp = dict(rp)
            rp["flags"] = json.loads(rp["flags"] or "[]")
            rp["linked_alerts"] = json.loads(rp["linked_alerts"]) if rp["linked_alerts"] else None
            rp["photos"] = [dict(p, flags=json.loads(p["flags"] or "[]"), path=None, thumb=None)
                            for p in con.execute("SELECT * FROM photos WHERE report_id=?", (rp["id"],))]
            reps.append(rp)
        revs = [dict(x) for x in con.execute("""SELECT v.*, s.name AS reviewer FROM reviews v JOIN staff s ON s.id=v.reviewer_id
                                                 WHERE incident_id=? ORDER BY utc""", (iid,))]
        row = inc_row(r, con)
        row["arrived_by_name"] = arrived_by["name"] if arrived_by else None
        row["near_recent"] = firms.near_recent(con, r)
        cause_fields(con, r, row, me)
        from . import big_fire
        row["big_fire_flag"] = big_fire.guard_flag(con, r, firms.iso(now()))
        row["big_fire_text"] = big_fire.GUARD_TEXT if row["big_fire_flag"] else None
        from .hint import safe
        if me["role"] != "guard":   # officials only (Akkshay, 16 Oct 2026)
            from . import control_burn
            row["control_burn"] = safe(control_burn.check, con, r, firms.iso(now()))
            from . import big_fire
            row["big_fire"] = safe(big_fire.check, con, r, firms.iso(now()))
            from . import direction
            row["direction"] = safe(direction.for_incident, con, r["id"], now())
            from . import still_burning
            row["still_burning"] = safe(still_burning.check, con, r["id"], now())
            from . import runway
            row["runway"] = safe(runway.for_incident, con, r["id"])
            from . import spread24   # likely burnt ground 24 h after the latest VIIRS look, officials only (19 Oct 2026)
            row["spread_24h"] = safe(spread24.for_incident, con, r["id"], now()) if (r["kind"] or "alert") == "alert" else None
    from . import scars
    fsi = next((x for x in dets if x.get("fsi_beat")), None)
    if me["role"] != "guard":   # officials only, as in the list
        row["burn_scar"] = safe(scars.for_points, dets, with_geometry=True)
    return row | {"detections": dets, "reports": reps, "reviews": revs,
                  "fsi_compartments": sorted({x["fsi_compartment"] for x in dets if x.get("fsi_compartment")}),
                  "fsi_beat": fsi and fsi["fsi_beat"]}


@app.get("/api/detections.geojson")
def detections(days: float = 3, me=Depends(current)):
    """All detections in the region, including outside beats (mostly farm fires), for the map. Guards: around their beat."""
    q, args = "SELECT id,instrument,source,lat,lon,acq_utc,confidence,frp,beat_uid,incident_id,forest_share FROM detections WHERE acq_utc >= ?", [firms.iso(now() - timedelta(days=days))]
    if me["role"] == "guard":
        f = next((f for f in BEATS.fc["features"] if f["properties"]["beat_uid"] == me["beat_uid"]), None)
        if not f:
            return {"type": "FeatureCollection", "features": []}
        from shapely.geometry import shape
        x0, y0, x1, y1 = shape(f["geometry"]).bounds
        q += " AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
        args += [y0 - 0.1, y1 + 0.1, x0 - 0.1, x1 + 0.1]   # the beat plus ~10 km
    with db.tx() as con:
        rows = con.execute(q, args).fetchall()
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
         "properties": {k: r[k] for k in r.keys() if k not in ("lat", "lon")}} for r in rows]}


@app.get("/api/beats.geojson")
def beats_geojson(bbox: Optional[str] = None, me=Depends(current)):
    """Beat outlines: inside the map view (bbox=x0,y0,x1,y1), else the signed-in person's own area."""
    if bbox:
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(400, "bbox must be x0,y0,x1,y1")
        return BEATS.in_box(x0, y0, x1, y1)
    uids = set()
    if me["role"] == "guard":
        uids = {me["beat_uid"]}
    elif me["role"] == "ranger":
        uids = set(BEATS.in_range(me["range_name"]))
    feats = [f for f in BEATS.fc["features"] if f["properties"]["beat_uid"] in uids]
    return {"type": "FeatureCollection", "features": feats}


# ---------- positions: route to the fire and auto "reached" ----------
class Position(BaseModel):
    lat: float
    lon: float
    acc_m: Optional[float] = None
    utc: Optional[str] = None
    device_id: Optional[str] = None
    mock_location: Optional[bool] = None


@app.post("/api/positions")
def post_positions(body: List[Position], me=Depends(current)):
    """The field page sends the phone's position about once a minute while open (queued when offline).
    The first time a phone comes within FS_ARRIVE_KM of an open alert's fire point, the alert is marked reached."""
    if len(body) > MAX_POSITIONS:
        raise HTTPException(413, f"send at most {MAX_POSITIONS} positions per request")
    where, args = scope_sql(me)
    pos = [p.dict() for p in body]
    reached = db.write(lambda con: record_positions(con, me["id"], where, args, pos))   # retried on a locked database
    push("alert.reached", reached)
    return {"reached": reached}


MAX_POSITIONS = 1000


def parse_time(s):
    """UTC from a phone or a platform: '...Z', '+00:00' / other offsets, or naive (taken as UTC); ValueError otherwise."""
    if not isinstance(s, str):
        raise ValueError("not a time")
    t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def record_positions(con, staff_id, where, args, positions):
    reached = []
    open_inc = con.execute(f"""SELECT i.* FROM incidents i WHERE {where} AND i.status IN ('new','revisit')
                               AND i.arrived_utc IS NULL""", args).fetchall()
    places = {r["id"]: pilot.Place.of(con, r) for r in open_inc}   # fire points, or the predicted cell
    since = {r["id"]: (r["due_from_utc"] if (r["kind"] or "alert") == "predicted" and r["due_from_utc"] else r["first_seen_utc"])
             for r in open_inc}   # a fix from before the alert (offline queue, slow phone clock) never reaches it
    t_now, stored = now(), []
    for p in positions:
        try:
            t = parse_time(p["utc"]) if p.get("utc") else t_now
        except ValueError:
            continue                                   # skip one bad fix, never fail the batch
        acc = evidence.num(p.get("acc_m"), 0, 1e6)
        if t > t_now + timedelta(minutes=10) or evidence.num(p.get("lat"), -90, 90) is None or evidence.num(p.get("lon")) is None:
            continue
        ts = firms.iso(t); stored.append(ts)
        con.execute("INSERT INTO positions(staff_id,device_id,utc,lat,lon,acc_m) VALUES (?,?,?,?,?,?)",
                    (staff_id, p.get("device_id"), ts, p["lat"], p["lon"], acc))
        if acc is None or acc > 100:
            continue   # too rough (or unknown) to count as reaching the spot
        if p.get("mock_location") or acc == 0:
            continue   # faked or fake-looking position
        for iid, pl in places.items():
            if iid not in reached and ts >= since[iid] and pl.reached(p["lat"], p["lon"]):
                con.execute("UPDATE incidents SET arrived_utc=?, arrived_by=? WHERE id=? AND arrived_utc IS NULL",
                            (ts, staff_id, iid))
                reached.append(iid)
    if stored:   # positions from a phone's offline queue can change a visit's entry / exit time
        pilot.refresh_sites(con, staff_id, min(stored), max(stored))
    return reached


def push(event, ids):
    """Webhook for changes made in the built-in pages too (eNetra misses them otherwise). Call after the commit."""
    from . import config as c
    if not c.WEBHOOK_URL or not ids:
        return
    from . import webhook
    from .api_v1 import alert_json
    with db.tx() as con:
        out = [alert_json(con, r) for r in (con.execute("SELECT * FROM incidents WHERE id=?", (i,)).fetchone() for i in ids) if r]
    for a in out:
        webhook.send(event, a)


@app.get("/api/incidents/{iid}/route")
def route(iid: int, me=Depends(current)):
    """Positions of the people who reported on this alert, from the first detection to their report."""
    where, args = scope_sql(me)
    with db.tx() as con:
        inc = con.execute(f"SELECT i.* FROM incidents i WHERE i.id=? AND {where}", [iid] + args).fetchone()
        if not inc:
            raise HTTPException(404)
        out = []
        for r in con.execute("SELECT staff_id, max(submitted_utc) AS until FROM reports WHERE incident_id=? GROUP BY staff_id", (iid,)):
            pts = con.execute("SELECT utc, lat, lon FROM positions WHERE staff_id=? AND utc BETWEEN ? AND ? ORDER BY utc",
                              (r["staff_id"], inc["first_seen_utc"], r["until"])).fetchall()
            out.append({"staff_id": r["staff_id"], "points": [[p["lat"], p["lon"], p["utc"]] for p in pts]})
    return out


# ---------- field reports ----------
@app.post("/api/incidents/{iid}/reports")
async def submit_report(iid: int, outcome: str = Form(...), visited_utc: Optional[str] = Form(None),
                        device_lat: Optional[float] = Form(None), device_lon: Optional[float] = Form(None),
                        device_acc_m: Optional[float] = Form(None), land_type: Optional[str] = Form(None), fire_type: Optional[str] = Form(None),
                        area_ha: Optional[float] = Form(None), cause: Optional[str] = Form(None),
                        action: Optional[str] = Form(None), crew: Optional[int] = Form(None),
                        notes: Optional[str] = Form(None), photo_meta: str = Form("[]"),
                        device_id: Optional[str] = Form(None), first_known_by: Optional[str] = Form(None),
                        fire_out_utc: Optional[str] = Form(None), burn_age: Optional[str] = Form(None),
                        crosses_beat_boundary: Optional[str] = Form(None), beats_touched: Optional[str] = Form(None),
                        suppression: Optional[str] = Form(None), suppression_utc: Optional[str] = Form(None),
                        people_met: Optional[str] = Form(None), enforcement: Optional[str] = Form(None),
                        client_ref: Optional[str] = Form(None),
                        photos: List[UploadFile] = File(default=[]), me=Depends(current)):
    raw, meta = await read_photos(photos), load_meta(photo_meta)
    where, args = scope_sql(me)

    def go(con):   # retried on a locked database (client_ref makes a retry after a commit a no-op)
        inc = con.execute(f"SELECT i.* FROM incidents i WHERE i.id=? AND {where}", [iid] + args).fetchone()
        if not inc:
            raise HTTPException(404, "alert not found in your area")
        return record_report(con, inc, me["id"], dict(
            outcome=outcome, visited_utc=visited_utc, device_lat=device_lat, device_lon=device_lon, device_acc_m=device_acc_m,
            land_type=land_type, fire_type=fire_type, area_ha=area_ha, cause=cause, action=action, crew=crew, notes=notes,
            device_id=device_id, first_known_by=first_known_by, fire_out_utc=fire_out_utc, burn_age=burn_age,
            crosses_beat_boundary=crosses_beat_boundary, beats_touched=beats_touched, suppression=suppression,
            suppression_utc=suppression_utc, people_met=people_met, enforcement=enforcement, client_ref=client_ref), raw, meta)
    res = db.write(go)
    if not res.get("duplicate"):
        push("alert.reported", [iid])
    return res


MAX_PHOTO = 15 * 1024 * 1024


async def read_photos(photos):
    """Read at most 6 photos of at most 15 MB each (Starlette has spooled them to disk; never more than limit + 1 byte in RAM)."""
    if len(photos) > 6:
        raise HTTPException(400, "up to 6 photos")
    out = []
    for up in photos:
        b = await up.read(MAX_PHOTO + 1)
        if len(b) > MAX_PHOTO:
            raise HTTPException(413, "photo over 15 MB")
        out.append(b)
    return out


def load_meta(photo_meta):
    try:
        return json.loads(photo_meta or "[]")
    except ValueError:
        raise HTTPException(400, "photo_meta must be JSON")


@app.post("/api/chance_finds")
async def chance_find(outcome: str = Form(...), device_lat: float = Form(...), device_lon: float = Form(...),
                      device_acc_m: Optional[float] = Form(None), visited_utc: Optional[str] = Form(None),
                      land_type: Optional[str] = Form(None), fire_type: Optional[str] = Form(None), area_ha: Optional[float] = Form(None),
                      cause: Optional[str] = Form(None), action: Optional[str] = Form(None), crew: Optional[int] = Form(None),
                      notes: Optional[str] = Form(None), photo_meta: str = Form("[]"), device_id: Optional[str] = Form(None),
                      first_known_by: Optional[str] = Form(None), fire_out_utc: Optional[str] = Form(None),
                      burn_age: Optional[str] = Form(None), crosses_beat_boundary: Optional[str] = Form(None), beats_touched: Optional[str] = Form(None),
                      suppression: Optional[str] = Form(None), suppression_utc: Optional[str] = Form(None),
                      people_met: Optional[str] = Form(None), enforcement: Optional[str] = Form(None), client_ref: Optional[str] = Form(None),
                      photos: List[UploadFile] = File(default=[]), me=Depends(current)):
    """A fire staff came across with no task (on the way to a check, on patrol): reported at the phone's position."""
    raw, meta = await read_photos(photos), load_meta(photo_meta)
    res = db.write(lambda con: record_chance(con, me, dict(
            outcome=outcome, visited_utc=visited_utc, device_lat=device_lat, device_lon=device_lon, device_acc_m=device_acc_m,
            land_type=land_type, fire_type=fire_type, area_ha=area_ha, cause=cause, action=action, crew=crew, notes=notes,
            device_id=device_id, first_known_by=first_known_by, fire_out_utc=fire_out_utc, burn_age=burn_age,
            crosses_beat_boundary=crosses_beat_boundary, beats_touched=beats_touched, suppression=suppression,
            suppression_utc=suppression_utc, people_met=people_met, enforcement=enforcement, client_ref=client_ref), raw, meta))
    if not res.get("duplicate"):
        push("alert.reported", [res["incident_id"]])
    return res


def record_chance(con, staff, f, photos, meta):
    if not isinstance(f, dict):
        raise HTTPException(400, "report must be a JSON object")
    if f.get("outcome") not in pilot.FIRE_OUTCOMES:
        raise HTTPException(400, f"a chance find must be one of {list(pilot.FIRE_OUTCOMES)}")
    if not con.in_transaction:
        con.execute("BEGIN IMMEDIATE")
    old = _resent(con, staff["id"], f)
    if old:   # a resend of a chance find already stored: no second incident
        return old | {"incident_id": old["_incident_id"], "beat_uid": old["_beat_uid"]}
    lat, lon = evidence.num(f.get("device_lat"), -90, 90), evidence.num(f.get("device_lon"))
    if lat is None or lon is None:
        raise HTTPException(400, "device_lat and device_lon are required")
    f["visited_utc"] = _utc_field(f, "visited_utc")
    inc = pilot.add_chance(con, BEATS, staff, lat, lon, f.get("visited_utc") or firms.iso(now()))
    return record_report(con, inc, staff["id"], f, photos, meta) | {"incident_id": inc["id"], "beat_uid": inc["beat_uid"]}


def _resent(con, staff_id, f):
    """The stored answer when this report (same staff, same client_ref) is already in: a phone resending after a lost answer."""
    ref = f.get("client_ref")
    if not ref:
        return None
    old = con.execute("""SELECT r.*, i.beat_uid AS inc_beat FROM reports r JOIN incidents i ON i.id=r.incident_id
                         WHERE r.staff_id=? AND r.client_ref=?""", (staff_id, str(ref)[:100])).fetchone()
    if not old:
        return None
    return {"report_id": old["id"], "evidence": old["evidence"], "flags": json.loads(old["flags"] or "[]"),
            "distance_km": old["distance_km"], "recheck": bool(old["recheck"]), "fire_id": old["fire_id"],
            "linked_alerts": json.loads(old["linked_alerts"]) if old["linked_alerts"] else None,
            "inspection": old["inspection"], "inspection_spread_m": None, "duplicate": True,
            "_incident_id": old["incident_id"], "_beat_uid": old["inc_beat"]}


def _utc_field(f, k):
    """A time field as 'YYYY-MM-DDTHH:MM:SSZ' (accepts +00:00 and naive UTC), None when empty; 400 when unreadable."""
    if f.get(k) in (None, ""):
        return None
    try:
        return firms.iso(parse_time(f[k]))
    except ValueError:
        raise HTTPException(400, f"{k} must be a UTC time like 2026-04-15T10:00:00Z")


def _clean(f, meta):
    """Validate a report once, for the field page and the /api/v1 integration alike (400 with a reason, never a 500)."""
    if not isinstance(f, dict) or not isinstance(meta, list) or not all(isinstance(m, dict) for m in meta):
        raise HTTPException(400, "report must be a JSON object and photo_meta a list of objects")
    for k in ("visited_utc", "fire_out_utc", "suppression_utc"):
        f[k] = _utc_field(f, k)
    for k, lo, hi in (("device_lat", -90, 90), ("device_lon", -180, 180), ("device_acc_m", 0, 1e6), ("area_ha", 0, 1e5)):
        if f.get(k) in (None, ""):
            f[k] = None
        elif evidence.num(f[k], lo, hi) is None:
            raise HTTPException(400, f"{k} must be a number from {lo} to {hi:g}")
        else:
            f[k] = evidence.num(f[k], lo, hi)
    if f["device_lat"] is None or f["device_lon"] is None:
        f["device_lat"] = f["device_lon"] = None
    if f.get("crew") in (None, ""):
        f["crew"] = None
    elif not str(f["crew"]).isdigit() or int(f["crew"]) > 500:
        raise HTTPException(400, "crew must be a whole number from 0 to 500")
    else:
        f["crew"] = int(f["crew"])
    for k in ("notes", "beats_touched", "land_type", "fire_type", "cause", "action", "first_known_by", "device_id", "client_ref"):
        if f.get(k) is not None and len(str(f[k])) > (4000 if k == "notes" else 300):
            raise HTTPException(400, f"{k} is too long")
    for m in meta:
        if m.get("dev_utc"):
            try:
                m["dev_utc"] = firms.iso(parse_time(m["dev_utc"]))
            except ValueError:
                m["dev_utc"] = None            # unreadable phone time: the photo gets no_time


def record_report(con, inc, staff_id, f, photos, meta):
    """Store a field report and its photos, run the proof checks, move the alert to 'visited'.
    Shared by the built-in field page and the /api/v1 integration (eNetra app)."""
    _clean(f, meta)
    try:
        loaded = [evidence.load_photo(raw) for raw in photos]   # every photo decodes before anything is written
    except evidence.BadPhoto as e:
        raise HTTPException(415, str(e))
    if not con.in_transaction:
        con.execute("BEGIN IMMEDIATE")   # two sends of one report at once: the second sees the first (client_ref)
    old = _resent(con, staff_id, f)
    if old:   # a resend of a report already stored: answer as before, store nothing
        return {k: v for k, v in old.items() if not k.startswith("_")}
    inc = con.execute("SELECT * FROM incidents WHERE id=?", (inc["id"],)).fetchone()   # as of the write lock
    if f.get("outcome") not in OUTCOMES:
        raise HTTPException(400, f"outcome must be one of {sorted(OUTCOMES)}")
    kind = inc["kind"] or "alert"
    if f["outcome"] == "nothing_found" and kind != "predicted":
        raise HTTPException(400, "nothing_found is only for predicted-cell checks; use no_fire for a satellite alert")
    if f.get("burn_age") and f["burn_age"] not in pilot.BURN_AGE:
        raise HTTPException(400, f"burn_age must be one of {list(pilot.BURN_AGE)}")
    if f.get("crosses_beat_boundary") and f["crosses_beat_boundary"] not in pilot.CROSSED:
        raise HTTPException(400, f"crosses_beat_boundary must be one of {list(pilot.CROSSED)}")
    if f.get("suppression") and f["suppression"] not in pilot.SUPPRESSION:
        raise HTTPException(400, f"suppression must be one of {list(pilot.SUPPRESSION)}")
    if f.get("enforcement") and f["enforcement"] not in pilot.ENFORCEMENT:
        raise HTTPException(400, f"enforcement must be one of {list(pilot.ENFORCEMENT)}")
    if f.get("people_met") not in (None, "") and (not str(f["people_met"]).isdigit() or int(f["people_met"]) > 500):
        raise HTTPException(400, "people_met must be a whole number from 0 to 500")
    if len(photos) > 6:
        raise HTTPException(400, "up to 6 photos")
    if f["outcome"] == "controlled_burn" and not f.get("cause"):
        f["cause"] = "Controlled burning / fire line"
    if f["outcome"] in ("active_fire", "burnt_out") and not f.get("cause"):
        from . import control_burn
        if control_burn.cause_check(con, inc, firms.iso(now())) in ("tagged", "random"):
            raise HTTPException(400, "cause is required for this alert (2027 cause check): give the likely cause, or Unknown")
    iid = inc["id"]
    place = pilot.Place.of(con, inc)
    first_seen = firms.parse_utc(inc["first_seen_utc"])
    if kind == "predicted":   # a photo is fine from the start of the check window, not only after the issue time
        first_seen = min(first_seen, firms.parse_utc(inc["due_from_utc"]))
    ts = firms.iso(now())
    late_visit = not config.DEMO_NOW and f.get("visited_utc") and f["visited_utc"] > firms.iso(now() + timedelta(minutes=10))
    if late_visit:
        f["visited_utc"] = ts                   # phone clock ahead: keep the report, flag it
    report_km = place.km(f.get("device_lat"), f.get("device_lon"))
    cur = con.execute("""INSERT INTO reports (incident_id,staff_id,submitted_utc,visited_utc,device_lat,device_lon,device_acc_m,
                         outcome,land_type,fire_type,area_ha,cause,action,crew,notes,distance_km) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (iid, staff_id, ts, f.get("visited_utc") or ts, f.get("device_lat"), f.get("device_lon"), f.get("device_acc_m"),
                       f["outcome"], f.get("land_type"), f.get("fire_type"), f.get("area_ha"), f.get("cause"), f.get("action"),
                       f.get("crew"), f.get("notes"), report_km))
    rid = cur.lastrowid
    photo_flags, photo_pts = [], []
    for k, raw in enumerate(photos):
        if len(raw) > MAX_PHOTO:
            raise HTTPException(413, "photo over 15 MB")
        m = meta[k] if k < len(meta) else {}
        m = dict(m, dev_lat=evidence.num(m.get("dev_lat"), -90, 90), dev_lon=evidence.num(m.get("dev_lon")))
        if m["dev_lat"] is None or m["dev_lon"] is None:
            m["dev_lat"] = m["dev_lon"] = None
        path, thumb, sha, ex = evidence.save_photo(loaded[k], raw, config.PHOTO_DIR / str(iid), f"r{rid}_{k}")
        seen = con.execute("SELECT 1 FROM photos WHERE sha256=?", (sha,)).fetchone()
        km, fl, taken = evidence.check_photo(m, ex, place, first_seen, seen, None if config.DEMO_NOW else now())   # a replay: real photos are "after" its clock
        if m.get("mock_location"):
            fl.append("mock_location")      # reported by a native app (Android isMock)
        photo_flags.append(fl)
        plat, plon = (ex["lat"], ex["lon"]) if ex.get("lat") is not None else (m.get("dev_lat"), m.get("dev_lon"))
        photo_pts.append({"lat": plat, "lon": plon, "utc": firms.iso(taken) if taken else None})
        con.execute("""INSERT INTO photos (report_id,path,thumb,sha256,taken_utc,exif_lat,exif_lon,dev_lat,dev_lon,dev_utc,distance_km,flags)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid, str(path), str(thumb), sha, firms.iso(taken) if taken else None, ex.get("lat"), ex.get("lon"),
                     m.get("dev_lat"), m.get("dev_lon"), m.get("dev_utc"), km, json.dumps(fl)))
    grade, flags = evidence.grade(report_km, photo_flags, len(photos))
    if "mock_location" in flags and grade == "strong":
        grade = "weak"
    if report_km is not None and report_km > place.report_km:
        flags.append("reported_outside_cell" if place.geom is not None else "reported_far_from_fire")
    acc = f.get("device_acc_m")
    if acc is not None and float(acc) == 0:
        flags.append("gps_accuracy_zero")      # typical of fake-GPS apps (ODK field experience)
        grade = "weak" if grade == "strong" else grade
    elif acc is not None and float(acc) > 50:
        flags.append("gps_rough")
    if f.get("device_id") and con.execute("""SELECT 1 FROM reports WHERE device_id=? AND staff_id<>? AND submitted_utc >= ?""",
                                          (f["device_id"], staff_id, firms.iso(now() - timedelta(days=30)))).fetchone():
        flags.append("phone_used_by_other_staff")
    if not inc["arrived_utc"]:
        flags.append("not_auto_reached")
    if late_visit:
        flags.append("visit_time_in_future")
    recheck = int(random.random() < config.RECHECK_SHARE)
    # A fire found on the ground: link it to satellite alerts within 1.5 km in the 3 days before the visit
    # (pilot scoring: "near active fire" vs "new ignition"). The alert's own points don't count.
    linked = None
    if f["outcome"] in pilot.FIRE_OUTCOMES:
        lat, lon = (f["device_lat"], f["device_lon"]) if f.get("device_lat") is not None else (inc["lat"], inc["lon"])
        linked = pilot.recent_alerts(con, float(lat), float(lon), f.get("visited_utc") or ts, exclude=iid)
    insp, spread = (None, None)
    if kind == "predicted":   # arriving in the cell is not the same as inspecting it
        insp, spread = pilot.inspection(con, inc, staff_id, photo_pts, ts)
        if insp != "completed":
            flags.append("inspection_not_shown" if insp == "not_shown" else "arrived_not_inspected")
    if inc["status"] == "verified":   # keep the accepted result; the officer sees the extra report and can send it back
        flags.append("filed_after_accept")
    con.execute("""UPDATE reports SET evidence=?, flags=?, device_id=?, first_known_by=?, fire_out_utc=?, recheck=?, burn_age=?,
                   linked_alerts=?, inspection=?, stream=?, crosses_beat_boundary=?, beats_touched=?, suppression=?,
                   suppression_utc=?, people_met=?, enforcement=?, client_ref=? WHERE id=?""",
                (grade, json.dumps(flags), f.get("device_id"), f.get("first_known_by"), f.get("fire_out_utc"), recheck,
                 f.get("burn_age") or None, None if linked is None else json.dumps(linked), insp, pilot.STREAM_OF.get(kind),
                 f.get("crosses_beat_boundary") or None, f.get("beats_touched") or None, f.get("suppression") or None,
                 f.get("suppression_utc") or None,
                 None if f.get("people_met") in (None, "") else int(f["people_met"]), f.get("enforcement") or None,
                 str(f["client_ref"])[:100] if f.get("client_ref") else None, rid))
    if inc["status"] != "verified":
        con.execute("""UPDATE incidents SET status='visited', outcome=?, first_report_utc=coalesce(first_report_utc, ?)
                       WHERE id=?""", (f["outcome"], ts, iid))
    v = f.get("visited_utc") or ts
    pilot.refresh_sites(con, staff_id, v, v)           # entry / exit of the cell or fire spot, from phone positions
    fire_id = pilot.assign_fire(con, rid) if f["outcome"] in pilot.FIRE_OUTCOMES else None
    return {"report_id": rid, "evidence": grade, "flags": flags, "distance_km": report_km, "recheck": bool(recheck),
            "linked_alerts": linked, "inspection": insp, "inspection_spread_m": spread, "fire_id": fire_id}


@app.get("/api/photos/{pid}")
def photo(pid: int, thumb: bool = True, me=Depends(current)):
    with db.tx() as con:
        p = con.execute("""SELECT p.*, r.incident_id FROM photos p JOIN reports r ON r.id=p.report_id
                           WHERE p.id=?""", (pid,)).fetchone()
    if not p:
        raise HTTPException(404)
    where, args = scope_sql(me)
    with db.tx() as con:
        in_scope = con.execute(f"SELECT 1 FROM incidents i WHERE i.id=? AND {where}", [p["incident_id"]] + args).fetchone()
        in_review = me["role"] in ("ranger", "admin") and con.execute(   # blind fire review is statewide
            "SELECT 1 FROM reports r JOIN fires f ON f.fire_id=r.fire_id WHERE r.id=? AND f.queued=1", (p["report_id"],)).fetchone()
        if not (in_scope or in_review):
            raise HTTPException(404)
    return FileResponse(p["thumb"] if thumb else p["path"])


class Review(BaseModel):
    decision: str            # accept | revisit
    note: Optional[str] = None
    report_id: Optional[int] = None   # the newest report the reviewer looked at (the control room sends it)


def do_review(con, inc, reviewer_id, decision, note, report_id=None):
    """Accept or send back the newest report. Only an alert waiting for a check ('visited') can be decided, only on the
    report the reviewer saw, never by its own author, and only once when two reviewers press at the same moment."""
    if decision not in ("accept", "revisit"):
        raise HTTPException(400, "decision must be accept or revisit")
    iid = inc["id"]
    last = con.execute("SELECT id, staff_id FROM reports WHERE incident_id=? ORDER BY id DESC LIMIT 1", (iid,)).fetchone()
    if not last:
        raise HTTPException(400, "no field report to check")
    if inc["status"] != "visited":
        raise HTTPException(409, f"this alert is '{inc['status']}', not waiting for a check; reload the page")
    if report_id is not None and report_id != last["id"]:
        raise HTTPException(409, "a newer field report came in; reload before deciding")
    if last["staff_id"] == reviewer_id:
        raise HTTPException(403, "you cannot check your own report")
    new = "verified" if decision == "accept" else "revisit"
    due = inc["due_utc"] if new == "verified" else firms.iso(now() + timedelta(hours=config.VISIT_DUE_HOURS))
    if con.execute("UPDATE incidents SET status=?, due_utc=? WHERE id=? AND status='visited'", (new, due, iid)).rowcount != 1:
        raise HTTPException(409, "someone else checked this alert first; reload")
    con.execute("INSERT INTO reviews(incident_id,report_id,reviewer_id,decision,note) VALUES (?,?,?,?,?)",
                (iid, last["id"], reviewer_id, decision, note))


@app.post("/api/incidents/{iid}/review")
def review(iid: int, body: Review, me=Depends(supervisor)):
    where, args = scope_sql(me)
    with db.tx() as con:
        inc = con.execute(f"SELECT i.* FROM incidents i WHERE i.id=? AND {where}", [iid] + args).fetchone()
        if not inc:
            raise HTTPException(404)
        do_review(con, inc, me["id"], body.decision, body.note, body.report_id)
    push("alert.reviewed", [iid])
    return {"ok": True}


# ---------- numbers ----------
@app.get("/api/stats")
def stats(days: float = 30, me=Depends(current)):
    where, args = scope_sql(me)
    since = firms.iso(now() - timedelta(days=days))
    with db.tx() as con:
        rows = con.execute(f"SELECT i.* FROM incidents i WHERE {where} AND i.first_seen_utc >= ?", args + [since]).fetchall()
        rechecks = con.execute(f"""SELECT count(*) FROM incidents i JOIN reports r ON r.incident_id=i.id
                                   WHERE {where} AND r.recheck=1 AND i.status='visited'""", args).fetchone()[0]
        ev = {r["incident_id"]: "strong" for r in con.execute(
            "SELECT DISTINCT incident_id FROM reports WHERE evidence = 'strong'")}
        last_ingest = con.execute("SELECT utc, source, new_rows, error FROM ingest_log ORDER BY id DESC LIMIT 8").fetchall()
        # newest good read per source group, for an honest feed line (an FSI success says nothing about NASA)
        feeds = {k: con.execute(f"SELECT max(utc) FROM ingest_log WHERE error IS NULL AND ({w})").fetchone()[0] for k, w in (
            ("nasa", "source LIKE 'FIRMS%' OR source LIKE 'VIIRS%' OR source LIKE 'MODIS%'"), ("fsi", "source LIKE 'FSI_PORTAL%'"),
            ("bhuvan", "source LIKE 'BHUVAN%'"))}
    by = {}
    tot = {"alerts": 0, "attended": 0, "verified": 0, "overdue": 0, "false_alarm": 0, "strong_proof": 0, "hours": []}
    pil = {"tasks": 0, "tasks_visited": 0, "nothing_found": 0, "fires_found": 0, "chance_finds": 0}
    for r in rows:
        if (r["kind"] or "alert") != "alert":   # pilot tasks and chance finds are counted apart from satellite alerts
            k = r["kind"]
            pil["chance_finds" if k == "chance" else "tasks"] += 1
            if k == "predicted" and r["outcome"]:
                pil["tasks_visited"] += 1
                pil["nothing_found"] += r["outcome"] == "nothing_found"
            pil["fires_found"] += r["outcome"] in pilot.FIRE_OUTCOMES
            continue
        rng = BEATS.by_uid.get(r["beat_uid"], {}).get("range", "?")
        for key in (rng, "_all"):
            b = by.setdefault(key, {"alerts": 0, "attended": 0, "verified": 0, "overdue": 0, "false_alarm": 0, "strong_proof": 0, "hours": []})
            b["alerts"] += 1
            if r["first_report_utc"]:
                b["attended"] += 1
                b["hours"].append((firms.parse_utc(r["first_report_utc"]) - firms.parse_utc(r["first_seen_utc"])).total_seconds() / 3600)
            b["verified"] += r["status"] == "verified"
            b["overdue"] += overdue(r)
            b["false_alarm"] += r["outcome"] in ("no_fire", "outside_forest")
            b["strong_proof"] += ev.get(r["id"]) == "strong"
    for b in by.values():
        h = sorted(b.pop("hours"))
        b["median_hours_to_visit"] = round(h[len(h) // 2], 1) if h else None
    tot = by.pop("_all", tot)
    tot.pop("hours", None)
    outcomes = {}
    for r in rows:
        if r["outcome"] and (r["kind"] or "alert") == "alert":
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    tot["rechecks_pending"] = rechecks
    with db.tx() as con:
        sh = con.execute(f"""SELECT s.* FROM shifts s JOIN staff st ON st.id = s.staff_id WHERE s.start_utc >= ?""", (since,)).fetchall()
    pil["staff_hours"] = round(sum(pilot.shift_hours(x, firms.iso(now())) * (x["crew_size"] or 1) for x in sh), 1)
    pil["crew_days"] = len(sh)
    return {"days": days, "total": tot, "pilot": pil, "by_range": by, "outcomes": outcomes, "ingest": [dict(x) for x in last_ingest],
            "feeds": feeds | {"fsi_on": config.FSI_PORTAL, "bhuvan_on": config.BHUVAN}}


@app.get("/api/export/incidents.csv")
def export(days: float = 365, me=Depends(supervisor)):
    """One row per alert with its latest field report: the ground-truth table for the research threads."""
    where, args = scope_sql(me)
    with db.tx() as con:
        rows = con.execute(f"""SELECT i.*, (SELECT group_concat(beat_uid) FROM incident_beats b WHERE b.incident_id=i.id) AS all_beats,
                               CASE WHEN r.outcome IN ('active_fire','burnt_out','controlled_burn') THEN 'yes'
                                    WHEN r.outcome IN ('no_fire','outside_forest') THEN 'no' END AS fsi_fire_yes_no,
                               r.outcome AS report_outcome, r.land_type, r.fire_type, r.area_ha, r.cause, r.action, r.crew,
                               r.visited_utc, r.fire_out_utc, r.first_known_by, r.evidence, r.flags, r.recheck, r.burn_age, r.linked_alerts, r.inspection, r.stream AS report_stream, r.crosses_beat_boundary, r.beats_touched, r.suppression, r.suppression_utc,
                               r.fire_id, r.site_entry_utc, r.site_exit_utc, r.people_met, r.enforcement, r.distance_km, r.device_lat, r.device_lon
                               FROM incidents i LEFT JOIN reports r ON r.id = (SELECT max(id) FROM reports WHERE incident_id=i.id)
                               WHERE {where} AND i.first_seen_utc >= ? ORDER BY i.first_seen_utc""",
                           args + [firms.iso(now() - timedelta(days=days))]).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    if rows:
        cols = [k for k in rows[0].keys() if k != "cell_geom"]   # the cell is cell_id; polygons via /api/v1/alerts
        w.writerow(cols + ["beat_name", "range", "block"])
        B = pilot.blocks()
        for r in rows:
            p = BEATS.by_uid.get(r["beat_uid"], {})
            w.writerow([csv_cell(r[k]) for k in cols] + [p.get("beat", ""), p.get("range", ""), B.get(r["beat_uid"], "")])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=field_checks.csv"})


# ---------- patrol pilot: crew-day log, predicted-cell tasks, season report ----------
class ShiftIn(BaseModel):
    crew_size: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    utc: Optional[str] = None
    device_id: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/shifts/current")
def shift_current(me=Depends(current)):
    with db.tx() as con:
        s = con.execute("SELECT * FROM shifts WHERE staff_id=? AND end_utc IS NULL ORDER BY id DESC LIMIT 1", (me["id"],)).fetchone()
    return dict(s) if s else None


@app.post("/api/shifts/start")
def shift_start(body: ShiftIn, me=Depends(current)):
    with db.tx() as con:
        return pilot.shift_start(con, me["id"], body.dict() | {"start_utc": body.utc}, firms.iso(now()))


@app.post("/api/shifts/end")
def shift_end(body: ShiftIn, me=Depends(current)):
    with db.tx() as con:
        s = pilot.shift_end(con, me["id"], body.dict() | {"end_utc": body.utc}, firms.iso(now()))
    if not s:
        raise HTTPException(400, "no day started")
    return s


@app.post("/api/tasks")
def add_tasks(body: dict, me=Depends(supervisor)):
    """Predicted-cell check tasks (the evening list). Same JSON as POST /api/v1/tasks; admins only."""
    if me["role"] != "admin":
        raise HTTPException(403, "admins only")
    try:
        with db.tx() as con:
            return pilot.add_tasks(con, BEATS, body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/pilot/report")
def pilot_report(start: str, end: str, me=Depends(supervisor)):
    """Per arm: tasks, fires found (new vs near active fire), chance finds, staff-hours, and alerts missed (no visit within 2 days)."""
    from . import scars
    with db.tx() as con:
        return pilot.report(con, BEATS, start, end, firms.iso(now()), scars)


@app.get("/api/pilot/missed.csv")
def pilot_missed(start: str, end: str, me=Depends(supervisor)):
    rep = pilot_report(start, end, me)
    buf = io.StringIO()
    if rep["missed"]:
        w = csv.DictWriter(buf, fieldnames=list(rep["missed"][0].keys()))
        w.writeheader()
        w.writerows({k: csv_cell(v) for k, v in r.items()} for r in rep["missed"])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=missed_fires_{start}_{end}.csv"})


def csv_cell(v):
    """Text that Excel would run as a formula (= + - @) gets a leading quote; numbers are left alone."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def _csv(rows, name):
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows({k: csv_cell(v) for k, v in r.items()} for r in rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={name}"})


@app.get("/api/pilot/shakedown")
def pilot_shakedown(start: str = "2027-01-25", end: str = "2027-02-07", me=Depends(supervisor)):
    """Launch gate per arm (protocol v3 section 0.3): complete shift logs, phone-position coverage, unassigned hours."""
    with db.tx() as con:
        return pilot.shakedown(con, start, end, firms.iso(now()))


@app.get("/api/pilot/beats.csv")
def pilot_beats(start: str, end: str, me=Depends(supervisor)):
    """One row per pilot beat: block, arm, confirmed starts by stream, person-hours by stream and component."""
    with db.tx() as con:
        return _csv(pilot.beat_csv(con, start, end, firms.iso(now())), f"pilot_beats_{start}_{end}.csv")


@app.post("/api/pilot/grouping")
def pilot_grouping(body: List[dict], me=Depends(supervisor)):
    """Post-season fire grouping (admins): [{fire_id, grouping, fire_first_utc, est_ignition_utc, merge_into, chips}]."""
    if me["role"] != "admin":
        raise HTTPException(403, "admins only")
    with db.tx() as con:
        return pilot.import_grouping(con, body, firms.iso(now()))


@app.get("/api/review/fires")
def review_fires(me=Depends(supervisor)):
    """Blind review queue: fires where field burn age and the satellite grouping disagree. No arm or beat shown."""
    from . import scars
    with db.tx() as con:
        return pilot.review_queue(con, me["id"], scars)


class Verdict(BaseModel):
    verdict: str
    reason: str


@app.post("/api/review/fires/{fid}/verdict")
def review_fire_verdict(fid: str, body: Verdict, me=Depends(supervisor)):
    try:
        with db.tx() as con:
            con.execute("BEGIN IMMEDIATE")   # two reviewers at the same instant are counted one after the other
            return pilot.add_verdict(con, fid, me["id"], body.verdict, body.reason, firms.iso(now()))
    except ValueError as e:
        raise HTTPException(400, str(e))


class QueueIn(BaseModel):
    reason: str


@app.post("/api/review/fires/{fid}/queue")
def review_fire_queue(fid: str, body: QueueIn, me=Depends(supervisor)):
    """Admins can send any fire to the blind review with a reason."""
    if me["role"] != "admin":
        raise HTTPException(403, "admins only")
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM fires WHERE fire_id=?", (fid,)).fetchone():
            raise HTTPException(404)
        con.execute("UPDATE fires SET queue_reason=? WHERE fire_id=?", ("manual: " + body.reason.strip(), fid))
        pilot.refresh_fire(con, fid)
    return {"ok": True}


def _brief_division(me, division):
    """Range officers get their own division; admins pick one (None = statewide)."""
    if me["role"] == "ranger":
        uids = BEATS.in_range(me["range_name"])
        if not uids:      # a ranger whose range is not in the beat map must not get the statewide page
            raise HTTPException(403, "your range is not in the beat map; ask an admin")
        return BEATS.by_uid[uids[0]].get("division")
    return division


@app.get("/api/brief")
def brief_json(division: Optional[str] = None, day: Optional[str] = None, me=Depends(supervisor)):
    """Officials' daily brief (16:00 IST). day = IST date; default the latest brief."""
    from . import brief
    t, d = brief.clock_for(day, now()), _brief_division(me, division)
    with db.tx() as con:
        return brief.build(con, d, t, BEATS) if d else {"clock_utc": firms.iso(t), "divisions": brief.statewide(con, t, BEATS)}


@app.get("/brief", response_class=HTMLResponse)
def brief_page(division: Optional[str] = None, day: Optional[str] = None, me=Depends(supervisor)):
    from . import brief
    t, d = brief.clock_for(day, now()), _brief_division(me, division)
    with db.tx() as con:
        if d:
            return brief.render(brief.build(con, d, t, BEATS))
        return brief.render_state(brief.statewide(con, t, BEATS), (t + brief.IST).strftime("%d %b %Y, %H:%M IST"))


@app.get("/scar-check", response_class=HTMLResponse)
def scar_check_page(division: Optional[str] = None, day: Optional[str] = None, me=Depends(supervisor)):
    """Weekly scar check (officials): the week that ended 7 days before `day` (IST date, default today)."""
    from . import scar_check
    d = _brief_division(me, division)
    day = day or (now() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    with db.tx() as con:
        w = scar_check.week(con, BEATS, day, d)
    return scar_check.render(w, f"Scar check: {d.replace('_', ' ')} division" if d else "Scar check: Madhya Pradesh")


@app.get("/review", response_class=HTMLResponse)
def review_page():
    return (STATIC / "review.html").read_text(encoding="utf-8")


@app.post("/api/ingest")
def ingest_now(me=Depends(supervisor)):
    if config.DEMO_NOW:   # a replay must not pull today's live alerts
        raise HTTPException(409, "replay database: live feeds are off")
    out = firms.run_live(BEATS, "24h", wait=False)   # never a second poll alongside the poller's
    if "busy" in out:
        raise HTTPException(409, "a poll is running now; try again in a few minutes")
    return out


@app.get("/healthz")
def healthz():
    """Plain liveness for the container's health check (no key, no data). The monitor's detail is GET /api/v1/health."""
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "control.html").read_text(encoding="utf-8")


@app.get("/field", response_class=HTMLResponse)
def field():
    return (STATIC / "field.html").read_text(encoding="utf-8")


from . import api_v1  # noqa: E402  (registers /api/v1 routes on app)
