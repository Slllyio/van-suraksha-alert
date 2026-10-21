# Build a demo database that replays a past day around Ratapani, using real alerts:
# FSI's own alerts (FSI portal export, with FSI beat + compartment) and NASA FIRMS points for the
# 3 days up to the demo date. Then start the server with FS_DEMO_NOW so the screens show that day.
#
#   FS_DATA_DIR=/tmp/demo python scripts/demo_replay.py 2026-04-15
#   FS_DATA_DIR=/tmp/demo FS_DEMO_NOW=2026-04-15T12:30:00Z python run.py
#
# Demo accounts (throwaway database only, not real users): admin 1111, ranger 2222, guard 3333.
import csv, glob, os, sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db, firms, fsi_portal
from app.geo import Beats
from app.server import hash_pin

if not os.environ.get("FS_DATA_DIR"):   # it adds demo staff (PINs 1111/2222/3333): never into the live ./var database
    sys.exit("set FS_DATA_DIR to a throwaway folder")
day = date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2026-04-15")
days = {(day - timedelta(d)).isoformat() for d in range(4 if os.environ.get("FS_REPLAY_MP") == "1" else 3)}   # MP: 3 full days before, for the big-fire chance
# nothing after the demo clock (default 6 pm IST on the demo day)
CUTOFF = os.environ.get("FS_DEMO_NOW") or f"{day.isoformat()}T12:30:00Z"
FSI_DIR = "/mnt/project-files/ratapani/fsi/fsi_portal/"
FIRMS_DIR = "/mnt/project-files/fire-alert-scars/alerts/"
SAT = {"viirs-snpp": ("VIIRS_SNPP", "VIIRS"), "viirs-jpss1": ("VIIRS_NOAA20", "VIIRS"), "viirs-noaa21": ("VIIRS_NOAA21", "VIIRS"),
       "modis": ("MODIS", "MODIS")}

db.init()
B = Beats()

# NASA FIRMS points (Ratapani archive files used by the burn-scar work; FS_REPLAY_MP=1: the all-MP archive)
if os.environ.get("FS_REPLAY_MP") == "1":
    FIRMS_DIR = "/mnt/project-files/fire-alert-scars/alerts_mp/"
rows = []
for f in glob.glob(FIRMS_DIR + f"*_{day.year}.csv"):
    src, ins = SAT[Path(f).stem.rsplit("_", 1)[0]]
    for r in csv.DictReader(open(f)):
        if r["acq_date"] in days and (r.get("acq_time") or "").strip() and r.get("satellite"):   # NRT-EE rows: no time
            d = firms.normalise(r, src, ins)
            if d["acq_utc"] <= CUTOFF:
                rows.append(d)
rows.sort(key=lambda d: d["acq_utc"])
print("FIRMS points", len(rows), firms.store(rows, B, "demo_firms"))

# FSI's own alerts for the same days: tag matching FIRMS points, add the rest
seen, fsi = set(), []
for f in glob.glob(FSI_DIR + "fsi_pts_*.csv") + [FSI_DIR + "obd_2026.csv"]:
    for r in csv.DictReader(open(f)):
        k = (r["Fire_Date"], r["Fire_Time"], r["Lat"], r["Lon"])
        if r["Fire_Date"] in days and k not in seen:
            seen.add(k)
            d = fsi_portal.normalise(r)
            if d["acq_utc"] <= CUTOFF:
                fsi.append(d)
fsi.sort(key=lambda d: d["acq_utc"])
extra = []
with db.tx() as con:
    for d in fsi:
        i = fsi_portal.match(con, d)
        if i:
            fsi_portal.tag(con, i, d)
        else:
            extra.append(d)
print("FSI alerts", len(fsi), "matched FIRMS", len(fsi) - len(extra), firms.store(extra, B, "demo_fsi"))
with db.tx() as con:
    for d in extra:
        i = fsi_portal.match(con, d)
        if i:
            fsi_portal.tag(con, i, d)
    for x in con.execute("""SELECT * FROM detections WHERE fsi_beat IS NOT NULL AND incident_id IS NULL
                            AND beat_uid IS NOT NULL AND mask_kind IS NULL""").fetchall():
        d = dict(x)
        near = B.touching(d["lat"], d["lon"], firms.FOOTPRINT_KM[d["instrument"]])
        d["beats"] = [d["beat_uid"]] + [b for b in near if b != d["beat_uid"]]
        firms.attach_to_incident(con, d["id"], d)
    # demo staff: the guard gets the beat with most alerts on the demo day, the ranger its range
    # (Ratapani's own division, Obedullahganj, first)
    cand = con.execute("""SELECT beat_uid, count(*) n FROM incidents WHERE substr(first_seen_utc,1,10)=?
                          GROUP BY beat_uid ORDER BY n DESC""", (day.isoformat(),)).fetchall() or \
           con.execute("SELECT beat_uid, count(*) n FROM incidents GROUP BY beat_uid ORDER BY n DESC").fetchall()
    top = sorted(cand, key=lambda r: (B.by_uid[r["beat_uid"]]["division"] != "Obedullahganj", -r["n"]))[0]
    p = B.by_uid[top["beat_uid"]]
    if not con.execute("SELECT 1 FROM staff").fetchone():
        for name, role, beat, rng, pin in [("Demo admin", "admin", None, None, "1111"),
                                           ("Demo ranger", "ranger", None, f"{p['division']}:{p['range']}", "2222"),
                                           (f"Demo guard ({p['beat']})", "guard", top["beat_uid"], None, "3333")]:
            con.execute("INSERT INTO staff(name,role,beat_uid,range_name,phone,pin_hash) VALUES (?,?,?,?,?,?)",
                        (name, role, beat, rng, None, hash_pin(pin)))
    print("incidents", con.execute("SELECT count(*) FROM incidents").fetchone()[0],
          "guard beat", top["beat_uid"], p["beat"], p["range"], p["division"])
