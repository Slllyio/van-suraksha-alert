# 2027 cause check (control_burn.cause_check): tagged late-Feb alerts and a random untagged sample must carry a cause;
# guards see only cause_required. In-process test on a throwaway database:
#   FS_DATA_DIR=<scratch> FS_FOREST_FILTER=0 FS_FSI_PORTAL=0 python scripts/cause_check_test.py
import os, sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi import HTTPException
from app import db, firms, control_burn, server
from app.geo import Beats

db.init()
B = Beats()
rnd = random.Random(7)
uids = [p["beat_uid"] for p in B.props if p.get("division") == "Obedullahganj"][:200]
rows = []
for k in range(120):   # alerts on 15-25 Feb 2027, far apart; even ones small daytime (tag), odd ones night/hot (no tag)
    g = B.geoms[[p["beat_uid"] for p in B.props].index(uids[k % len(uids)])].representative_point()
    day = 15 + k % 10
    tag = k % 2 == 0
    rows.append(dict(source="VIIRS_NOAA20", instrument="VIIRS", satellite="N20", lat=round(g.y, 5), lon=round(g.x, 5),
                     acq_utc=f"2027-02-{day:02d}T{'08:00' if tag else '20:30'}:00Z", confidence="nominal", frp=3.0 if tag else 15.0,
                     daynight="D" if tag else "N", bright=330.0, scan=0.4, track=0.4))
rows.append(dict(rows[0], acq_utc="2026-02-20T08:00:00Z", lat=rows[0]["lat"] + 0.3))   # 2026: before the check starts
firms.store(rows, B, "test")
NOW = "2027-03-10T00:00:00Z"
server.now = lambda: firms.parse_utc(NOW)
guard, official = {"role": "guard"}, {"role": "admin"}
G = {}
with db.tx() as con:
    for r in con.execute("SELECT * FROM incidents ORDER BY id").fetchall():
        d = {}
        server.cause_fields(con, r, d, official)
        G[r["id"]] = (r["first_seen_utc"], d["cause_group"], d["cause_required"])
        gd = {}
        server.cause_fields(con, con.execute("SELECT * FROM incidents WHERE id=?", (r["id"],)).fetchone(), gd, guard)
        assert set(gd) == {"cause_required"} and gd["cause_required"] == d["cause_required"], gd
        again = control_burn.cause_check(con, con.execute("SELECT * FROM incidents WHERE id=?", (r["id"],)).fetchone(), NOW)
        assert again == d["cause_group"], "decided once"
grp = [g for t, g, _ in G.values() if t.startswith("2027")]
print({k: grp.count(k) for k in set(grp)})
assert all(g is None for t, g, _ in G.values() if t.startswith("2026"))
assert grp.count("tagged") == 60 and 15 <= grp.count("random") <= 60, "about equal groups"
req = next(i for i, (t, g, q) in G.items() if g == "random")
free = next(i for i, (t, g, q) in G.items() if g == "none")
with db.tx() as con:
    inc = con.execute("SELECT * FROM incidents WHERE id=?", (req,)).fetchone()
    try:
        server.record_report(con, inc, 1, {"outcome": "burnt_out"}, [], [])
        raise SystemExit("report without cause was accepted")
    except HTTPException as e:
        assert e.status_code == 400 and "cause" in e.detail
    f = {"outcome": "controlled_burn"}
    try:
        server.record_report(con, inc, 1, f, [], [])
    except HTTPException as e:
        assert "cause" not in str(e.detail), e.detail
    except Exception:
        pass   # later checks (staff, photos) are not part of this test
    assert f["cause"] == "Controlled burning / fire line"
    inc2 = con.execute("SELECT * FROM incidents WHERE id=?", (free,)).fetchone()
    try:
        server.record_report(con, inc2, 1, {"outcome": "burnt_out"}, [], [])
    except HTTPException as e:
        assert "cause" not in str(e.detail), e.detail
    except Exception:
        pass
    con.rollback()
print("cause check test passed")
