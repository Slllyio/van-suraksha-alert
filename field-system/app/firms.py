"""Pull NASA FIRMS active-fire points, keep those in the region, assign beats, group into incidents.

Live feed: NASA's public near-real-time files (no key), refreshed by NASA within
~3 h of each overpass. Four sensors: VIIRS on Suomi-NPP, NOAA-20, NOAA-21 (375 m)
and MODIS on Terra/Aqua (1 km). These are the same satellites FSI's alerts use.
FSI's own alerts (with FSI beat and compartment) are added from its open portal, see fsi_portal.py.
NRSC's Bhuvan panel sends S-NPP, NOAA-20 and Aqua passes about an hour after the pass, see bhuvan.py.
"""
import csv, io, logging, math, threading, time, urllib.request
from datetime import datetime, timedelta, timezone
from . import config, db
from .geo import haversine_km
from .landcover import WorldCover

_WC = None
_WC_DOWN_UNTIL = 0.0   # after a WorldCover failure, no 60 s retry per point for 10 min
SEEN_SQL = "SELECT 1 FROM detections WHERE instrument=? AND satellite=? AND lat=? AND lon=? AND acq_utc=?"
LOCK = threading.RLock()        # one store at a time in this process (sources fetch in parallel, see run_live)
_RUN = threading.Lock()         # one run_live at a time (poller and /api/ingest)


def forest_share(d, fails=None):
    """Tree + shrub share in the pixel footprint, or None if WorldCover can't be read (then keep the point;
    the failure is counted in `fails` and in ingest_log.forest_unknown)."""
    global _WC, _WC_DOWN_UNTIL
    if time.monotonic() >= _WC_DOWN_UNTIL:
        try:
            _WC = _WC or WorldCover()
            s = _WC.share(d["lat"], d["lon"], FOOTPRINT_KM[d["instrument"]])
            return None if s is None else round(s[1], 3)
        except Exception:
            log.exception("worldcover read failed, forest filter off for 10 min")
            _WC_DOWN_UNTIL = time.monotonic() + 600
    if fails is not None:
        fails.append(1)
    return None

log = logging.getLogger("firms")
FOOTPRINT_KM = {"VIIRS": 0.19, "MODIS": 0.5}
BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
FEEDS = {
    "VIIRS_SNPP": ("VIIRS", "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_{r}_{w}.csv"),
    "VIIRS_NOAA20": ("VIIRS", "noaa-20-viirs-c2/csv/J1_VIIRS_C2_{r}_{w}.csv"),
    "VIIRS_NOAA21": ("VIIRS", "noaa-21-viirs-c2/csv/J2_VIIRS_C2_{r}_{w}.csv"),
    "MODIS": ("MODIS", "modis-c6.1/csv/MODIS_C6_1_{r}_{w}.csv"),
}


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def normalise(row, source, instrument):
    t = str(int(float(row["acq_time"]))).zfill(4)   # pandas reads 800 as 800.0 when the column has a blank
    acq = datetime.strptime(f"{row['acq_date']} {t}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
    conf = str(row.get("confidence", ""))
    if instrument == "MODIS" and conf.isdigit():   # MODIS confidence is 0-100
        c = int(conf)
        conf = "low" if c < 30 else ("nominal" if c < 80 else "high")
    conf = {"l": "low", "n": "nominal", "h": "high"}.get(conf, conf)
    return dict(source=source, instrument=instrument, satellite=row.get("satellite", ""),
                lat=round(float(row["latitude"]), 5), lon=round(float(row["longitude"]), 5),
                acq_utc=iso(acq), confidence=conf, frp=float(row.get("frp") or 0),
                daynight=row.get("daynight", ""),
                bright=float(row.get("bright_ti4") or row.get("brightness") or 0),
                scan=float(row.get("scan") or 0), track=float(row.get("track") or 0))


def in_bbox(d):
    x0, y0, x1, y1 = config.BBOX
    return x0 <= d["lon"] <= x1 and y0 <= d["lat"] <= y1


def http_get(req, timeout=30, deadline=180):
    """GET with a total deadline: urlopen's timeout is per socket read, so a trickling server never trips it."""
    end = time.monotonic() + deadline
    buf = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        while chunk := r.read1(1 << 16):
            buf.append(chunk)
            if time.monotonic() > end:
                raise TimeoutError(f"download over {deadline} s")
    return b"".join(buf)


def parse_rows(text, need, make, what, empty_ok=False):
    """Rows of a CSV, one by one: a bad row is skipped and counted, not the whole file. An HTML page, an empty
    file or a header without the columns we need raises (logged in ingest_log, not stored as 'no fires')."""
    rd = csv.DictReader(io.StringIO(text))
    miss = [c for c in need if c not in (rd.fieldnames or [])]
    if miss:
        raise ValueError(f"not a {what} CSV (HTML or empty file?): no {', '.join(miss)} in {text[:80]!r}")
    out, bad = [], 0
    for row in rd:
        try:
            if None in row or None in row.values() or any(row[c] in (None, "") for c in need):
                raise ValueError("incomplete row")
            out.append(make(row))
        except (KeyError, ValueError, TypeError, IndexError):
            bad += 1
    if bad:
        log.warning("%s: skipped %d malformed rows of %d", what, bad, bad + len(out))
    if not out and (bad or not empty_ok):
        raise ValueError(f"{what}: no usable rows ({bad} malformed)")
    return out


NEED = ("latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence")


def fetch_feed(source, window="24h"):
    instrument, path = FEEDS[source]
    url = f"{BASE}/{path.format(r=config.FIRMS_REGION, w=window)}"
    text = http_get(url).decode("utf-8-sig")

    def make(r):   # a line cut short has missing columns (caught above) or a cut acq_time
        if not str(r["acq_time"]).isdigit():
            raise ValueError("bad acq_time")
        return normalise(r, source, instrument)
    return parse_rows(text, NEED, make, source)   # a South Asia 24 h file is never empty, in season or out of it


_MASK = None
EARLY = ("FSI_PORTAL", "BHUVAN")   # sources that can send a pixel before FIRMS does


def mask():
    global _MASK
    if _MASK is None:
        from .geo import Mask
        try:
            _MASK = Mask()
            if not _MASK.geoms:
                log.warning("industry mask %s missing or empty: mines and kilns are not masked", config.MASK_PATH)
        except Exception:   # a truncated file must not fail every source on every poll
            log.exception("industry mask %s unreadable: mines and kilns are not masked", config.MASK_PATH)
            _MASK = Mask(path=config.DATA_DIR / "no-such-mask.geojson")
    return _MASK


def store(rows, beats, source_label, tasks=True):
    """Insert new detections, assign beats, group beat detections into incidents.
    tasks=False (archive imports): store the points for persistent heat and the hints, open no field tasks."""
    fetched = len(rows)
    rows = sorted((d for d in rows if in_bbox(d) and d.get("instrument") in FOOTPRINT_KM), key=lambda d: d["acq_utc"])
    new_rows = new_inc = 0
    touched = set()
    # WorldCover is read over HTTP (0.3-2 s a point). Read it before the write transaction: inside it every
    # API write (reports, positions, reviews) waits on the lock and fails after 30 s.
    shares, fails = {}, []
    if config.FOREST_FILTER:
        with db.tx() as ro:
            for d in rows:
                k = (d["instrument"], d["lat"], d["lon"])
                if (d["source"] != "FSI_PORTAL" and k not in shares
                        and beats.touching(d["lat"], d["lon"], FOOTPRINT_KM[d["instrument"]])
                        and not ro.execute(SEEN_SQL, (d["instrument"], d["satellite"], d["lat"], d["lon"], d["acq_utc"])).fetchone()):
                    shares[k] = forest_share(d, fails)
    with LOCK, db.tx() as con:
        con.execute("BEGIN IMMEDIATE")   # the write lock up front: no 'locked' half way when another writer got in first
        for d in rows:
            if con.execute(SEEN_SQL, (d["instrument"], d["satellite"], d["lat"], d["lon"], d["acq_utc"])).fetchone():
                continue   # seen in an earlier poll
            official = d["source"] == "FSI_PORTAL"
            if not official:
                from . import fsi_portal
                early = fsi_portal.match(con, d)
                row = early and con.execute("SELECT source, scan FROM detections WHERE id=?", (early,)).fetchone()
                src = row and row["source"]
                if src in EARLY and d["source"] not in EARLY and not row["scan"]:
                    # FSI or Bhuvan sent this pixel before FIRMS did: keep their row (and its alert), take FIRMS'
                    # measurements, position and time, so the next poll of the same FIRMS file finds it as seen
                    con.execute("""UPDATE detections SET satellite=?, confidence=?, frp=?, daynight=?, bright=?, scan=?, track=?,
                                   lat=?, lon=?, acq_utc=? WHERE id=?""",
                                (d["satellite"], d["confidence"], d["frp"], d["daynight"], d["bright"], d["scan"], d["track"],
                                 d["lat"], d["lon"], d["acq_utc"], early))
                    # Bhuvan's granule time is a few minutes after the scan: the alert's first look moves back to it
                    # (and the due time with it: 17:57 IST is a day look, 18:04 a night one)
                    con.execute("""UPDATE incidents SET due_utc = min(due_utc, ?), first_seen_utc = min(first_seen_utc, ?),
                                   max_frp = max(coalesce(max_frp,0), ?),
                                   sensors = CASE WHEN instr(sensors, ?) THEN sensors ELSE sensors || ',' || ? END
                                   WHERE id = (SELECT incident_id FROM detections WHERE id = ?)""",
                                (iso(due_for(parse_utc(d["acq_utc"]))), d["acq_utc"], d["frp"], d["source"], d["source"], early))
                    continue
                if src and d["source"] == "BHUVAN":
                    continue   # Bhuvan point for a pixel already stored (FIRMS, FSI, or an earlier read of this pass)
            # FSI: the alert location is the pixel centre, up to ~190 m (VIIRS) / 500 m (MODIS)
            # from the fire, so a pixel overlapping a junction goes to every beat it touches.
            near = beats.touching(d["lat"], d["lon"], FOOTPRINT_KM[d["instrument"]])
            d["beat_uid"] = beats.locate(d["lat"], d["lon"]) or (near[0] if near else None)
            d["beats"] = [d["beat_uid"]] + [b for b in near if b != d["beat_uid"]] if d["beat_uid"] else []
            d["mask_kind"] = (mask().hit(d["lat"], d["lon"]) or persistent_heat(con, d)) if d["beat_uid"] else None
            if official:   # FSI's own alert: FSI has already masked it to forest
                d["mask_kind"] = None
            k = (d["instrument"], d["lat"], d["lon"])
            if d["beat_uid"] and not d["mask_kind"] and config.FOREST_FILTER and not official and k not in shares:
                shares[k] = forest_share(d, fails)   # only if the beat test above missed it (rare)
            d["forest_share"] = (shares[k] if d["beat_uid"] and not d["mask_kind"] and config.FOREST_FILTER
                                 and not official else None)
            cur = con.execute(
                """INSERT OR IGNORE INTO detections
                   (source,instrument,satellite,lat,lon,acq_utc,confidence,frp,daynight,bright,scan,track,beat_uid,forest_share,mask_kind)
                   VALUES (:source,:instrument,:satellite,:lat,:lon,:acq_utc,:confidence,:frp,:daynight,:bright,:scan,:track,:beat_uid,:forest_share,:mask_kind)""", d)
            if cur.rowcount == 0:
                continue
            new_rows += 1
            in_forest = d["forest_share"] is None or d["forest_share"] >= config.FOREST_MIN
            if tasks and d["beat_uid"] and d["confidence"] != "low" and in_forest and not d["mask_kind"]:
                if attach_to_incident(con, cur.lastrowid, d):
                    new_inc += 1
                touched.add(con.execute("SELECT incident_id FROM detections WHERE id=?", (cur.lastrowid,)).fetchone()[0])
        con.execute("INSERT INTO ingest_log(utc,source,fetched,in_bbox,new_rows,new_incidents,forest_unknown) VALUES (?,?,?,?,?,?,?)",
                    (iso(datetime.now(timezone.utc)), source_label, fetched, len(rows), new_rows, new_inc, len(fails) or None))
    if fails:
        log.error("%s: forest filter unavailable for %d points (kept as tasks)", source_label, len(fails))
    if tasks:
        send_updates(touched)
    return new_rows, new_inc


def send_updates(ids):
    """alert.updated for each changed alert. After the commit, and never an error of the feed: the points are stored."""
    if not ids or not config.WEBHOOK_URL:
        return
    from . import webhook
    from .api_v1 import alert_json
    for iid in ids:
        try:
            with db.tx() as con:
                r = con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
                body = r and alert_json(con, r)
            if body:
                webhook.send("alert.updated", body)
        except Exception:
            log.exception("alert.updated for %s not queued", iid)


def persistent_heat(con, d):
    """'persistent_heat' when fire has been seen at this spot on many separate days (a static heat source)."""
    t = parse_utc(d["acq_utc"])
    dlat = config.PERSIST_KM / 111.32
    dlon = dlat / max(math.cos(math.radians(d["lat"])), 0.2)
    n = con.execute("""SELECT count(DISTINCT substr(acq_utc, 1, 10)) FROM detections
                       WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND acq_utc >= ? AND acq_utc < ?""",
                    (d["lat"] - dlat, d["lat"] + dlat, d["lon"] - dlon, d["lon"] + dlon,
                     iso(t - timedelta(days=config.PERSIST_DAYS)), iso(t - timedelta(hours=12)))).fetchone()[0]
    return "persistent_heat" if n >= config.PERSIST_MIN_DAYS else None


def due_for(t):
    """Visit deadline for a new alert: day alerts the same evening (19:30 IST), night alerts at first
    light (09:00 IST next morning), never sooner than 5 h after the pass (feeds arrive 1-6 h late),
    never later than FS_VISIT_DUE_HOURS. Field rule from FSI scouting (diurnal_and_controlled_burns.md)."""
    ist = timezone(timedelta(hours=5, minutes=30))
    lt = t.replace(tzinfo=timezone.utc).astimezone(ist) if t.tzinfo is None else t.astimezone(ist)
    if 6 <= lt.hour < 18:
        rule = lt.replace(hour=19, minute=30, second=0, microsecond=0)
    else:
        rule = (lt if lt.hour < 6 else lt + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    due = min(max(rule, lt + timedelta(hours=5)), lt + timedelta(hours=config.VISIT_DUE_HOURS))
    return due.astimezone(timezone.utc).replace(tzinfo=t.tzinfo)


def near_recent(con, r, km=1.0, days=7):
    """Ids of earlier alerts with a fire point within 1 km in the 7 days before this one (ones not merged
    into it: already visited, or quiet for more than CLUSTER_HOURS): this fire likely spread from them."""
    t0 = parse_utc(r["first_seen_utc"])
    out = set()
    for x in con.execute(
            """SELECT x.incident_id, x.lat, x.lon FROM detections x JOIN incidents i ON i.id = x.incident_id
               WHERE i.id != ? AND i.first_seen_utc < ? AND x.acq_utc >= ?
               AND x.lat BETWEEN ? AND ? AND x.lon BETWEEN ? AND ?""",
            (r["id"], r["first_seen_utc"], iso(t0 - timedelta(days=days)),
             r["lat"] - 0.01, r["lat"] + 0.01, r["lon"] - 0.011, r["lon"] + 0.011)):
        if haversine_km(r["lat"], r["lon"], x["lat"], x["lon"]) <= km:
            out.add(x["incident_id"])
    return sorted(out)


def attach_to_incident(con, det_id, d):
    """Join an open incident nearby in space and time, else open a new one. Returns True if new.

    Open = not yet visited, or a large fire (FSI rule) seen in the last 3 days: large
    fires are tracked as one incident until 3 days after their last detection.
    """
    t = parse_utc(d["acq_utc"])
    lo = iso(t - timedelta(hours=config.CLUSTER_HOURS))
    lo_large = iso(t - timedelta(days=3))
    dl = config.CLUSTER_KM / 110.0      # only detections near the point can be within CLUSTER_KM (cos 27 deg > 1 / 1.2)
    cands = con.execute(
        """SELECT DISTINCT i.id, x.lat, x.lon FROM incidents i JOIN detections x ON x.incident_id = i.id
           WHERE ((i.status IN ('new','revisit') AND i.last_seen_utc >= ?) OR (i.large = 1 AND i.last_seen_utc >= ?))
             AND i.first_seen_utc <= ? AND x.lat BETWEEN ? AND ? AND x.lon BETWEEN ? AND ?""",
        # a point may arrive after a later look of the same fire (Bhuvan granule time, NOAA-21 via NASA, feed order)
        (lo, lo_large, iso(t + timedelta(hours=config.CLUSTER_HOURS)),
         d["lat"] - dl, d["lat"] + dl, d["lon"] - 1.2 * dl, d["lon"] + 1.2 * dl)).fetchall()
    best = None
    for c in cands:
        km = haversine_km(d["lat"], d["lon"], c["lat"], c["lon"])
        if km <= config.CLUSTER_KM and (best is None or km < best[1]):
            best = (c["id"], km)
    if best:
        inc = best[0]
        con.execute("""UPDATE incidents SET n_detections = n_detections + 1,
                       due_utc = CASE WHEN ? < first_seen_utc THEN min(due_utc, ?) ELSE due_utc END,
                       first_seen_utc = min(first_seen_utc, ?),
                       last_seen_utc = max(last_seen_utc, ?), max_frp = max(coalesce(max_frp,0), ?),
                       sensors = CASE WHEN instr(sensors, ?) THEN sensors ELSE sensors || ',' || ? END
                       WHERE id = ?""", (d["acq_utc"], iso(due_for(t)), d["acq_utc"], d["acq_utc"], d["frp"],
                                         d["source"], d["source"], inc))
        con.execute("UPDATE detections SET incident_id = ? WHERE id = ?", (inc, det_id))
        link_beats(con, inc, d["beats"])
        mark_large(con, inc)
        return False
    due = due_for(t)
    late = datetime.now(timezone.utc) - t
    if not config.DEMO_NOW and timedelta(0) <= late < timedelta(hours=config.VISIT_DUE_HOURS):
        due = max(due, datetime.now(timezone.utc) + timedelta(hours=2))   # a pass NASA sends 6 h late is never born overdue
    due = iso(due)
    cur = con.execute("""INSERT INTO incidents (beat_uid,lat,lon,first_seen_utc,last_seen_utc,n_detections,max_frp,sensors,due_utc)
                         VALUES (?,?,?,?,?,1,?,?,?)""",
                      (d["beat_uid"], d["lat"], d["lon"], d["acq_utc"], d["acq_utc"], d["frp"], d["source"], due))
    con.execute("UPDATE detections SET incident_id = ? WHERE id = ?", (cur.lastrowid, det_id))
    link_beats(con, cur.lastrowid, d["beats"])
    return True


def link_beats(con, inc, uids):
    con.executemany("INSERT OR IGNORE INTO incident_beats VALUES (?,?)", [(inc, u) for u in uids])


def mark_large(con, inc):
    """FSI large fire: 3 or more adjacent VIIRS pixels from one overpass (~40 ha or more)."""
    rows = con.execute("""SELECT satellite, acq_utc, lat, lon, scan FROM detections
                          WHERE incident_id = ? AND instrument = 'VIIRS'""", (inc,)).fetchall()
    passes = {}
    for r in rows:
        passes.setdefault((r["satellite"], r["acq_utc"]), []).append((r["lat"], r["lon"], max(r["scan"] or 0, 0.375)))
    for pts in passes.values():
        if len(pts) < 3:
            continue
        # adjacent = centres within ~1.5 pixel widths (the wider of the two: pixels grow to ~0.8 km at the swath edge)
        linked = {0}
        grew = True
        while grew:
            grew = False
            for j, q in enumerate(pts):
                if j not in linked and any(haversine_km(*q[:2], *pts[k][:2]) <= 1.6 * max(q[2], pts[k][2]) for k in linked):
                    linked.add(j)
                    grew = True
        if len(linked) >= 3:
            con.execute("UPDATE incidents SET large = 1 WHERE id = ?", (inc,))
            return


def _log_error(source, e):
    """ingest_log row for a failed source; never raises (a locked DB here must not end the poll)."""
    for i in range(3):
        try:
            with db.tx() as con:
                con.execute("INSERT INTO ingest_log(utc,source,error) VALUES (?,?,?)",
                            (iso(datetime.now(timezone.utc)), source, str(e)[:500] or repr(e)))
            return
        except Exception:
            time.sleep(1 + i)
    log.error("could not log the %s error in ingest_log: %s", source, e)


_SIDE = {}   # Bhuvan / FSI threads of the last poll: a hung one is not started again until it ends


def _side(name, fn, out):
    def go():
        try:
            out[name] = fn()
        except Exception as e:
            log.exception("%s failed", name)
            _log_error(name, e)
            out[name] = str(e) or repr(e)
    t = _SIDE.get(name)
    if t and t.is_alive():
        _log_error(name, RuntimeError("previous read still running (hung download?)"))
        out[name] = "still running"
        return None
    t = _SIDE[name] = threading.Thread(target=go, daemon=True, name=f"ingest-{name}")
    t.start()
    return t


def run_live(beats, window="24h", wait=True):
    """One poll of every source. Bhuvan, FSI and the four NASA files download in parallel, each with its own deadline,
    so a hung source holds back no other; stores run one at a time (LOCK). NASA's four files are stored as one
    time-sorted list, so a look is grouped in time order whatever file it came in. Returns {source: result}."""
    if not _RUN.acquire(blocking=wait):
        return {"busy": "another poll is running"}
    try:
        out, side = {}, []
        if config.BHUVAN:   # NRSC's panel has passes 1-5 h before NASA's files
            from . import bhuvan
            side.append(_side("BHUVAN", lambda: bhuvan.run(beats), out))
        if config.FSI_PORTAL:   # FSI's own alerts (NRSC feed, with beat tags)
            from . import fsi_portal
            side.append(_side("FSI_PORTAL", lambda: fsi_portal.run(beats, 7 if window == "7d" else 2), out))
        got = {}

        def feed(source):
            try:
                got[source] = fetch_feed(source, window)
            except Exception as e:  # keep the other sensors going
                log.exception("feed %s failed", source)
                _log_error(source, e)
                out[source] = str(e) or repr(e)
        ts = [threading.Thread(target=feed, args=(f,), daemon=True) for f in FEEDS]
        for t in ts:
            t.start()
        for t in ts:
            t.join(240)   # http_get's own deadline is 180 s
        rows = [d for f in FEEDS for d in got.get(f, [])]
        for f in FEEDS:
            if f in got:
                out[f] = len(got[f])
            elif f not in out:
                _log_error(f, TimeoutError("no answer in 240 s"))
                out[f] = "no answer in 240 s"
        if rows:   # NASA FIRMS fills FRP/position on Bhuvan and FSI rows, adds NOAA-21/Terra/non-forest
            try:
                out["FIRMS"] = store(rows, beats, f"FIRMS_{window}:" + ",".join(f for f in FEEDS if f in got))
            except Exception as e:
                log.exception("FIRMS store failed")
                _log_error("FIRMS", e)
                out["FIRMS"] = str(e) or repr(e)
        for t in side:
            if t:
                t.join(300)   # Bhuvan keeps to 240 s; a thread past this is left running and reported next poll
        return out
    finally:
        _RUN.release()
