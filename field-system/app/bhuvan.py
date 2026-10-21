"""VIIRS and MODIS fire points from NRSC's Bhuvan forest-fire panel, 1-5 h before NASA's files.

Bhuvan (bhuvan-app1.nrsc.gov.in, no login) lists each pass from NRSC's Shadnagar ground station on its
"current forest fire" panel about 40-60 min after the pass (18-19 Oct 2026: VIIRS 40-62 min, Aqua 18 min;
NASA FIRMS 1.7-2.8 h at night, 4.5-6 h by day). The points are the same pixels as FIRMS (median 15-65 m
apart, rounding), but carry only position, sensor and the pass time, and only points inside NRSC's forest
mask. So a Bhuvan point opens the alert early; when FIRMS sends the same pixel, firms.store() fills in
FIRMS' measurements (FRP, confidence, scan) on the Bhuvan row instead of adding a second point.

Sensors on the panel: S-NPP VIIRS 375 m (VF375), NOAA-20 VIIRS 375 m (JPVF375, "JPSS1") and Aqua MODIS (A).
NOAA-21 and Terra are not on it and still come from NASA. The 750 m VIIRS points are skipped (not FIRMS pixels).
The pass time is NRSC's granule time in IST, 2-12 min after FIRMS' acquisition time.
The panel is a web page, not an API, and resets about 1 request in 4, so every call retries."""
import logging, re, time
from datetime import datetime, timedelta, timezone

from . import config

log = logging.getLogger("bhuvan")
BASE = "https://bhuvan-app1.nrsc.gov.in/disaster/usrtasks/fire"
IST = timezone(timedelta(hours=5, minutes=30))
SENSORS = {"VF375": ("VIIRS", "N"), "JPVF375": ("VIIRS", "N20"), "A": ("MODIS", "A")}
PASS = re.compile(r"view_curr\('[^']*',(\d+),'([\d-]+)','([^']+)','([A-Z0-9]+)'\)")
_done = set()   # passes already read in full; the panel keeps only the last day or so


BUDGET_S = 240   # one poll never spends more than this on Bhuvan (NASA and FSI run alongside, see firms.run_live)


def _get(url, params=None, tries=3, deadline=60):
    """GET with retries (the panel resets ~1 request in 4) and a total deadline per try (timeout= is per read)."""
    import requests
    for i in range(tries):
        try:
            end = time.monotonic() + deadline
            with requests.get(url, params=params, timeout=(10, 30), headers={"User-Agent": "Mozilla/5.0"}, stream=True) as r:
                r.raise_for_status()
                buf = []
                for chunk in r.iter_content(1 << 16):
                    buf.append(chunk)
                    if time.monotonic() > end:
                        raise TimeoutError(f"download over {deadline} s")
                r._content = b"".join(buf)
                return r
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 + 2 * i)


def passes():
    """(ctr, date, time, sensor) of every 375 m VIIRS / MODIS pass on the panel now."""
    return [m for m in PASS.findall(_get(f"{BASE}/fire.php", {"uname": ""}).text) if m[3] in SENSORS]


def pass_utc(date, t):
    """'2026-10-19 02:32:07.45' or '03:55:20' (with date) in IST -> aware UTC datetime."""
    s = t if " " in t else f"{date} {t}"
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST).astimezone(timezone.utc)


def read_pass(ctr, date, t, sensor):
    import xlrd
    r = _get(f"{BASE}/phpExcel/activefire_location.php", {"ctr": ctr, "date": date, "t": t, "s": sensor})
    sh = xlrd.open_workbook(file_contents=r.content, ignore_workbook_corruption=True).sheet_by_index(0)
    instrument, satellite = SENSORS[sensor]
    acq = pass_utc(date, t)
    ist = acq.astimezone(IST)
    rows = []
    for i in range(2, sh.nrows):   # row 0 title, row 1 header: Longitude, Latitude, Sensor
        lon, lat = sh.row_values(i)[:2]
        try:
            lon, lat = float(lon), float(lat)
        except (TypeError, ValueError):
            continue
        rows.append(dict(source="BHUVAN", instrument=instrument, satellite=satellite, lat=round(lat, 5), lon=round(lon, 5),
                         acq_utc=acq.strftime("%Y-%m-%dT%H:%M:%SZ"), confidence="nominal", frp=0.0,
                         daynight="D" if 6 <= ist.hour < 18 else "N", bright=0.0, scan=0.0, track=0.0))
    return rows


def run(beats):
    """Read passes not read before and store their points. Returns (passes read, new points, new alerts)."""
    from . import firms
    read = new_rows = new_inc = 0
    t_end = time.monotonic() + BUDGET_S
    ps = passes()
    if not ps:   # the panel always lists the day's passes: none means the page changed or came back empty
        raise RuntimeError("Bhuvan panel lists no 375 m passes (page layout changed?)")
    for p in ps:
        if p in _done:
            continue
        if time.monotonic() > t_end:
            log.warning("bhuvan: %d s budget used, remaining passes next poll", BUDGET_S)
            break
        try:
            rows = read_pass(*p)
        except Exception as e:
            log.exception("bhuvan pass %s failed", p)
            firms._log_error(f"BHUVAN_{p[3]}", f"pass {p[1]} {p[2]}: {e!r}"[:500])
            continue        # try again at the next poll
        n, k = firms.store(rows, beats, f"BHUVAN_{p[3]}") if rows else (0, 0)
        # an empty sheet may not be filled in yet: keep re-reading it for 3 h after the pass
        if rows or datetime.now(timezone.utc) - pass_utc(p[1], p[2]) > timedelta(hours=3):
            _done.add(p)
        read, new_rows, new_inc = read + 1, new_rows + n, new_inc + k
    return read, new_rows, new_inc
