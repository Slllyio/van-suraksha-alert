# Offline check of the Bhuvan intake: a Bhuvan point opens the alert, the same FIRMS pixel fills it in
# instead of adding a second point, and neighbouring pixels / other satellites stay separate points.
#   FS_DATA_DIR=<empty folder> python scripts/bhuvan_test.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import bhuvan, config, db, firms
from app.geo import Beats

config.FOREST_FILTER = False   # WorldCover reads are not what is tested here
db.init()
B = Beats()
LAT, LON = 23.0496, 77.7425    # inside a Ratapani beat (a 2026 dry-run alert)
assert B.locate(LAT, LON), "test point is not in a beat"


def row(source, sat, lat, lon, acq, frp=0.0, scan=0.0, inst="VIIRS"):
    return dict(source=source, instrument=inst, satellite=sat, lat=lat, lon=lon, acq_utc=acq, confidence="nominal",
                frp=frp, daynight="D", bright=0.0, scan=scan, track=scan)


def count(sql, *a):
    with db.tx() as con:
        return con.execute(sql, a).fetchone()[0]


ok = lambda c, msg: print(("PASS " if c else "FAIL ") + msg) or c
res = []
assert bhuvan.pass_utc("2026-10-19", "2026-10-19 02:32:07.45").strftime("%H:%M:%S") == "21:02:07"
assert bhuvan.pass_utc("2026-10-19", "03:55:20").strftime("%Y-%m-%d %H:%M") == "2026-10-18 22:25"

# 1. Bhuvan sends NOAA-20 pixel at the granule time 13:22 IST (07:52 UTC): alert opens
firms.store([row("BHUVAN", "N20", LAT, LON, "2026-04-22T07:52:00Z")], B, "t")
res.append(ok(count("SELECT count(*) FROM incidents") == 1, "Bhuvan point opens an alert"))
# 2. FIRMS sends the same pixel 40 m away, scanned 8 min earlier: fills the Bhuvan row, no new point
f = row("VIIRS_NOAA20", "N20", LAT + 0.0003, LON + 0.0002, "2026-04-22T07:44:00Z", frp=6.5, scan=0.4)
firms.store([f], B, "t")
res.append(ok(count("SELECT count(*) FROM detections") == 1, "same FIRMS pixel merges into the Bhuvan row"))
res.append(ok(count("SELECT frp FROM detections WHERE source='BHUVAN'") == 6.5, "Bhuvan row takes FIRMS' FRP"))
# 3. the next poll of the same FIRMS file: still one point
firms.store([f], B, "t")
res.append(ok(count("SELECT count(*) FROM detections") == 1, "re-polled FIRMS pixel is not added again"))
# 4. FIRMS neighbouring pixel 375 m away, same pass: its own point, same alert
firms.store([row("VIIRS_NOAA20", "N20", LAT + 0.0034, LON, "2026-04-22T07:44:00Z", frp=3.0, scan=0.4)], B, "t")
res.append(ok(count("SELECT count(*) FROM detections") == 2, "neighbouring pixel stays a separate point"))
# 5. NOAA-21 at the same spot 18 min later: a separate look, not merged into the NOAA-20 Bhuvan row
firms.store([row("VIIRS_NOAA21", "N21", LAT, LON, "2026-04-22T08:10:00Z", frp=4.0, scan=0.4)], B, "t")
res.append(ok(count("SELECT count(*) FROM detections") == 3, "other satellite is not merged"))
# 6. Bhuvan re-lists a pixel FIRMS already sent (S-NPP sent by FIRMS first): skipped
firms.store([row("VIIRS_SNPP", "N", LAT - 0.01, LON, "2026-04-22T08:30:00Z", frp=2.0, scan=0.4)], B, "t")
firms.store([row("BHUVAN", "N", LAT - 0.0101, LON, "2026-04-22T08:36:00Z")], B, "t")
res.append(ok(count("SELECT count(*) FROM detections WHERE satellite='N'") == 1, "late Bhuvan copy of a FIRMS pixel is skipped"))
res.append(ok(count("SELECT count(DISTINCT incident_id) FROM detections WHERE satellite IN ('N20','N21')") == 1,
              "the merged point, its neighbour and the NOAA-21 look are one alert"))
print("ALL PASS" if all(res) else "SOME FAILED")
sys.exit(0 if all(res) else 1)
