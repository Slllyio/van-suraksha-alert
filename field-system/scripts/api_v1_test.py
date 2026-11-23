# Test of the /api/v1 integration (what eNetra's app and dashboard would call).
# Run against a throwaway database with FS_SERVICE_KEYS set in the server's environment;
# pass the same key here: FS_URL=... FS_KEY=... python scripts/api_v1_test.py
import io, json, os, requests
from PIL import Image
B, KEY = os.environ.get("FS_URL", "http://127.0.0.1:8000"), os.environ["FS_KEY"]
H = {"X-Api-Key": KEY}
s = requests.Session(); s.trust_env = False

print("no key ->", s.get(B + "/api/v1/alerts").status_code)
fc = s.get(B + "/api/v1/alerts", headers=H).json()
print("alerts", len(fc["features"]), "first:", json.dumps(fc["features"][0]["properties"])[:300])
a = fc["features"][0]["properties"]
lat, lon = a["lat"], a["lon"]
one = s.get(f"{B}/api/v1/alerts/{a['id']}", headers=H).json()
print("points", [(p["source"], p["forest_share"]) for p in one["points"]])

r = s.post(B + "/api/v1/positions", headers=H, json={"staff_external_id": "enetra-u-17", "staff_name": "Guard (eNetra)",
           "beat_uids": a["all_beat_uids"], "positions": [{"lat": lat - 0.02, "lon": lon, "acc_m": 8}, {"lat": lat + 0.0008, "lon": lon, "acc_m": 6}]})
print("positions", r.json())

im = Image.new("RGB", (640, 480), (90, 60, 40)); b = io.BytesIO(); im.save(b, "JPEG")
rep = {"outcome": "burnt_out", "land_type": "Forest", "fire_type": "Ground / litter fire", "area_ha": 0.8, "cause": "Unknown",
       "first_known_by": "satellite", "device_id": "android-abc", "device_lat": lat + 0.0005, "device_lon": lon, "device_acc_m": 5}
meta = [{"dev_lat": lat + 0.0005, "dev_lon": lon, "dev_utc": "2026-10-14T15:40:00Z", "mock_location": False}]
r = s.post(f"{B}/api/v1/alerts/{a['id']}/reports", headers=H,
           data={"staff_external_id": "enetra-u-17", "report": json.dumps(rep), "photo_meta": json.dumps(meta)},
           files=[("photos", ("p.jpg", b.getvalue(), "image/jpeg"))])
print("report", r.status_code, {k: r.json()[k] for k in ("evidence", "flags", "distance_km")})
# A mocked GPS from a native app downgrades proof
im2 = Image.new("RGB", (640, 480), (20, 60, 40)); b2 = io.BytesIO(); im2.save(b2, "JPEG")
r = s.post(f"{B}/api/v1/alerts/{a['id']}/reports", headers=H,
           data={"staff_external_id": "enetra-u-17", "report": json.dumps(rep), "photo_meta": json.dumps([dict(meta[0], mock_location=True)])},
           files=[("photos", ("q.jpg", b2.getvalue(), "image/jpeg"))])
print("mock report", {k: r.json()[k] for k in ("evidence", "flags")})
print("review", s.post(f"{B}/api/v1/alerts/{a['id']}/review", headers=H,
      json={"reviewer_external_id": "enetra-ro-3", "decision": "accept"}).json()["status"])
one = s.get(f"{B}/api/v1/alerts/{a['id']}", headers=H).json()
print("photo url", one["reports"][0]["photos"][0]["url"], s.get(B + one["reports"][0]["photos"][0]["url"], headers=H).status_code)
summ = s.get(B + "/api/v1/beats/summary?days=7", headers=H).json()["beats"]
print("beat summary", [b for b in summ if b["beat_uid"] == a["beat_uid"]])
# Officials' daily brief (16:00 IST): statewide, then the visited alert's division
st = s.get(B + "/api/v1/brief", headers=H).json()
dv = BEATS_DIV = summ[0]["division"] if summ else None
one_div = s.get(B + f"/api/v1/brief?division={dv}", headers=H).json() if dv else {}
assert "divisions" in st and (not dv or "counts" in one_div), (st, one_div)
print("brief", len(st["divisions"]), "divisions;", dv, one_div.get("counts"))
sc = s.get(B + "/api/v1/scar_check?day=2026-04-22", headers=H).json()
assert "ranges" in sc, sc
print("scar check", sc["week_ist"], len(sc["ranges"]), "ranges")
