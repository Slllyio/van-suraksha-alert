# Webhook delivery test against a throwaway demo database (scripts/demo_replay.py). The server must run with
#   FS_WEBHOOK_URL=http://127.0.0.1:<FS_HOOK_PORT>/ FS_WEBHOOK_SECRET=<FS_HOOK_SECRET> FS_SERVICE_KEYS=<FS_KEY>
# This script is the receiver. It checks: events from the built-in pages (reached, reported, reviewed) arrive signed,
# in order, with an event id and a timestamp signature; an event made while the receiver is down arrives after it is
# back; a resent report (same client_ref) makes no second report and no second event; `since` polling sees the review.
#   FS_URL=... FS_KEY=... FS_HOOK_PORT=8041 FS_HOOK_SECRET=... python scripts/webhook_test.py
import hashlib, hmac, io, json, os, threading, time, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from PIL import Image

B, KEY = os.environ.get("FS_URL", "http://127.0.0.1:8000"), os.environ["FS_KEY"]
PORT, SECRET = int(os.environ.get("FS_HOOK_PORT", "8041")), os.environ.get("FS_HOOK_SECRET", "hooksecret").encode()
GOT, DOWN = [], [False]


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if DOWN[0]:
            self.send_response(503); self.end_headers(); return
        ts = self.headers.get("X-Timestamp", "")
        GOT.append({"event": self.headers.get("X-Event"), "id": int(self.headers.get("X-Event-Id", 0)), "body": json.loads(body),
                    "sig": hmac.compare_digest(hmac.new(SECRET, body, hashlib.sha256).hexdigest(), self.headers.get("X-Signature", "")),
                    "sig_ts": hmac.compare_digest(hmac.new(SECRET, ts.encode() + b"." + body, hashlib.sha256).hexdigest(),
                                                  self.headers.get("X-Signature-Ts", ""))})
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


threading.Thread(target=HTTPServer(("127.0.0.1", PORT), H).serve_forever, daemon=True).start()


def login(sid, pin):
    s = requests.Session(); s.trust_env = False
    s.post(B + "/api/login", json={"staff_id": sid, "pin": pin}).raise_for_status()
    return s


def wait(pred, secs=90):
    t = time.time()
    while time.time() - t < secs:
        if pred():
            return True
        time.sleep(0.5)
    return False


def events(iid):
    return [g["event"] for g in GOT if g["body"]["data"]["id"] == iid]


g, adm = login(3, "3333"), login(1, "1111")
inc = [i for i in g.get(B + "/api/incidents?days=7").json() if i["status"] == "new" and (i["kind"] or "alert") == "alert"][0]
iid, lat, lon = inc["id"], inc["lat"], inc["lon"]
r = g.post(B + "/api/positions", json=[{"lat": lat + 0.0005, "lon": lon, "acc_m": 8}]).json()
assert iid in r["reached"], r
assert wait(lambda: "alert.reached" in events(iid)), GOT
print("reached ->", events(iid))

b = io.BytesIO(); Image.new("RGB", (64, 48), "brown").save(b, "JPEG")
ref = str(uuid.uuid4())
form = {"outcome": "burnt_out", "burn_age": "1_2_days", "cause": "Unknown", "device_lat": lat + 0.0005, "device_lon": lon,
        "device_acc_m": 6, "photo_meta": json.dumps([{"dev_lat": lat + 0.0005, "dev_lon": lon}]), "client_ref": ref}
r1 = g.post(f"{B}/api/incidents/{iid}/reports", data=form, files=[("photos", ("p.jpg", b.getvalue()))]).json()
r2 = g.post(f"{B}/api/incidents/{iid}/reports", data=form, files=[("photos", ("p.jpg", b.getvalue()))]).json()
assert r2.get("duplicate") and r2["report_id"] == r1["report_id"], (r1, r2)
assert wait(lambda: "alert.reported" in events(iid)), GOT
print("report", r1["report_id"], r1["evidence"], "| resend ->", r2["report_id"], "duplicate", r2["duplicate"])

H_ = {"X-Api-Key": KEY}
s = requests.Session(); s.trust_env = False
before = s.get(f"{B}/api/v1/alerts/{iid}", headers=H_).json()["updated_utc"]
DOWN[0] = True
time.sleep(1.1)   # updated_utc has 1 s steps
rv = adm.post(f"{B}/api/incidents/{iid}/review", json={"decision": "revisit", "note": "go again", "report_id": r1["report_id"]})
assert rv.status_code == 200, rv.text
after = s.get(f"{B}/api/v1/alerts/{iid}", headers=H_).json()
assert after["status"] == "revisit" and after["updated_utc"] > before, (before, after["updated_utc"])
polled = s.get(f"{B}/api/v1/alerts", headers=H_, params={"since": after["updated_utc"]}).json()["features"]
assert any(f["id"] == iid for f in polled)
print("send-back while the receiver is down; since poll sees it:", True, "| updated", before, "->", after["updated_utc"])
time.sleep(3)
assert "alert.reviewed" not in events(iid)
DOWN[0] = False
assert wait(lambda: "alert.reviewed" in events(iid), 120), GOT
print("after the receiver is back ->", events(iid))
assert events(iid).count("alert.reported") == 1, events(iid)
ids = [x["id"] for x in GOT]
assert ids == sorted(ids) and len(set(ids)) == len(ids), ids
assert all(x["sig"] and x["sig_ts"] for x in GOT), GOT
print("events in order, signed (body and timestamp), each once:", ids)
print("ALL WEBHOOK CHECKS PASSED")
