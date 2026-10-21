# End-to-end test against a throwaway demo database (demo accounts created with
# scripts/add_staff.py: id 1 admin PIN 1111, id 2 ranger 2222, id 3 guard 3333). Not real users.
import io, json, requests
from fractions import Fraction
from PIL import Image, ImageDraw
import os
B = os.environ.get("FS_URL", "http://127.0.0.1:8000")

def dms(x):
    d = int(x); m = int((x - d) * 60); s = round(((x - d) * 60 - m) * 60, 2)
    return (d, m, s)

def photo(lat, lon, local_time, color):
    im = Image.new("RGB", (800, 600), color); ImageDraw.Draw(im).text((20, 20), f"{lat},{lon}", fill="white")
    ex = Image.Exif()
    ex[306] = local_time
    gps = {1: "N", 2: dms(lat), 3: "E", 4: dms(lon)}
    ex[0x8825] = gps
    b = io.BytesIO(); im.save(b, "JPEG", exif=ex); return b.getvalue()

def login(sid, pin):
    s = requests.Session(); r = s.post(B + "/api/login", json={"staff_id": sid, "pin": pin}); r.raise_for_status(); return s

print("wrong pin ->", requests.post(B + "/api/login", json={"staff_id": 3, "pin": "0000"}).status_code)
g = login(3, "3333")
inc = g.get(B + "/api/incidents?days=7").json(); print("guard sees", [(i["id"], i["beat"], i["status"]) for i in inc])
iid = inc[0]["id"]
inc0 = g.get(f"{B}/api/incidents/{iid}").json()
LAT, LON = inc0["lat"], inc0["lon"]
# Walk towards the fire: positions 3 km, 1 km, then 100 m away -> auto "reached" on the last one
route = [{"lat": LAT - d, "lon": LON, "acc_m": 10, "device_id": "dev-guard"} for d in (0.027, 0.009, 0.0009)]
print("positions", g.post(B + "/api/positions", json=route).json(), "reached at", g.get(f"{B}/api/incidents/{iid}").json()["arrived_utc"])
# Report 1: at the fire, photo after alert -> strong
p1 = photo(LAT + 0.0003, LON + 0.0003, "2026:10:14 15:05:00", (90, 60, 40))
meta = [{"dev_lat": LAT + 0.0002, "dev_lon": LON + 0.0002, "dev_utc": "2026-10-14T09:35:00Z"}]
r = g.post(f"{B}/api/incidents/{iid}/reports", data={"outcome": "burnt_out", "land_type": "Forest", "fire_type": "Ground / litter fire", "area_ha": 1.5,
     "cause": "Mahua collection", "action": "Already out on arrival", "crew": 2, "notes": "test report",
     "device_lat": LAT + 0.0002, "device_lon": LON + 0.0002, "device_acc_m": 8, "photo_meta": json.dumps(meta),
     "device_id": "dev-guard", "first_known_by": "satellite", "fire_out_utc": "2026-10-14T09:50:00Z"},
     files=[("photos", ("a.jpg", p1, "image/jpeg"))]); print("report 1", r.status_code, r.json())
# Report 2: same photo reused + a photo taken 6 km away and before the alert -> weak
p2 = photo(LAT + 0.05, LON, "2026:10:13 10:00:00", (40, 80, 40))
r = g.post(f"{B}/api/incidents/{iid}/reports", data={"outcome": "no_fire", "device_lat": LAT + 0.05, "device_lon": LON, "photo_meta": "[]", "device_id": "dev-other"},
     files=[("photos", ("a.jpg", p1, "image/jpeg")), ("photos", ("b.jpg", p2, "image/jpeg"))]); print("report 2", r.status_code, r.json())
# Guard cannot review; guard cannot see other beats
print("guard review ->", g.post(f"{B}/api/incidents/{iid}/review", json={"decision": "accept"}).status_code)
other = [i for i in login(1, "1111").get(B + "/api/incidents?days=7").json() if i["id"] != iid]
print("guard other beat ->", g.get(f"{B}/api/incidents/{other[0]['id']}").status_code if other else "n/a")
rg = login(2, "2222")
print("ranger sees", [(i["id"], i["status"]) for i in rg.get(B + "/api/incidents?days=7").json()])
print("ranger revisit", rg.post(f"{B}/api/incidents/{iid}/review", json={"decision": "revisit", "note": "Second report has a reused photo"}).json())
print("status now", g.get(f"{B}/api/incidents/{iid}").json()["status"])
r = g.post(f"{B}/api/incidents/{iid}/reports", data={"outcome": "burnt_out", "area_ha": 2, "device_lat": LAT, "device_lon": LON + 0.0003,
     "photo_meta": json.dumps([{"dev_lat": LAT, "dev_lon": LON + 0.0003, "dev_utc": "2026-10-14T10:10:00Z"}]), "device_id": "dev-guard"},
     files=[("photos", ("c.jpg", photo(LAT - 0.0002, LON, "2026:10:14 15:40:00", (120, 50, 30)), "image/jpeg"))]); print("report 3", r.json())
# Another person's report from the guard's phone is flagged
a = login(1, "1111")
print("admin on guard phone", a.post(f"{B}/api/incidents/{iid}/reports", data={"outcome": "burnt_out", "device_id": "dev-guard", "photo_meta": "[]"}).json()["flags"])
print("ranger accept", rg.post(f"{B}/api/incidents/{iid}/review", json={"decision": "accept", "note": "Scar visible, ok"}).json())
d = rg.get(f"{B}/api/incidents/{iid}").json(); print("final", d["status"], d["outcome"], [(x["evidence"], x["flags"]) for x in d["reports"]])
print("stats", json.dumps(rg.get(B + "/api/stats?days=7").json()["total"]))
pid = d["reports"][0]["photos"][0]["id"]; print("photo", rg.get(f"{B}/api/photos/{pid}").status_code, requests.get(f"{B}/api/photos/{pid}").status_code)
print(rg.get(B + "/api/export/incidents.csv").text[:400])
