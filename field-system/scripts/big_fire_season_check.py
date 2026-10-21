# Score a whole past season with the app's big-fire chance (app/big_fire.py) and check it against what happened.
# Loads every in-beat VIIRS point of 12 Feb-15 Jun (FIRMS archive, type 0, as in the research) into a throwaway database
# through the app's own ingest, scores each alert's first look, then compares with VIIRS truth computed here the
# research's way (ratapani/fsi/scouting/code/big_fire_chance b2/b4/b5: fires linked at 1.2 km / 30 h, distinct 375 m
# cells within 7 days, ha = 10.9 * cells^1.01 for 2023-26, big = 200 ha+). Scar truth is not rebuilt here.
#
#   FS_DATA_DIR=<scratch> FS_FOREST_FILTER=0 FS_FSI_PORTAL=0 python scripts/big_fire_season_check.py 2025 <out.csv>
import csv, glob, math, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import pyproj
from app import big_fire, db, firms
from app.geo import Beats

year, out_csv = int(sys.argv[1]), sys.argv[2]
SAT = {"viirs-snpp": "VIIRS_SNPP", "viirs-jpss1": "VIIRS_NOAA20", "viirs-noaa21": "VIIRS_NOAA21"}
lo, hi = f"{year}-02-12", f"{year}-06-15"
rows = []
for f in glob.glob(f"/mnt/project-files/fire-alert-scars/alerts_mp/viirs-*_{year}.csv"):
    src = SAT[Path(f).stem.rsplit("_", 1)[0]]
    for r in csv.DictReader(open(f)):
        if lo <= r["acq_date"] <= hi and r.get("type", "0") == "0":
            rows.append(firms.normalise(r, src, "VIIRS"))
print("points", len(rows), flush=True)
db.init()
B = Beats()
t = time.time()
for k in range(0, len(rows), 5000):
    firms.store(rows[k:k + 5000], B, "season_check")
    print("stored", k + 5000, round(time.time() - t), flush=True)

with db.tx() as con:
    P = [dict(x) for x in con.execute("""SELECT id, lat, lon, acq_utc, incident_id FROM detections
                                         WHERE instrument='VIIRS' AND beat_uid IS NOT NULL ORDER BY acq_utc""")]
    # VIIRS truth, the research's way
    tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
    x, y = tp(np.array([p["lon"] for p in P]), np.array([p["lat"] for p in P]))
    th = np.array([(firms.parse_utc(p["acq_utc"]) - datetime(year, 1, 1, tzinfo=timezone.utc)).total_seconds() / 3600 for p in P])
    X = np.c_[x, y, th * (1200 / 30)]
    pr = cKDTree(X).query_pairs(1200, p=np.inf, output_type="ndarray")
    pr = pr[np.hypot(x[pr[:, 0]] - x[pr[:, 1]], y[pr[:, 0]] - y[pr[:, 1]]) <= 1200]
    _, fire = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(P),) * 2), directed=False)
    t0 = {}
    for i, f in enumerate(fire):
        t0[f] = min(t0.get(f, 1e9), th[i])
    cells = {}
    for i, f in enumerate(fire):
        if th[i] - t0[f] <= 168:
            cells.setdefault(f, set()).add((math.floor(x[i] / 375), math.floor(y[i] / 375)))
    ha = {f: 10.9 * len(c) ** 1.01 for f, c in cells.items()}
    fire_of = {p["id"]: fire[i] for i, p in enumerate(P)}
    pid = {(p["lat"], p["lon"], p["acq_utc"]): p["id"] for p in P}

    incs = con.execute("SELECT * FROM incidents ORDER BY first_seen_utc").fetchall()
    print("incidents", len(incs), flush=True)
    out = []
    for n, inc in enumerate(incs):
        r = big_fire.check(con, inc, "2100-01-01T00:00:00Z", B, with_chance=True)
        if not r or not r.get("new_fire") or r["first_look_utc"][5:10] > "06-08":
            continue
        d = con.execute("""SELECT id FROM detections WHERE incident_id=? AND instrument='VIIRS' AND satellite<>'FSI'
                           ORDER BY acq_utc LIMIT 1""", (inc["id"],)).fetchone()
        f = fire_of[d["id"]]
        out.append(dict(incident=inc["id"], first_look_utc=r["first_look_utc"], division=r["division"], lat=inc["lat"], lon=inc["lon"],
                        points=r["points"], chance=r["chance"], farmland_checked=int(r["farmland_checked"]),
                        items="; ".join(f"{a} {b:+d}" for a, b in r["items"]), viirs_ha=round(ha[f]), big=int(ha[f] >= 200)))
        if n % 2000 == 0:
            print("scored", n, round(time.time() - t), flush=True)
with open(out_csv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0]))
    w.writeheader(); w.writerows(out)
print("alerts scored", len(out), "big", sum(o["big"] for o in out))
