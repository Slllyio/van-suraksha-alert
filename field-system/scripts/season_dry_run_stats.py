# Daily load tables from a dry-run database (scripts/season_dry_run.py): alerts and new fires per day statewide, per beat/range/
# division, junction alerts, guard big-fire flags. Big-fire points are scored for every alert (same as the live list does).
#   FS_DATA_DIR=<scratch> python scripts/season_dry_run_stats.py <out_dir>
import json, sys, time
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from app import big_fire, db, firms
from app.geo import Beats
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
db.init(); B = Beats(); t = time.time()
with db.tx() as con:
    I = pd.DataFrame([dict(r) for r in con.execute("SELECT id, beat_uid, first_seen_utc, n_detections, large, sensors FROM incidents WHERE COALESCE(kind,'alert')='alert'")])
    jb = pd.DataFrame([dict(r) for r in con.execute("SELECT incident_id, count(*) n FROM incident_beats GROUP BY incident_id")])
    rows = []
    for k, r in enumerate(con.execute("SELECT * FROM incidents WHERE COALESCE(kind,'alert')='alert'").fetchall()):
        b = big_fire.check(con, r, "2100-01-01T00:00:00Z", B)
        rows.append(dict(id=r["id"], new_fire=bool(b and b.get("new_fire")), points=(b or {}).get("points"), guard_flag=bool(b and b.get("guard_flag"))))
        if k % 5000 == 0: print("scored", k, round(time.time() - t), flush=True)
I = I.merge(pd.DataFrame(rows), on="id").merge(jb.rename(columns={"incident_id": "id"}), on="id", how="left")
# alerts are due by the IST day they arrive
I["day"] = (pd.to_datetime(I.first_seen_utc) + pd.Timedelta(hours=5, minutes=30)).dt.date
p = {u: B.by_uid.get(u, {}) for u in I.beat_uid.unique()}
I["range"] = I.beat_uid.map(lambda u: (p[u].get("division"), p[u].get("range"))); I["division"] = I.beat_uid.map(lambda u: p[u].get("division"))
I = I[(I.day >= pd.Timestamp("2026-02-15").date()) & (I.day <= pd.Timestamp("2026-06-15").date())]
D = I.groupby("day").agg(alerts=("id", "size"), new_fires=("new_fire", "sum"), guard_flags=("guard_flag", "sum"), large=("large", "sum"),
                         beats_with_alert=("beat_uid", "nunique"), junction=("n", lambda s: int((s > 1).sum())))
D.to_csv(out / "daily_statewide.csv")
per = lambda col: I.groupby([col, "day"]).size()
s = {}
for col in ["beat_uid", "range", "division"]:
    x = per(col)
    s[col] = dict(units_with_any_alert=int(I[col].nunique()), busiest_day_max=int(x.max()), p99_per_unit_day=float(x.quantile(.99)),
                  median_on_days_with_alerts=float(x.median()), share_unit_days_over_5=round(float((x > 5).mean()), 3))
top = D.sort_values("alerts", ascending=False).head(10)
res = dict(alerts=int(len(I)), new_fires=int(I.new_fire.sum()), guard_flags=int(I.guard_flag.sum()), days=int(D.shape[0]),
           alerts_per_day=dict(median=float(D.alerts.median()), p90=float(D.alerts.quantile(.9)), max=int(D.alerts.max()), peak_day=str(D.alerts.idxmax())),
           guard_flags_per_day=dict(median=float(D.guard_flags.median()), max=int(D.guard_flags.max())), units=s,
           top_days=[[str(d), int(r.alerts), int(r.new_fires), int(r.guard_flags)] for d, r in top.iterrows()])
json.dump(res, open(out / "summary.json", "w"), indent=1); print(json.dumps(res, indent=1))
