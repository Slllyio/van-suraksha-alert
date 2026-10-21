# Hint coverage on one day of a dry-run database: how many of that day's alerts get the 30 m arrow, the runway hint and a
# still-burning line, and how long each takes. Day = IST date; the clock is 18:30 IST that day (after the afternoon passes).
#   FS_DATA_DIR=<scratch> python scripts/season_dry_run_hints.py 2026-04-22 <out.json>
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, direction, firms, runway, still_burning
day = sys.argv[1]; now = datetime.fromisoformat(day + "T13:00:00+00:00")
lo = firms.iso(datetime.fromisoformat(day + "T00:00:00+00:00") - timedelta(hours=5, minutes=30))
db.init()
with db.tx() as con:
    ids = [r[0] for r in con.execute("""SELECT id FROM incidents WHERE COALESCE(kind,'alert')='alert' AND first_seen_utc >= ? AND first_seen_utc <= ?""",
                                     (lo, firms.iso(now)))]
print("alerts", len(ids), flush=True)
t = time.time(); runway.run_due(now, ids=ids); tr = time.time() - t
print("runway done", round(tr), flush=True)
t = time.time(); direction.run_due(now, ids=ids); td = time.time() - t
with db.tx() as con:
    R = dict(con.execute(f"SELECT status, count(*) FROM fire_runway WHERE incident_id IN ({','.join(map(str, ids))}) GROUP BY status").fetchall())
    Dd = dict(con.execute(f"SELECT status, count(*) FROM fire_direction WHERE incident_id IN ({','.join(map(str, ids))}) GROUP BY status").fetchall())
    shown = sum(1 for i in ids if direction.for_incident(con, i, now))
    sb = [still_burning.check(con, i, now) for i in ids]
out = dict(day=day, clock_utc=firms.iso(now), alerts=len(ids), runway=R, runway_seconds_per_alert=round(tr / max(len(ids), 1), 2),
           direction=Dd, direction_shown=shown, direction_seconds_per_alert=round(td / max(len(ids), 1), 2),
           still_burning_lines=sum(1 for x in sb if x), still_burning_by_chance={str(p): sum(1 for x in sb if x and x["chance"] == p) for p in (.62, .33, .16, .09)})
json.dump(out, open(sys.argv[2], "w"), indent=1); print(json.dumps(out, indent=1))
