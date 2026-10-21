# Full-season dry run: feed a whole past season of all-MP FIRMS points (VIIRS 3 satellites + MODIS, FIRMS archive) through the
# app's own live ingest in time order, one satellite pass at a time, as the 15-minute poller would see them (forest filter on,
# as live). Then the daily load tables are made by scripts/season_dry_run_stats.py.
#   FS_DATA_DIR=<scratch> FS_FSI_PORTAL=0 python scripts/season_dry_run.py 2026
import csv, glob, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, firms
from app.geo import Beats
from app.server import hash_pin

year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
SAT = {"viirs-snpp": ("VIIRS_SNPP", "VIIRS"), "viirs-jpss1": ("VIIRS_NOAA20", "VIIRS"), "viirs-noaa21": ("VIIRS_NOAA21", "VIIRS"), "modis": ("MODIS", "MODIS")}
rows = []
for f in glob.glob(f"/mnt/project-files/fire-alert-scars/alerts_mp/*_{year}.csv"):
    src, ins = SAT[Path(f).stem.rsplit("_", 1)[0]]
    for r in csv.DictReader(open(f)):
        if f"{year}-02-12" <= r["acq_date"] <= f"{year}-06-15" and r.get("type", "0") in ("0", ""):
            rows.append(firms.normalise(r, src, ins))
rows.sort(key=lambda d: d["acq_utc"])
print("points", len(rows), flush=True)
db.init()
with db.tx() as con:   # throwaway accounts so the screens can be opened
    for sid, name, role, pin in [(1, "Admin", "admin", "1111"), (2, "Ranger", "ranger", "2222"), (3, "Guard", "guard", "3333")]:
        con.execute("INSERT OR IGNORE INTO staff (id, name, role, pin_hash) VALUES (?,?,?,?)", (sid, name, role, hash_pin(pin)))
B = Beats(); t = time.time(); k = 0
while k < len(rows):   # one pass at a time: points within 20 min of the first one
    j = k
    while j < len(rows) and rows[j]["acq_utc"][:15] <= rows[k]["acq_utc"][:15] and j - k < 20000:
        j += 1
    while j < len(rows) and firms.parse_utc(rows[j]["acq_utc"]) <= firms.parse_utc(rows[k]["acq_utc"]).replace(second=0) + __import__("datetime").timedelta(minutes=20):
        j += 1
    firms.store(rows[k:j], B, "dry_run")
    if (k // 5000) != (j // 5000):
        print("stored", j, rows[j - 1]["acq_utc"], round(time.time() - t), flush=True)
    k = j
with db.tx() as con:
    print("incidents", con.execute("SELECT count(*) FROM incidents").fetchone()[0], "in", round(time.time() - t), "s")
