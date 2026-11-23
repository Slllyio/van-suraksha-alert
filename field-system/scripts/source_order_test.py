# Offline check of the source order Bhuvan -> FSI -> NASA: an FSI alert for a pixel Bhuvan already sent only tags it,
# an FSI-only alert opens its own point, and NASA's later copy fills both rows instead of adding points.
#   FS_DATA_DIR=<empty folder> python scripts/source_order_test.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db, firms, fsi_portal
from app.geo import Beats

config.FOREST_FILTER = False
db.init()
B = Beats()
LAT, LON = 23.0496, 77.7425


def row(source, sat, lat, lon, acq, frp=0.0, scan=0.0, **kw):
    return dict(source=source, instrument="VIIRS", satellite=sat, lat=lat, lon=lon, acq_utc=acq, confidence="nominal",
                frp=frp, daynight="D", bright=0.0, scan=scan, track=scan, **kw)


def count(sql, *a):
    with db.tx() as con:
        return con.execute(sql, a).fetchone()[0]


ok = lambda c, msg: print(("PASS " if c else "FAIL ") + msg) or c
res = []
tags = dict(fsi_division="Raisen", fsi_range="R", fsi_beat="B1", fsi_compartment="101")
firms.store([row("BHUVAN", "N20", LAT, LON, "2026-04-22T07:52:00Z")], B, "t")                    # 1. Bhuvan
fsi = [row("FSI_PORTAL", "FSI", LAT + 0.0004, LON, "2026-04-22T07:50:00Z", **tags),                 # 2. FSI, same pixel
       row("FSI_PORTAL", "FSI", LAT + 0.02, LON, "2026-04-22T07:50:00Z", **tags)]                   #    FSI-only pixel
with db.tx() as con:
    extra = []
    for d in fsi:
        i = fsi_portal.match(con, d)
        (fsi_portal.tag(con, i, d) if i else extra.append(d))
firms.store(extra, B, "t")
res.append(ok(count("SELECT count(*) FROM detections") == 2, "FSI tags the Bhuvan point and adds only its own extra pixel"))
res.append(ok(count("SELECT fsi_beat FROM detections WHERE source='BHUVAN'") == "B1", "Bhuvan point carries FSI's beat"))
firms.store([row("VIIRS_NOAA20", "N20", LAT + 0.0002, LON, "2026-04-22T07:44:00Z", frp=6.5, scan=0.4),   # 3. NASA
             row("VIIRS_NOAA20", "N20", LAT + 0.0201, LON, "2026-04-22T07:44:00Z", frp=3.0, scan=0.4)], B, "t")
res.append(ok(count("SELECT count(*) FROM detections") == 2, "NASA fills both rows, no extra points"))
res.append(ok(count("SELECT count(*) FROM detections WHERE frp > 0") == 2, "both rows now carry NASA's FRP"))
print("ALL PASS" if all(res) else "SOME FAILED")
sys.exit(0 if all(res) else 1)
