# Test of the patrol-pilot additions (pilot.py) against a throwaway demo database (scripts/demo_replay.py),
# with FS_SERVICE_KEYS set in the server's environment and the same key passed here:
#   FS_URL=http://127.0.0.1:8000 FS_KEY=... python scripts/pilot_test.py
# Demo accounts (throwaway database only): admin 1111, ranger 2222, guard 3333 (beat 009-001-008, Kevlajhir).
import csv, io, json, os, requests
from PIL import Image
from shapely.geometry import shape

B, KEY = os.environ.get("FS_URL", "http://127.0.0.1:8000"), os.environ["FS_KEY"]
H = {"X-Api-Key": KEY}
BEAT = "009-001-008"


def login(sid, pin):
    s = requests.Session(); s.trust_env = False
    s.post(B + "/api/login", json={"staff_id": sid, "pin": pin}).raise_for_status()
    return s


def jpg(color="green"):
    b = io.BytesIO(); Image.new("RGB", (64, 48), color).save(b, "JPEG"); return b.getvalue()


s = requests.Session(); s.trust_env = False
cells = [r["cell_id"] for r in csv.DictReader(open("/mnt/project-files/ratapani/beats/cell_beat.csv")) if r["beat_uid"] == BEAT][:4]
me = login(3, "3333").get(B + "/api/me").json()
issue = me["now_utc"][:10]
# the list for day t is issued in the evening of t-1; use yesterday so the window covers the demo clock
from datetime import date, timedelta
issue = (date.fromisoformat(issue) - timedelta(days=1)).isoformat()
VER = {"model_hash": "sha256-test", "code_commit": "git-abc123", "config_hash": "sha256-cfg", "data_cutoff_utc": "2027-02-14T12:00:00Z",
       "thresholds": {"daily_total": 456}}
bad = s.post(B + "/api/v1/tasks", headers=H, json={"issue_date": "2026-04-14", "model_hash": "x", "tasks": []})
print("version record incomplete ->", bad.status_code, bad.json()["detail"][:80])
assert bad.status_code == 400
body = {"issue_date": issue, "model_version": VER, "grid": "ratapani",
        "tasks": [{"cell_id": int(c), "score": 0.9 - k / 10} for k, c in enumerate(cells[:3])] + [{"cell_id": int(cells[3]), "near_active_fire": True}]}
r = s.post(B + "/api/v1/tasks", headers=H, json=body).json()
print("tasks", r)
assert len(r["created"]) == 3 and not r["errors"] and len(r["excluded_near_active"]) == 1
r2 = s.post(B + "/api/v1/tasks", headers=H, json=body).json()
print("resend", r2["already_there"], "created", len(r2["created"]))
assert r2["already_there"] == 3 and not r2["created"]

t = s.get(f"{B}/api/v1/alerts/{r['created'][0]}", headers=H).json()
print("task json", {k: t[k] for k in ("kind", "beat", "status")}, {k: v for k, v in t["task"].items() if k != "cell"})
assert t["kind"] == "predicted" and t["task"]["arm"] in ("fixed", "calendar", "forecast")
assert t["task"]["stream"] == "ignition" and t["task"]["model_version"]["code_commit"] == "git-abc123"

g = login(3, "3333")
mine = [i for i in g.get(B + "/api/incidents?days=7").json() if i.get("kind") == "predicted"]
print("guard sees predicted tasks", [i["id"] for i in mine])
assert len(mine) == 3

# Reached only from inside the cell: 60 m outside the edge is not enough, the centre is.
poly = shape(t["task"]["cell"])
x0, y0, x1, y1 = poly.bounds
r = g.post(B + "/api/positions", json=[{"lat": (y0 + y1) / 2, "lon": x1 + 0.0006, "acc_m": 8}]).json()
print("60 m outside ->", r)
assert t["id"] not in r["reached"]
c = poly.centroid
r = g.post(B + "/api/positions", json=[{"lat": c.y, "lon": c.x, "acc_m": 8}]).json()
print("inside ->", r)
assert t["id"] in r["reached"]

# One photo at the centre: arrived, but the inspection is not shown
meta = json.dumps([{"dev_lat": c.y, "dev_lon": c.x, "dev_utc": me["now_utc"]}])
r = g.post(f"{B}/api/incidents/{t['id']}/reports", data={"outcome": "nothing_found", "device_lat": c.y, "device_lon": c.x,
           "device_acc_m": 8, "photo_meta": meta}, files=[("photos", ("a.jpg", jpg(), "image/jpeg"))])
print("nothing_found, one photo ->", r.status_code, r.json())
assert r.ok and r.json()["inspection"] == "arrived" and "arrived_not_inspected" in r.json()["flags"]
# Two photos 150 m apart inside the square: inspected
meta = json.dumps([{"dev_lat": c.y - 0.0007, "dev_lon": c.x, "dev_utc": me["now_utc"]}, {"dev_lat": c.y + 0.0007, "dev_lon": c.x, "dev_utc": me["now_utc"]}])
r = g.post(f"{B}/api/incidents/{t['id']}/reports", data={"outcome": "nothing_found", "device_lat": c.y, "device_lon": c.x,
           "device_acc_m": 8, "photo_meta": meta}, files=[("photos", ("a.jpg", jpg("olive"), "image/jpeg")), ("photos", ("b.jpg", jpg("navy"), "image/jpeg"))])
print("nothing_found, two photos 150 m apart ->", r.json())
assert r.ok and r.json()["inspection"] == "completed" and r.json()["evidence"] == "strong"

alerts = [i for i in g.get(B + "/api/incidents?days=7").json() if i.get("kind", "alert") == "alert"]
a = alerts[0]
r = g.post(f"{B}/api/incidents/{a['id']}/reports", data={"outcome": "nothing_found", "device_lat": a["lat"], "device_lon": a["lon"]})
print("nothing_found on a satellite alert ->", r.status_code)
assert r.status_code == 400

# Burnt cell found on a second task, photo 300 m outside the cell -> flagged
t2 = r_ = s.get(f"{B}/api/v1/alerts/{mine[1]['id']}", headers=H).json()
p2 = shape(t2["task"]["cell"]); c2 = p2.centroid; bx = p2.bounds
far = {"dev_lat": c2.y, "dev_lon": bx[2] + 0.003, "dev_utc": me["now_utc"]}
r = g.post(f"{B}/api/incidents/{t2['id']}/reports", data={"outcome": "burnt_out", "burn_age": "1_2_days", "device_lat": c2.y,
           "device_lon": c2.x, "photo_meta": json.dumps([far])}, files=[("photos", ("b.jpg", jpg(), "image/jpeg"))])
print("burnt cell, photo outside ->", r.json())
assert "outside_cell" in r.json()["flags"] and isinstance(r.json()["linked_alerts"], list)
r = g.post(f"{B}/api/incidents/{t2['id']}/reports", data={"outcome": "burnt_out", "burn_age": "last_week"})
assert r.status_code == 400
r = g.post(f"{B}/api/incidents/{t2['id']}/reports", data={"outcome": "burnt_out", "crosses_beat_boundary": "maybe"})
assert r.status_code == 400

# Protocol v2: only ignition-stream tasks are sent; the recent-fire ranker is stored as a shadow list
r = s.post(B + "/api/v1/tasks", headers=H, json={"issue_date": issue, "stream": "active_fire", "model_version": VER,
           "tasks": [{"cell_id": int(cells[0])}]})
assert r.status_code == 400
r = s.post(B + "/api/v1/tasks", headers=H, json={"issue_date": issue, "shadow": True, "list_name": "recent_fire_ranker",
           "model_version": VER, "tasks": [{"cell_id": int(cells[0]), "score": 0.7}]}).json()
print("shadow list ->", r)
assert r["shadow"] and not r["created"]

# A burnt cell inspected properly, then accepted by the range officer: counts for the primary result
t3 = mine[2]["id"]
p3 = shape(s.get(f"{B}/api/v1/alerts/{t3}", headers=H).json()["task"]["cell"]).centroid
meta = json.dumps([{"dev_lat": p3.y - 0.0007, "dev_lon": p3.x, "dev_utc": me["now_utc"]}, {"dev_lat": p3.y + 0.0007, "dev_lon": p3.x, "dev_utc": me["now_utc"]}])
r = g.post(f"{B}/api/incidents/{t3}/reports", data={"outcome": "burnt_out", "people_met": "4", "enforcement": "warning", "burn_age": "1_2_days", "crosses_beat_boundary": "yes",
           "beats_touched": "Kevlajhir, Bari", "suppression": "fire_line", "suppression_utc": me["now_utc"], "device_lat": p3.y, "device_lon": p3.x,
           "device_acc_m": 6, "photo_meta": meta}, files=[("photos", ("c.jpg", jpg("maroon"), "image/jpeg")), ("photos", ("d.jpg", jpg("teal"), "image/jpeg"))])
print("burnt cell, inspected ->", r.json())
assert r.json()["inspection"] == "completed" and r.json()["evidence"] == "strong" and r.json()["fire_id"]
assert g.post(f"{B}/api/incidents/{t3}/reports", data={"outcome": "burnt_out", "enforcement": "arrest"}).status_code == 400
assert g.post(f"{B}/api/incidents/{t3}/reports", data={"outcome": "burnt_out", "people_met": "-2"}).status_code == 400
fire3 = r.json()["fire_id"]
assert login(2, "2222").post(f"{B}/api/incidents/{t3}/review", json={"decision": "accept"}).ok
r = g.post(f"{B}/api/incidents/{t3}/reports", data={"outcome": "burnt_out", "suppression": "magic"})
assert r.status_code == 400

# Chance find right next to a satellite alert -> linked to it
r = g.post(B + "/api/chance_finds", data={"outcome": "active_fire", "burn_age": "now", "device_lat": a["lat"] + 0.002,
           "device_lon": a["lon"], "device_acc_m": 6, "photo_meta": json.dumps([{"dev_lat": a["lat"] + 0.002, "dev_lon": a["lon"],
           "dev_utc": me["now_utc"]}])}, files=[("photos", ("c.jpg", jpg(), "image/jpeg"))])
print("chance find ->", r.json())
assert r.ok and a["id"] in r.json()["linked_alerts"] and r.json()["fire_id"].startswith("S")
fire_a = r.json()["fire_id"]
r = g.post(B + "/api/chance_finds", data={"outcome": "no_fire", "device_lat": a["lat"], "device_lon": a["lon"]})
assert r.status_code == 400

# Crew-day log
# Crew-day log: 03:00-13:00 UTC with a crew of 3; the cell reports at 12:30 put the day's hours in the ignition stream
print("start day", g.post(B + "/api/shifts/start", json={"crew_size": 3, "lat": c.y, "lon": c.x, "utc": issue[:8] + "15T03:00:00Z"}).json())
print("current", g.get(B + "/api/shifts/current").json()["crew_size"])
print("end day", g.post(B + "/api/shifts/end", json={"lat": c.y, "lon": c.x, "utc": issue[:8] + "15T13:00:00Z"}).json()["end_utc"])
print("v1 shift", s.post(B + "/api/v1/shifts", headers=H, json={"staff_external_id": "enetra-u-17", "beat_uid": BEAT,
                                                              "action": "start", "crew_size": 2}).json()["id"])

st = login(1, "1111").get(B + "/api/stats?days=7").json()
print("stats pilot", st["pilot"], "| alerts", st["total"]["alerts"])
rep = s.get(B + f"/api/v1/pilot/report?start={issue[:4]}-02-15&end={issue[:4]}-06-15", headers=H).json()
print("report", json.dumps(rep["arms"]["forecast"], indent=None))
f = rep["arms"]["forecast"]
assert f["ignition"]["inspected"] == 2 and f["fires_crossing_beats"] == 1 and f["fires_suppressed"] == 1
assert f["staff_hours"]["ignition"] == 30.0 and f["ignition"]["fires_verified_no_recent_viirs"] == 1 and f["ignition"]["fires_new"] == 1
assert f["primary"]["confirmed_starts_ignition"] == 1 and f["primary"]["per_100_ignition_person_hours"] == 3.33
assert f["primary"]["rate_ratio_label"] == "beat bootstrap, not the locked analysis" and len(rep["shadow_lists"]) == 1
print("missed", len(rep["missed"]), rep["missed"][:1])
csvt = login(2, "2222").get(B + f"/api/pilot/missed.csv?start={issue[:4]}-02-15&end={issue[:4]}-06-15").text
print("missed.csv lines", len(csvt.splitlines()))

# ---------- protocol v3 ----------
day = me["now_utc"][:10]
T = lambda hm: f"{day}T{hm}:00Z"
# Phone track for the crew-day: 3 km walk in, 40 min inside cell 3, then away
track = [("11:30", p3.y + 0.027), ("11:45", p3.y + 0.0135), ("12:00", p3.y), ("12:10", p3.y + 0.0003), ("12:20", p3.y),
         ("12:40", p3.y - 0.0003), ("12:50", p3.y - 0.009), ("12:58", p3.y - 0.012)]
g.post(B + "/api/positions", json=[{"lat": y, "lon": p3.x, "acc_m": 8, "utc": T(hm)} for hm, y in track]).raise_for_status()
rep = s.get(B + f"/api/v1/pilot/report?start={day[:4]}-02-15&end={day[:4]}-06-15", headers=H).json()
f = rep["arms"]["forecast"]
ph = f["person_hours"]
print("person-hours", ph)
tot = sum(v for d in ph.values() for v in d.values())
assert abs(tot - 30.0) < 0.2, tot
assert ph["ignition"]["on_site"] >= 1.5 and ph["ignition"]["travel"] >= 1.0 and ph["ignition"]["no_positions"] >= 20

# Dedup: a second report 200 m from cell 3's fire, no satellite event -> the same fire, still credited to the inspection
r = g.post(B + "/api/chance_finds", data={"outcome": "burnt_out", "burn_age": "1_2_days", "device_lat": p3.y + 0.0018,
           "device_lon": p3.x, "device_acc_m": 6, "photo_meta": json.dumps([{"dev_lat": p3.y + 0.0018, "dev_lon": p3.x,
           "dev_utc": me["now_utc"]}])}, files=[("photos", ("e.jpg", jpg("purple"), "image/jpeg"))]).json()
print("second report on the same fire ->", r["fire_id"], "(cell 3 fire", fire3 + ")")
assert r["fire_id"] == fire3

# Post-season grouping; the chance find next to an alert turns out to be a separate fire -> blind review
r = s.post(B + "/api/v1/pilot/grouping", headers=H, json=[
    {"fire_id": fire3, "grouping": "no_satellite_event", "est_ignition_utc": T("02:30")},
    {"fire_id": fire_a, "grouping": "separate_fire", "chips": [{"label": "before", "url": "https://example.org/before.png"}]},
    {"fire_id": "F999999", "grouping": "none"}]).json()
print("grouping", r)
assert r["updated"] == 2 and len(r["errors"]) == 1
adm, rng = login(1, "1111"), login(2, "2222")
q = adm.get(B + "/api/review/fires").json()
print("review queue", [(c["case"], c["question"], c["needs"]) for c in q])
assert [c["case"] for c in q] == [fire_a]
blob = json.dumps(q)
assert '"arm"' not in blob and "beat" not in blob and "model" not in blob
assert adm.post(f"{B}/api/review/fires/{fire_a}/verdict", json={"verdict": "confirmed_start", "reason": ""}).status_code == 400
assert adm.post(f"{B}/api/review/fires/{fire_a}/verdict", json={"verdict": "confirmed_start", "reason": "fresh ash, alert 1 km off"}).json()["class_final"] is None
assert rng.post(f"{B}/api/review/fires/{fire_a}/verdict", json={"verdict": "continuation", "reason": "same smoke column"}).json()["class_final"] is None
import secrets
pin = str(secrets.randbelow(9000) + 1000)
third = adm.post(B + "/api/staff", json={"name": "Analyst", "role": "admin", "pin": pin}).json()["id"]
r = login(third, pin).post(f"{B}/api/review/fires/{fire_a}/verdict", json={"verdict": "confirmed_start", "reason": "scar separate on chip"}).json()
print("third reviewer ->", r)
assert r["class_final"] == "confirmed_start" and r["verdicts"] == 3
assert adm.get(B + "/api/review/fires").json() == []

rep = s.get(B + f"/api/v1/pilot/report?start={day[:4]}-02-15&end={day[:4]}-06-15", headers=H).json()
fs = {a: o["fires"] for a, o in rep["arms"].items()}
print("fires by arm", json.dumps(fs))
assert fs["forecast"]["confirmed_starts"]["ignition"] == 1 and fs["forecast"]["found_not_credited"] >= 1
assert sum(x["confirmed_starts"]["chance"] for x in fs.values()) == 1
assert fs["forecast"]["time_to_discovery_h"]["ignition"]["median"] >= 9.5
# Primary counts only range-officer-accepted reports: the chance find was never accepted
assert sum(x["confirmed_starts_accepted"]["chance"] for x in fs.values()) == 0
assert rep["arms"]["forecast"]["primary"]["sensitivity"]["per_100_no_acceptance_required"] == 3.33
e = rep["arms"]["forecast"]["effort"]
print("effort", e)
assert e["people_met"] == 4 and e["warnings"] == 1 and e["forest_km2"] > 0 and e["person_hours_per_km2_per_week"] > 0

rows = list(csv.DictReader(io.StringIO(s.get(B + f"/api/v1/pilot/beats.csv?start={day[:4]}-02-15&end={day[:4]}-06-15", headers=H).text)))
print("beats.csv", len(rows), "rows; columns", list(rows[0])[:8], "...")
assert len(rows) == 94 and rows[0]["block"] and sum(int(x["starts_ignition"]) for x in rows) == 1
assert sum(int(x["starts_chance"]) for x in rows) == 0 and sum(int(x["starts_chance_no_acceptance"]) for x in rows) == 1
assert abs(sum(float(x["ph_total"]) for x in rows if x["arm"] == "forecast") - tot) < 0.2
sd = adm.get(B + f"/api/pilot/shakedown?start={day[:4]}-04-01&end={day[:4]}-04-30").json()
print("shakedown", json.dumps(sd["arms"]["forecast"]))
assert sd["arms"]["forecast"]["shifts"] >= 1 and set(sd["arms"]) == {"fixed", "calendar", "forecast"}
ex = adm.get(B + "/api/export/incidents.csv?days=30").text.splitlines()[0]
assert "block" in ex and "fire_id" in ex and "site_entry_utc" in ex
print("ALL PILOT CHECKS PASSED")
