# Check of the officials' 2-day list rule (app/daily_list.py) on one dry-run day with stand-in scores.
# The real scores come from the PC pipeline; here a square's score is how many VIIRS points fell within ~2 km in the
# 30 days before (plus noise), which is enough to test the rule's arithmetic, not its catch rate.
#   cp <dry-run>/field.db <scratch>/ && FS_DATA_DIR=<scratch> python scripts/daily_list_test.py 2026-04-22
import math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import daily_list as DL, db
from app.geo import Beats

day = sys.argv[1] if len(sys.argv) > 1 else "2026-04-22"
db.init()
B = Beats()
cid, row, col, beat = DL.cells()
g = DL.grid()
until = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=5, minutes=30))) + timedelta(hours=16)
with db.tx() as con:
    pts = con.execute("SELECT lat, lon FROM detections WHERE instrument='VIIRS' AND acq_utc BETWEEN ? AND ?",
                      ((until - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), until.strftime("%Y-%m-%dT%H:%M:%SZ"))).fetchall()
from pyproj import Transformer
x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform([p[1] for p in pts], [p[0] for p in pts])
heat = np.zeros((g["H"], g["W"]))
np.add.at(heat, (((g["Y1"] - np.array(y)) // g["S"]).astype(int).clip(0, g["H"] - 1),
                 ((np.array(x) - g["X0"]) // g["S"]).astype(int).clip(0, g["W"] - 1)), 1)
k = np.ones(9)                                          # ~2 km box blur, separable
heat = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, heat)
heat = np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 0, heat)
rng = np.random.default_rng(1)
score = np.log1p(heat[row, col]) + rng.normal(0, 0.3, len(cid))
div = np.array([B.by_uid.get(b, {}).get("division", "") for b in beat])
scale = {d: rng.uniform(0.5, 2) for d in set(div)}        # divisions calibrate differently: same score, different %
pct = 1 - np.exp(-np.maximum(score, 0) * np.array([scale[d] for d in div]) / 10)

res = []
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or res.append(bool(c))
body = {"issue_date": day, "model_version": {"model": "stand-in"}, "cell": cid.tolist(), "pct": pct.tolist(), "score": score.tolist()}
with db.tx() as con:
    s = DL.build(con, B, body, until)
    n = __import__("json").loads(con.execute("SELECT counts FROM daily_list_meta WHERE issue_date=?", (day,)).fetchone()[0])
    got = dict(con.execute("SELECT division, count(*) FROM daily_list WHERE issue_date=? GROUP BY 1", (day,)).fetchall())
    reason = dict(con.execute("SELECT reason, count(*) FROM daily_list WHERE issue_date=? GROUP BY 1", (day,)).fetchall())
    qpool = con.execute("SELECT count(*) FROM daily_list WHERE issue_date=? AND reason!='division'", (day,)).fetchone()[0]
print({k: v for k, v in s.items() if k != "divisions_below_half"}, "below half:", s["divisions_below_half"])
ok(s["flagged"] == s["total"] == sum(n.values()), f"flags = the day's total ({s['total']}), same workload as per-division counts")
ok(all(got.get(d, 0) >= math.ceil(k * DL.FLOOR) for d, k in n.items()), "every division keeps at least half its own count")
ok(abs(reason.get("quiet square", 0) - round(qpool * DL.QUIET_SHARE)) <= 1, f"{round(100 * DL.QUIET_SHARE)}% of the pooled flags go to quiet squares")
cells_per_div = {d: int((div == d).sum()) for d in n}
ok(all(k == round(cells_per_div[d] * DL.BASE_SHARE * DL.config.DAILY_K) for d, k in n.items()), "first-week count = k x 10% of each division's squares")
moved = sorted(((got.get(d, 0) - k, d) for d, k in n.items()))
print("most borrowed from:", moved[:3], " most lent to:", moved[-3:])
with db.tx() as con:
    s2 = DL.build(con, B, dict(body, rule="division"), until)
    got2 = dict(con.execute("SELECT division, count(*) FROM daily_list WHERE issue_date=? GROUP BY 1", (day,)).fetchall())
ok(s2["flagged"] == s["total"] and all(got2.get(d, 0) == k for d, k in n.items() if k), "FS_DAILY_RULE=division: each division exactly its count")
with db.tx() as con:
    DL.build(con, B, body, until)   # leave the day's list on the default rule
print("ALL PASS" if all(res) else "SOME FAILED")
sys.exit(0 if all(res) else 1)
