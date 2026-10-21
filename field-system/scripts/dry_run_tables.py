# Every alert of the 2026 dry run, by day and by division / range / beat, as one spreadsheet.
#   FS_DATA_DIR=<dry-run folder> python scripts/dry_run_tables.py docs/dry_run_2026/dry_run_2026_tables.xlsx
# Days are IST dates of an alert's first satellite point; the season is 15 Feb-15 Jun 2026.
import json, sys
from datetime import timedelta
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db
from app.geo import Beats

IST = timedelta(hours=5, minutes=30)
B = Beats()
db.init()
with db.tx() as con:
    inc = pd.read_sql("SELECT * FROM incidents WHERE COALESCE(kind,'alert')='alert'", con)
    bf = {r[0]: json.loads(r[1]) for r in con.execute("SELECT incident_id, data FROM big_fire_score")}
    rw = {r[0]: (r[1], json.loads(r[2]) if r[2] else {}) for r in con.execute("SELECT incident_id, status, data FROM fire_runway")}
    dr = {r[0]: (r[1], json.loads(r[2]) if r[2] else {}) for r in con.execute("SELECT incident_id, status, data FROM fire_direction")}
    det = pd.read_sql("""SELECT incident_id, instrument, satellite, acq_utc, frp, daynight FROM detections WHERE incident_id IS NOT NULL""", con)
    nb = dict(con.execute("SELECT incident_id, count(*) FROM incident_beats GROUP BY 1").fetchall())

t = lambda s: pd.to_datetime(s, utc=True).dt.tz_convert(None) + IST
inc["first_ist"], inc["last_ist"], inc["due_ist"] = t(inc.first_seen_utc), t(inc.last_seen_utc), t(inc.due_utc)
inc["day"] = inc.first_ist.dt.date
inc = inc[(inc.first_ist >= "2026-02-15") & (inc.first_ist < "2026-06-16")].copy()
p = lambda u, k: B.by_uid.get(u, {}).get(k, "")
inc["division"] = inc.beat_uid.map(lambda u: p(u, "division")); inc["range"] = inc.beat_uid.map(lambda u: p(u, "range"))
inc["beat"] = inc.beat_uid.map(lambda u: p(u, "beat"))
inc["beats_touched"] = inc.id.map(lambda i: nb.get(i, 1))
d1 = det.groupby("incident_id")
inc["first_sensor"] = inc.id.map(d1.apply(lambda g: g.sort_values("acq_utc").iloc[0]["satellite"]))
inc["night_first"] = inc.id.map(d1.apply(lambda g: g.sort_values("acq_utc").iloc[0]["daynight"] == "N"))
inc["viirs_points"] = inc.id.map(det[det.instrument == "VIIRS"].groupby("incident_id").size()).fillna(0).astype(int)
inc["modis_points"] = inc.id.map(det[det.instrument == "MODIS"].groupby("incident_id").size()).fillna(0).astype(int)
inc["days_seen"] = ((inc.last_ist - inc.first_ist).dt.total_seconds() / 86400).round(1)
g = lambda i, k, dflt=None: bf.get(i, {}).get(k, dflt)
inc["new_fire"] = inc.id.map(lambda i: g(i, "new_fire"))
inc["big_fire_points"] = inc.id.map(lambda i: g(i, "points") if g(i, "new_fire") else None)
inc["guard_big_fire_flag"] = inc.id.map(lambda i: bool(g(i, "guard_flag", False)))
inc["fsi_large_fire"] = inc.large.astype(bool)
inc["runway_hint"] = inc.id.map(lambda i: rw[i][1].get("text") if i in rw and rw[i][0] == "found" else None)
inc["arrow_hint"] = inc.id.map(lambda i: f'Heading {dr[i][1]["heading"]} ({dr[i][1]["sensor"]})' if i in dr and dr[i][0] == "found" else None)
inc["no_viirs_yet"] = inc.viirs_points.eq(0)

A = inc.sort_values("first_ist")
alerts = pd.DataFrame({
    "alert_id": A.id, "date_IST": A.day, "first_seen_IST": A.first_ist.dt.strftime("%Y-%m-%d %H:%M"),
    "last_seen_IST": A.last_ist.dt.strftime("%Y-%m-%d %H:%M"), "days_seen": A.days_seen, "division": A.division, "range": A.range,
    "beat": A.beat, "beat_uid": A.beat_uid, "beats_touched": A.beats_touched, "lat": A.lat.round(5), "lon": A.lon.round(5),
    "first_satellite": A.first_sensor, "first_seen_at_night": A.night_first, "viirs_points": A.viirs_points,
    "modis_points": A.modis_points, "max_frp_MW": A.max_frp, "fsi_large_fire_3px": A.fsi_large_fire,
    "new_fire": A.new_fire, "big_fire_points": A.big_fire_points, "guard_big_fire_flag": A.guard_big_fire_flag,
    "runway_hint": A.runway_hint, "arrow_hint": A.arrow_hint, "visit_due_IST": A.due_ist.dt.strftime("%Y-%m-%d %H:%M")})


INTS = ["alerts", "new_fires", "guard_big_fire_flags", "fsi_large_fires", "first_seen_at_night", "modis_only_at_first",
        "with_runway_hint", "with_arrow_hint"]


def ints(df):
    return df.astype({c: int for c in INTS if c in df})


def agg(df):
    return pd.Series({"alerts": len(df), "new_fires": int((df.new_fire == True).sum()),
                      "guard_big_fire_flags": int(df.guard_big_fire_flag.sum()), "fsi_large_fires": int(df.fsi_large_fire.sum()),
                      "first_seen_at_night": int(df.night_first.sum()), "modis_only_at_first": int(df.no_viirs_yet.sum()),
                      "max_big_fire_points": df.big_fire_points.max(), "with_runway_hint": int(df.runway_hint.notna().sum()),
                      "with_arrow_hint": int(df.arrow_hint.notna().sum())})


daily = ints(inc.groupby("day").apply(agg).reset_index())
busy = inc.groupby(["day", "division"]).size().reset_index(name="n").sort_values("n").groupby("day").tail(1).set_index("day")
daily["divisions_with_alerts"] = daily.day.map(inc.groupby("day").division.nunique())
daily["ranges_with_alerts"] = daily.day.map(inc.groupby("day").range.nunique())
daily["beats_with_alerts"] = daily.day.map(inc.groupby("day").beat_uid.nunique())
daily["busiest_division"] = daily.day.map(busy.division); daily["busiest_division_alerts"] = daily.day.map(busy.n)
daily = daily.rename(columns={"day": "date_IST"})

dd = ints(inc.groupby(["day", "division"]).apply(agg).reset_index())
dd["ranges_with_alerts"] = [inc[(inc.day == a) & (inc.division == b)].range.nunique() for a, b in zip(dd.day, dd.division)]
dd["max_alerts_one_beat"] = [inc[(inc.day == a) & (inc.division == b)].beat_uid.value_counts().max() for a, b in zip(dd.day, dd.division)]
dd = dd.rename(columns={"day": "date_IST"})
grid = dd.pivot_table(index="date_IST", columns="division", values="alerts", fill_value=0).reset_index()


def season(keys):
    s = ints(inc.groupby(keys).apply(agg).reset_index())
    per = inc.groupby(keys + ["day"]).size().reset_index(name="n")
    pk = per.sort_values("n").groupby(keys).tail(1).set_index(keys)
    s = s.set_index(keys)
    s["days_with_alerts"] = per.groupby(keys).size()
    s["peak_day"] = pk.day; s["peak_day_alerts"] = pk.n
    s["median_alerts_on_active_days"] = per.groupby(keys).n.median()
    s["share_of_state_alerts_%"] = (100 * s.alerts / len(inc)).round(2)
    return s.reset_index().sort_values("alerts", ascending=False)


div, rng, beat = season(["division"]), season(["division", "range"]), season(["division", "range", "beat", "beat_uid"])
monthly = inc.assign(month=inc.first_ist.dt.strftime("%Y-%m")).pivot_table(index="division", columns="month", values="id", aggfunc="count", fill_value=0)
monthly["total"] = monthly.sum(axis=1); monthly = monthly.sort_values("total", ascending=False).reset_index()

readme = pd.DataFrame({"What": [
    "Source", "Days", "Alert", "New fire", "Big-fire points", "Guard big-fire flag", "FSI large fire", "Runway hint", "Arrow hint",
    "Visits", "Sheets"], "Meaning": [
    "The 2026 dry run: every FIRMS point of 15 Feb-15 Jun 2026 (VIIRS x3 + MODIS) through the app's live intake with the forest filter on. Replay, not live.",
    "IST date of the alert's first satellite point.",
    "One field task for one beat: points within 1.5 km and 48 h join the same alert. A fire burning for days can be one alert.",
    "First look not linked to a fire seen in the last 30 h (the big-fire rule). Only new fires get points and the runway hint.",
    "Officials only: higher = more likely to pass 200 ha. Ranking, not a %.",
    "Guards told 'may become a big fire': 12+ points.",
    "FSI's rule: 3+ touching VIIRS pixels in one pass.",
    "'Likely to burn farther toward X' (officials). Filled for every new fire.",
    "30 m Sentinel-2/Landsat direction. Only 22 Apr and Khandwa 17 Mar were checked in the dry run (it needs a scene download per alert).",
    "Nobody visited in a replay, so visit columns are only the due time.",
    "Daily statewide; Day x division; Division grid (alerts per day, one column per division); Division season; Range season; Beat season; Division by month; All alerts."]})

out = sys.argv[1]
with pd.ExcelWriter(out, engine="openpyxl") as w:
    for name, df in [("Read me", readme), ("Daily statewide", daily), ("Day x division", dd), ("Division grid", grid),
                     ("Division season", div), ("Range season", rng), ("Beat season", beat), ("Division by month", monthly),
                     ("All alerts", alerts)]:
        df.to_excel(w, sheet_name=name, index=False)
        ws = w.sheets[name]; ws.freeze_panes = "B2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(48, max(9, max(len(str(c.value or "")) for c in col[:200]) + 2))
for name, df in [("daily_statewide", daily), ("day_by_division", dd), ("division_season", div), ("range_season", rng), ("all_alerts", alerts)]:
    df.to_csv(Path(out).with_name(f"{name}.csv"), index=False)
print(len(inc), "alerts;", inc.division.nunique(), "divisions;", inc.day.nunique(), "days")
print(div.head(10)[["division", "alerts", "new_fires", "guard_big_fire_flags", "fsi_large_fires", "peak_day", "peak_day_alerts"]].to_string(index=False))
