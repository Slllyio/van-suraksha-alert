"""FSI's own fire alerts from its open Fire Point Search portal (fsiforestfire.gov.in, no login).

Each FSI alert carries FSI's Division, Range, Beat and Compartment_No. We use the portal two ways:
  1. tag our FIRMS points with FSI's beat and compartment (same instrument, within 15 min and 400 m);
  2. add FSI alerts that FIRMS does not have (FSI gets its points from NRSC's ground station,
     and some passes are missing from FIRMS) as detections with source 'FSI_PORTAL'.
FSI already masks its alerts to forest, so FSI-only points skip our forest filter.
FSI times are IST. Season data starts 1 Nov 2025.
"""
import logging, urllib.request
from datetime import datetime, timedelta, timezone
from . import config, db
from .geo import haversine_km

log = logging.getLogger("fsi_portal")
URL = "https://fsiforestfire.gov.in/FirePointSearch/DownloadCsv?FromDate={d0}&ToDate={d1}&Source=Both&State={state}"
IST = timezone(timedelta(hours=5, minutes=30))
# FSI points equal FIRMS ones since FSI moved to NOAA-21 (late Apr 2026); in its S-NPP era (Nov 2025 -
# Apr 2026) FSI geolocated pixels itself, median 0.25 km off FIRMS. 0.4 km (about one pixel), nearest wins.
MATCH_KM, MATCH_MIN = 0.4, 15
# Bhuvan's pass time is NRSC's granule time, 2-12 min after FIRMS' scan time, so those matches get 20 min;
# a FIRMS satellite must then equal the Bhuvan row's (NOAA-21 passes ~25 min from NOAA-20 and S-NPP).
# Bhuvan points are FIRMS' own pixels (median 15-65 m apart), so 150 m: a neighbouring pixel (~375 m) never merges.
BHUVAN_MIN, BHUVAN_KM = 20, 0.15


def fetch(days=2):
    now = datetime.now(timezone.utc)
    url = URL.format(d0=(now - timedelta(days=days)).strftime("%Y-%m-%d"),
                     d1=(now + timedelta(days=1)).strftime("%Y-%m-%d"), state=config.FSI_STATE)
    # the portal resets connections from clients without a browser User-Agent
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
    from .firms import http_get, parse_rows, FOOTPRINT_KM
    text = http_get(req).decode("utf-8-sig")          # total deadline; tolerates a BOM (.NET exports)
    rows = parse_rows(text, ("Fire_Date", "Fire_Time", "Lat", "Lon", "Source_Type"), normalise, "FSI_PORTAL",
                      empty_ok=True)   # FSI lists only alerts: none for 2 days is normal off-season
    bad = [d["instrument"] for d in rows if d["instrument"] not in FOOTPRINT_KM]
    if bad:
        log.warning("FSI: skipped %d points of unknown sensor %s", len(bad), sorted(set(bad)))
    return [d for d in rows if d["instrument"] in FOOTPRINT_KM]


def normalise(row):
    acq = datetime.fromisoformat(f"{row['Fire_Date']}T{row['Fire_Time']}").replace(tzinfo=IST).astimezone(timezone.utc)
    title = lambda s: (s or "").strip().title()
    return dict(source="FSI_PORTAL", instrument=row["Source_Type"].strip().upper(), satellite="FSI",
                lat=round(float(row["Lat"]), 5), lon=round(float(row["Lon"]), 5),
                acq_utc=acq.strftime("%Y-%m-%dT%H:%M:%SZ"), confidence="nominal", frp=0.0,
                daynight="D" if 0 <= acq.hour < 12 else "N", bright=0.0, scan=0.0, track=0.0,
                fsi_division=title(row.get("Division")).replace(" Division", ""),
                fsi_range=title(row.get("Range")).replace(" Range", ""),
                fsi_beat=title(row.get("Beat")).replace(" Beat", ""),
                fsi_compartment=(row.get("Compartment_No") or "").strip())


def match(con, d):
    """Id of a stored detection that is the same fire pixel as d, else None."""
    t = datetime.strptime(d["acq_utc"], "%Y-%m-%dT%H:%M:%SZ")
    lo, hi = [(t + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ") for m in (-BHUVAN_MIN, BHUVAN_MIN)]
    best = None
    # +instrument: on a fresh database (no statistics) the planner would otherwise scan every VIIRS point
    for x in con.execute("""SELECT id, lat, lon, acq_utc, source, satellite FROM detections WHERE +instrument=? AND acq_utc BETWEEN ? AND ?
                            AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?""",
                         (d["instrument"], lo, hi, d["lat"] - 0.002, d["lat"] + 0.002, d["lon"] - 0.002, d["lon"] + 0.002)):
        bhuvan = "BHUVAN" in (x["source"], d.get("source"))
        dt = abs((datetime.strptime(x["acq_utc"], "%Y-%m-%dT%H:%M:%SZ") - t).total_seconds()) / 60
        if dt > (BHUVAN_MIN if bhuvan else MATCH_MIN):
            continue
        if bhuvan and "FSI" not in (x["satellite"], d.get("satellite")) and x["satellite"] != d.get("satellite"):
            continue
        km = haversine_km(d["lat"], d["lon"], x["lat"], x["lon"])
        if km <= (BHUVAN_KM if bhuvan else MATCH_KM) and (best is None or km < best[1]):
            best = (x["id"], km)
    return best and best[0]


def tag(con, det_id, d):
    """FSI's beat and compartment on the detection (the first one), and every beat FSI sent it to in fsi_tags
    (FSI lists a junction pixel once per beat). The alert's updated_utc moves, so `since` polling sees the tag."""
    con.execute("""UPDATE detections SET fsi_division=?, fsi_range=?, fsi_beat=?, fsi_compartment=?
                   WHERE id=? AND fsi_beat IS NULL""",
                (d["fsi_division"], d["fsi_range"], d["fsi_beat"], d["fsi_compartment"], det_id))
    if con.execute("INSERT OR IGNORE INTO fsi_tags VALUES (?,?,?,?,?)",
                   (det_id, d["fsi_division"], d["fsi_range"], d["fsi_beat"], d["fsi_compartment"])).rowcount:
        con.execute("""UPDATE incidents SET updated_utc = strftime('%Y-%m-%dT%H:%M:%SZ','now')
                       WHERE id = (SELECT incident_id FROM detections WHERE id = ?)""", (det_id,))


def run(beats, days=2):
    """Tag matching FIRMS points with FSI's beat/compartment; store FSI-only alerts; open tasks
    for FSI alerts our forest filter dropped. Returns (tagged, added, promoted)."""
    from . import firms
    rows = [d for d in fetch(days) if firms.in_bbox(d)]
    tagged, extra, tagged_ids = 0, [], []
    with firms.LOCK, db.tx() as con:
        con.execute("BEGIN IMMEDIATE")
        for d in rows:
            i = match(con, d)
            if i:
                if con.execute("SELECT fsi_beat IS NULL FROM detections WHERE id=?", (i,)).fetchone()[0]:
                    tagged_ids.append(i)
                tag(con, i, d)
                tagged += 1
            else:
                extra.append(d)
    added = firms.store(extra, beats, f"FSI_PORTAL_{days}d")[0] if extra else 0
    promoted, touched = 0, set()
    with firms.LOCK, db.tx() as con:   # store() inserted the FSI-only rows; give them their FSI tags too
        con.execute("BEGIN IMMEDIATE")
        for d in extra:
            i = match(con, d)
            if i:
                tag(con, i, d)
        # FSI sent an alert for a pixel our forest filter dropped: FSI's forest mask wins, since the
        # beat guard gets FSI's SMS for it anyway. Masked points (mines, persistent heat) stay out.
        for x in con.execute("""SELECT * FROM detections WHERE fsi_beat IS NOT NULL AND incident_id IS NULL
                                AND beat_uid IS NOT NULL AND mask_kind IS NULL AND acq_utc >= ?""",
                             ((datetime.now(timezone.utc) - timedelta(days=days + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),)).fetchall():
            d = dict(x)
            near = beats.touching(d["lat"], d["lon"], firms.FOOTPRINT_KM[d["instrument"]])
            d["beats"] = [d["beat_uid"]] + [b for b in near if b != d["beat_uid"]]
            promoted += firms.attach_to_incident(con, d["id"], d)
            touched.add(con.execute("SELECT incident_id FROM detections WHERE id=?", (d["id"],)).fetchone()[0])
        if config.WEBHOOK_URL:   # FSI tags changed these alerts too
            touched |= {r[0] for r in con.execute(
                "SELECT DISTINCT incident_id FROM detections WHERE fsi_beat IS NOT NULL AND incident_id IS NOT NULL AND id IN (%s)"
                % (",".join(str(i) for i in tagged_ids) or "0"))}
    firms.send_updates(touched - {None})
    return tagged, added, promoted
