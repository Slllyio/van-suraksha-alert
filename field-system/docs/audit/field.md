# Audit: field workflow and eNetra integration

Scope: a task reaching a guard, then the visit, report, photos, positions and "reached", then the range officer's accept or send-back, the blind fire review, the `/api/v1` alerts, reports, positions, review and auth parts, the webhook, and DB migrations.
Files read: `app/server.py`, `app/api_v1.py`, `app/evidence.py`, `app/pilot.py` (Place, tasks, inspection, sites, fires, verdicts, review queue), `app/webhook.py`, `app/db.py`, `app/static/field.html`, `common.js`, `control.html`, `review.html`, and the five scripts named in the brief.
Date: 20 Oct 2026. No file under `field-system/` was changed except this one.

## How it was tested

- Throwaway DB: `FS_DATA_DIR=/tmp/claude-0/audit_field/var python3 scripts/demo_replay.py 2026-04-15` (104 alerts, demo accounts admin 1111, ranger 2222, guard 3333).
- Server (port 8012): `FS_DEMO_NOW=2026-04-15T12:30:00Z FS_SERVICE_KEYS=testkey FS_FSI_PORTAL=0 FS_BHUVAN=0 FS_SCAR_LIVE=0 FS_DIRECTION=0 FS_RUNWAY=0`. The webhook pointed at a local signed receiver (`tests/hook_receiver.py`, port 8013). Two clock-dependent checks used a second server on real time (port 8015, `FS_POLL_MINUTES=0`).
- All scratch is in `/tmp/claude-0/audit_field/`: tests in `tests/`, outputs in `out_*.txt`. The servers and the receiver were stopped by PID afterwards.
- `tests/field_queue_test.js` runs the real `field.html` and `common.js` script in Node, with mock IndexedDB, localStorage, fetch and GPS. This exercises the phone's offline queue without a browser.

**Existing tests**
- Against one shared DB: `flow_test.py` and `api_v1_test.py` pass. `pilot_test.py` then fails at line 147: `staff_hours.ignition` is 1.5, expected 30.0. The cause is that flow_test's alert reports by the same guard move the shift's hours to the response stream.
- On a fresh DB, `pilot_test.py` passes ("ALL PILOT CHECKS PASSED").
- So the suite depends on run order: each test needs its own DB. This is noted under L9.

## Summary

| Severity | Count |
|---|---|
| Critical | 3 |
| High | 9 |
| Medium | 10 |
| Low | 10 |

**Checked and found sound**
- All SQL is parameterised. The f-strings only add `?` lists or fixed text, so there is no SQL injection.
- Photo paths are built on the server (`photos/<iid>/r<rid>_<k>.<fmt>`) and the client filename is ignored, so there is no path traversal.
- PINs are hashed with PBKDF2-SHA256 (100k rounds, salted) and compared with `compare_digest`.
- Expired sessions and deactivated staff get 401 (X1, X2). The service key gets 401 when missing, wrong or empty (A10).
- Guards stay in their beat for incidents, detail, reports, photos and route. Rangers stay in their range. An unknown range or beat fails closed.
- Notes, names, cause and action are escaped in `control.html` and `field.html`.
- The 6-photo and 15 MB limits are enforced, though only after the whole upload has been read (see M1).
- A database with only the base schema upgrades cleanly (M1 in `out_migrate.txt`).
- Webhook signatures check out with the shared secret (W3).

---

## Critical

### C1. The phone deletes a report the server rejects, and tells the guard "Report sent"
`app/static/field.html:33` (flush) and `:182-185` (send)

**What goes wrong**
- `flush()` deletes an outbox item on `r.ok || r.status === 400 || r.status === 404`.
- `send()` then shows "Report sent. Thank you." because `flush()` returned 0 left.

**How a report gets rejected (these happen in the field)**
- A photo over 15 MB gives 400 (R2).
- The 2027 cause check can turn on after the guard loaded the list. The tag is provisional for 3 days, and `cause_required` is computed again at submit time. The answer is 400.
- The guard's beat is reassigned, or another person signs in on the shared phone before the queue flushes. The answer is 404.

**Effect:** the report, photos included, is gone from the phone with no trace on the server.

**Reproduced:** `node tests/field_queue_test.js` (`out_field_queue.txt`)
```
[J1 400 on a queued report] left_in_queue=0 | stored_on_phone=0 | screen_would_say="Report sent"
[J1b 404 (beat changed / other user signed in)] left=0 | stored_on_phone=0
```
`tests/t_reports.py`: `[R2 16 MB photo] status=400 | body={"detail":"photo over 15 MB"}`

**Patch:** keep rejected items and show the reason. This goes with C1's idempotency key, so a retry is always safe.
```diff
--- a/app/static/field.html
+++ b/app/static/field.html
@@ -29,9 +29,16 @@
 async function flush() {
+  if (flush.busy) return flush.busy;   // one flush at a time: send(), the 'online' event and "Send now" can overlap (H1)
+  return flush.busy = (async () => { try {
   const keys = await outbox('keys'); let left = keys.length;
+  const why = [];
   for (const k of keys) { const it = await outbox('get', null, k); const fd = new FormData();
     Object.entries(it.fields).forEach(([a, b]) => b !== '' && b != null && fd.append(a, b)); it.photos.forEach((p, j) => fd.append('photos', p, 'photo' + j + '.jpg'));
-    try { const r = await fetch(it.url || `/api/incidents/${it.iid}/reports`, {method: 'POST', body: fd}); if (r.ok || r.status === 400 || r.status === 404) { await outbox('del', null, k); left--; } } catch (e) { break; } }
-  document.getElementById('outbox').innerHTML = left ? `<div class="banner">${left} report${left>1?'s':''} saved on this phone, will send when there is signal. <button class="btn alt" onclick="flush()">Send now</button></div>` : '';
+    try { const r = await fetch(it.url || `/api/incidents/${it.iid}/reports`, {method: 'POST', body: fd});
+      if (r.ok) { await outbox('del', null, k); left--; }
+      else if (r.status !== 401) why.push(`alert ${it.iid ?? 'new fire'}: ${(await r.json().catch(() => ({}))).detail || 'server error ' + r.status}`);
+    } catch (e) { break; } }
+  document.getElementById('outbox').innerHTML = left ? `<div class="banner">${left} report${left>1?'s':''} saved on this phone, not sent yet.
+    ${why.map(esc).join('<br>')} <button class="btn alt" onclick="flush()">Send now</button></div>` : '';
   return left;
+  } finally { flush.busy = null; } })();
 }
@@ -181 +188 @@
-  await outbox('add', {iid: CUR.id, url: CUR.id == null ? '/api/chance_finds' : null, fields, photos: SHOTS.map(s => s.file)});
+  fields.client_ref = crypto.randomUUID();   // idempotency key, fixed when the report is saved (H1)
+  await outbox('add', {iid: CUR.id, url: CUR.id == null ? '/api/chance_finds' : null, fields, photos: SHOTS.map(s => s.file)});
```
A 4xx report then needs a way out: an "Edit / Discard" button on the banner. The guard decides, and the phone never deletes silently.

### C2. PINs can be brute-forced. The staff list is public.
`app/server.py:129-145`

**What goes wrong**
- `/api/staff` needs no login. It lists every active account's id, name, role and beat (A1).
- `/api/login` has no attempt limit, delay or lockout.
- 300 wrong PINs took 9.5 s on one connection, and the right PIN still worked. The whole 4-digit space would take about 5 minutes on a single thread, less in parallel.
- `POST /api/staff` and `scripts/add_staff.py` accept any PIN, even an empty one (A5).
- The admin account (id 1) is the obvious target. With it an attacker can file reports that pass the proof checks, accept them, add staff and export data. A guard account is enough for fake visits.
- README plans a cloud VM or a tunnel, so the login is exposed to the internet.

**Reproduced:** `tests/t_auth.py` (`out_auth.txt`)
```
[A1 staff list without login] status=200 | rows=3 | sample={'id': 1, 'name': 'Demo admin', 'role': 'admin', ...}
[A2 brute force] attempts=300 | codes={403: 300} | seconds=9.5 | per_s=31.5 | right_pin_after=200 | est_full_4digit_space_min=5.3
[A5 empty PIN accepted] status=200 | body={'id': 5}
[A5 login with empty PIN] status=200
```
**Patch** (per-account and per-IP throttle, minimum PIN length):
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -133,9 +133,27 @@
+_FAILS = {}   # key -> (count, locked_until); in-process is enough for one server
+
+def _check_lock(key):
+    n, until = _FAILS.get(key, (0, 0))
+    if until > time.time():
+        raise HTTPException(429, "too many wrong PINs; try again in a few minutes")
+
+def _fail(key):
+    n = _FAILS.get(key, (0, 0))[0] + 1
+    _FAILS[key] = (n, time.time() + min(3600, 30 * 2 ** max(0, n - 5)) if n >= 5 else 0)
+
 @app.post("/api/login")
-def login(body: Login, response: Response):
+def login(body: Login, response: Response, request: Request):
+    keys = (f"staff:{body.staff_id}", f"ip:{request.client.host}")
+    for k in keys:
+        _check_lock(k)
     with db.tx() as con:
         s = con.execute("SELECT * FROM staff WHERE id=? AND active=1", (body.staff_id,)).fetchone()
         if not s or not pin_ok(body.pin, s["pin_hash"]):
+            for k in keys:
+                _fail(k)
             raise HTTPException(403, "wrong PIN")
+        for k in keys:
+            _FAILS.pop(k, None)
@@ -172,4 +190,6 @@ def add_staff(body: NewStaff, me=Depends(supervisor)):
     if me["role"] != "admin" or body.role not in ("guard", "ranger", "admin"):
         raise HTTPException(403, "admins add staff; role must be guard, ranger or admin")
+    if not (body.pin.isdigit() and len(body.pin) >= 6):
+        raise HTTPException(400, "PIN must be at least 6 digits")
```
Add the same PIN check in `scripts/add_staff.py`, and import `Request` from fastapi. For admins, use a longer PIN or a passphrase. The `/api/staff` list could become name-only search, so it no longer exposes role, beat and id. Behind a proxy, use the forwarded client IP.

### C3. eNetra loses status changes: no retry, and `since` polling cannot recover them
`app/webhook.py:108-121`, `app/api_v1.py:147`

**What goes wrong**
- `webhook.send` makes one attempt in a thread and only logs failures. There is no outbox, retry, event id, timestamp or ordering.
- If eNetra is down for a moment, an `alert.reviewed` event (for example a send-back) is lost.
- INTEGRATION.md offers polling as the alternative. But `/api/v1/alerts?since=` only compares `last_seen_utc`, `first_report_utc` and `created_utc`. None of these change on review, send-back or reached.
- So a send-back after the first report never reaches an eNetra poller, and the guard in eNetra is never told to go back. A late "reached" is lost the same way.
- Webhooks run in separate threads, so `alert.reported` and `alert.reviewed` for one alert can arrive out of order.
- The body is signed without a timestamp or id, so a captured event can be replayed.

**Reproduced**
- `tests/t_webhook_v1.py` (`out_webhook.txt`): the receiver was stopped, the review sent, the receiver restarted. The event was never delivered:
  ```
  [W4 eNetra down during review] review_status=200 | engine_status={'status': 'verified'} | failures_logged=1 | redelivered_after_restart=False
  [W3 v1 report webhook] ... headers=[..., 'X-Event', 'X-Signature']   (no event id, no timestamp)
  ```
- `tests/t_since.py` on the real-clock server (`out_since.txt`):
  ```
  [W4b poll since last poll after a send-back] since=2026-10-20T16:11:28Z | alert_returned=False | n_returned=0
  [W4c poll after 'reached'] reached=True | alert_returned=False
  ```

**Patch:** an `updated_utc` that every change bumps, `since` on it, and a durable outbox with retries.
```diff
--- a/app/db.py
+++ b/app/db.py
@@ -420,2 +420,13 @@ MIGRATIONS = [
     "ALTER TABLE reports ADD COLUMN enforcement TEXT",
+    "ALTER TABLE incidents ADD COLUMN updated_utc TEXT",
+    """CREATE TRIGGER IF NOT EXISTS inc_touch AFTER UPDATE ON incidents WHEN NEW.updated_utc IS OLD.updated_utc
+       BEGIN UPDATE incidents SET updated_utc = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = NEW.id; END""",
+    "CREATE INDEX IF NOT EXISTS inc_updated ON incidents(updated_utc)",
+    """CREATE TABLE IF NOT EXISTS webhook_outbox (id INTEGER PRIMARY KEY, event TEXT NOT NULL, body BLOB NOT NULL,
+       created_utc TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0, next_utc TEXT NOT NULL, sent_utc TEXT, last_error TEXT)""",
 ]
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -146,3 +146,3 @@
     if since:
-        q += " AND (i.last_seen_utc >= ? OR i.first_report_utc >= ? OR i.created_utc >= ?)"
-        args += [since] * 3
+        q += " AND coalesce(i.updated_utc, i.created_utc) >= ?"
+        args.append(since)
--- a/app/webhook.py
+++ b/app/webhook.py
@@ -108,14 +108,40 @@
-def send(event, payload):
-    if not config.WEBHOOK_URL:
-        return
-    body = json.dumps({"event": event, "data": payload}, default=str).encode()
-    headers = {"Content-Type": "application/json", "X-Event": event}
-    if config.WEBHOOK_SECRET:
-        headers["X-Signature"] = hmac.new(config.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
-
-    def go():
-        try:
-            urllib.request.urlopen(urllib.request.Request(config.WEBHOOK_URL, data=body, headers=headers), timeout=30)
-        except Exception as e:
-            log.warning("webhook %s failed: %s", event, e)
-    threading.Thread(target=go, daemon=True).start()
+def send(event, payload):
+    """Queue the event durably; one worker delivers in id order with backoff, so nothing is lost while eNetra is down."""
+    if not config.WEBHOOK_URL:
+        return
+    from . import db
+    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
+    with db.tx() as con:
+        cur = con.execute("INSERT INTO webhook_outbox(event, body, created_utc, next_utc) VALUES (?,?,?,?)",
+                          (event, b"", now, now))
+        body = json.dumps({"id": cur.lastrowid, "event": event, "sent_utc": now, "data": payload}, default=str).encode()
+        con.execute("UPDATE webhook_outbox SET body=? WHERE id=?", (body, cur.lastrowid))
+    _wake.set()
+
+def _worker():   # started once from server.startup()
+    from . import db
+    while True:
+        _wake.wait(30); _wake.clear()
+        with db.tx() as con:
+            rows = con.execute("SELECT * FROM webhook_outbox WHERE sent_utc IS NULL AND next_utc <= strftime('%Y-%m-%dT%H:%M:%SZ','now') ORDER BY id LIMIT 100").fetchall()
+        for r in rows:   # in order; stop at the first failure so events never overtake each other
+            ts = str(int(time.time()))
+            h = {"Content-Type": "application/json", "X-Event": r["event"], "X-Event-Id": str(r["id"]), "X-Timestamp": ts}
+            if config.WEBHOOK_SECRET:
+                h["X-Signature"] = hmac.new(config.WEBHOOK_SECRET.encode(), ts.encode() + b"." + r["body"], hashlib.sha256).hexdigest()
+            try:
+                urllib.request.urlopen(urllib.request.Request(config.WEBHOOK_URL, data=r["body"], headers=h), timeout=30)
+                with db.tx() as con:
+                    con.execute("UPDATE webhook_outbox SET sent_utc=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (r["id"],))
+            except Exception as e:
+                delay = min(3600, 30 * 2 ** r["tries"])
+                with db.tx() as con:
+                    con.execute("""UPDATE webhook_outbox SET tries=tries+1, last_error=?,
+                                   next_utc=strftime('%Y-%m-%dT%H:%M:%SZ','now', ?) WHERE id=?""", (str(e)[:200], f"+{delay} seconds", r["id"]))
+                break
```
INTEGRATION.md then needs to change:
- The signature becomes HMAC of `X-Timestamp + "." + body`.
- eNetra should de-duplicate on `X-Event-Id` and reject old timestamps.
- `since` should be fed the `generated_utc` of the previous poll.

---

## High

### H1. Duplicate reports on retry. The duplicate is flagged "photo reused", and the duplicate is what gets accepted.
`app/server.py:384-410, 474`, `app/static/field.html:29-36, 37, 182`

**What goes wrong**
- The form has no idempotency key. These all resend the same report:
  - a lost response (a timeout, or signal dropping after the server committed);
  - two `flush()` calls at once (`send()` and the `online` event, or the "Send now" button);
  - a 500 raised after the commit (see H5: the NaN response).
- The second copy's photos match the first copy's sha256, so it gets `photo_reused`. Its grade drops to weak. Accept then binds to the latest report, which is the duplicate (H2).
- The honest guard ends up looking like a cheat, and stats count the visit twice in `reports`.

**Reproduced**
- `tests/t_reports.py` (`out_reports.txt`):
  ```
  [R1 same report twice] first=(5, 'strong', ['not_auto_reached']) | retry=(6, 'weak', ['photo_reused', 'not_auto_reached']) | reports_stored=2
  [R1b concurrent duplicate] results=[(7, 'strong', [...]), (8, 'weak', ['photo_reused', 'not_auto_reached'])]
  ```
- `tests/field_queue_test.js`:
  ```
  [J3 concurrent flush] POSTs_of_one_report=2
  [J4 lost response] POSTs_of_one_report=2 (server keeps both; no idempotency key in the form)
  ```

**Patch:** the client side is in C1, the server side is below. The same `client_ref` key goes in the v1 report JSON.
```diff
--- a/app/db.py
+++ b/app/db.py
@@ MIGRATIONS
+    "ALTER TABLE reports ADD COLUMN client_ref TEXT",
+    "CREATE UNIQUE INDEX IF NOT EXISTS rep_client_ref ON reports(staff_id, client_ref) WHERE client_ref IS NOT NULL",
--- a/app/server.py
+++ b/app/server.py
@@ -395,2 +395,3 @@ async def submit_report(...
                         people_met: Optional[str] = Form(None), enforcement: Optional[str] = Form(None),
+                        client_ref: Optional[str] = Form(None),
@@ -409 +410 @@
-            suppression_utc=suppression_utc, people_met=people_met, enforcement=enforcement), raw, json.loads(photo_meta or "[]"))
+            suppression_utc=suppression_utc, people_met=people_met, enforcement=enforcement, client_ref=client_ref), raw, json.loads(photo_meta or "[]"))
@@ -443,2 +444,9 @@ def record_report(con, inc, staff_id, f, photos, meta):
     Shared by the built-in field page and the /api/v1 integration (eNetra app)."""
+    if f.get("client_ref"):   # a resend of a report already stored: answer as before, store nothing
+        old = con.execute("SELECT * FROM reports WHERE staff_id=? AND client_ref=?", (staff_id, f["client_ref"])).fetchone()
+        if old:
+            return {"report_id": old["id"], "evidence": old["evidence"], "flags": json.loads(old["flags"] or "[]"),
+                    "distance_km": old["distance_km"], "recheck": bool(old["recheck"]), "fire_id": old["fire_id"],
+                    "linked_alerts": json.loads(old["linked_alerts"]) if old["linked_alerts"] else None,
+                    "inspection": old["inspection"], "inspection_spread_m": None, "duplicate": True}
@@ -525,3 +533,3 @@
-    con.execute("""UPDATE reports SET evidence=?, flags=?, device_id=?, first_known_by=?, fire_out_utc=?, recheck=?, burn_age=?,
+    con.execute("""UPDATE reports SET client_ref=?, evidence=?, flags=?, device_id=?, first_known_by=?, fire_out_utc=?, recheck=?, burn_age=?,
@@
-                (grade, json.dumps(flags), ...
+                (f.get("client_ref"), grade, json.dumps(flags), ...
```
`record_chance` has to check `client_ref` before `pilot.add_chance`, or a retried chance find creates a second incident.

### H2. Review: accept binds to whatever report is newest. No status check. Two reviewers race.
`app/server.py:561-580`, `app/api_v1.py:234-255`, `app/static/control.html:266-270`

**What goes wrong**
- `review()` takes the latest report id at the moment Accept is pressed, not the report the officer read.
- It never checks the alert's status:
  - a visit that was sent back, with no new visit since, can be accepted;
  - an accepted alert can be sent back from a stale page;
  - two officers acting at once both succeed, and the last write wins.
- An officer can accept their own report, including one with proof `none` (V4). The same holds for v1 when the reviewer and the reporter share an external id (W8).

**Reproduced:** `tests/t_review.py` (`out_review.txt`) and `tests/t_webhook_v1.py`
```
[V1 accept after a newer report] reviewer_saw=[22] | accepted_report=23 | report_B=23 | B_evidence=none | outcome={'status': 'verified', 'outcome': 'no_fire'}
[V2 accept after send-back, no new visit] status=200 | now={'status': 'verified'}
[V2b send back an accepted alert (stale page)] status=200 | now={'status': 'revisit', 'due_utc': '2026-04-16T12:30:00Z'}
[V3 accept + send back at once] codes=[200, 200] | reviews=['revisit', 'accept'] | final={'status': 'verified'}
[V4 ranger accepts own report] report=26 | evidence=none | accept_status=200 | final={'status': 'verified', 'outcome': 'no_fire'}
[W8 v1 self-approval] status=200 | final=verified
```
**Patch** (the same change applies to `v1_review`):
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -556,3 +556,4 @@
 class Review(BaseModel):
     decision: str            # accept | revisit
     note: Optional[str] = None
+    report_id: Optional[int] = None   # the report the reviewer looked at; required by the control room
@@ -570,11 +571,19 @@
         last = con.execute("SELECT id FROM reports WHERE incident_id=? ORDER BY id DESC LIMIT 1", (iid,)).fetchone()
         if body.decision == "accept" and not last:
             raise HTTPException(400, "no field report to accept")
+        if inc["status"] != "visited":
+            raise HTTPException(409, f"this alert is '{inc['status']}', not waiting for a check; reload the page")
+        if body.report_id is not None and last and body.report_id != last["id"]:
+            raise HTTPException(409, "a newer field report came in; reload before deciding")
+        if last and con.execute("SELECT 1 FROM reports WHERE id=? AND staff_id=?", (last["id"], me["id"])).fetchone():
+            raise HTTPException(403, "you cannot check your own report")
+        new = "verified" if body.decision == "accept" else "revisit"
+        due = inc["due_utc"] if new == "verified" else firms.iso(now() + timedelta(hours=config.VISIT_DUE_HOURS))
+        if con.execute("UPDATE incidents SET status=?, due_utc=? WHERE id=? AND status='visited'", (new, due, iid)).rowcount != 1:
+            raise HTTPException(409, "someone else checked this alert first; reload")
         con.execute("INSERT INTO reviews(incident_id,report_id,reviewer_id,decision,note) VALUES (?,?,?,?,?)",
                     (iid, last["id"] if last else None, me["id"], body.decision, body.note))
-        if body.decision == "accept":
-            con.execute("UPDATE incidents SET status='verified' WHERE id=?", (iid,))
-        else:
-            due = firms.iso(now() + timedelta(hours=config.VISIT_DUE_HOURS))
-            con.execute("UPDATE incidents SET status='revisit', due_utc=? WHERE id=?", (due, iid))
--- a/app/static/control.html
+++ b/app/static/control.html
@@ -267,2 +267,3 @@ async function rev(id, decision) {
-  await api(`/api/incidents/${id}/review`, {method: 'POST', headers: {'content-type': 'application/json'},
-    body: JSON.stringify({decision, note: document.getElementById('rv-note').value})});
+  const i = await api('/api/incidents/' + id), last = i.reports[i.reports.length - 1];
+  await api(`/api/incidents/${id}/review`, {method: 'POST', headers: {'content-type': 'application/json'},
+    body: JSON.stringify({decision, note: document.getElementById('rv-note').value, report_id: OPENED_REPORT[id] ?? last?.id})});
```
`OPENED_REPORT[id]` is the newest report id at the time `openInc` drew the drawer.

### H3. A late report reopens an accepted alert and overwrites the accepted outcome
`app/server.py:533-534`

**What goes wrong**
- Any report on a `verified` alert sets the status back to `visited` and replaces `incidents.outcome`.
- Examples: a duplicate (H1), a second guard of a junction beat, or a stale queued report.
- The accepted ground truth changes, for example from burnt_out to no_fire. The CSV's "latest report" row changes with it.

**Reproduced:** `tests/t_reports.py`
```
[R7 report after accept] after_accept={'status': 'verified', 'outcome': 'burnt_out'} | after_late_report={'status': 'visited', 'outcome': 'no_fire'}
```
**Patch:**
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -533,2 +533,6 @@
-    con.execute("""UPDATE incidents SET status='visited', outcome=?, first_report_utc=coalesce(first_report_utc, ?)
-                   WHERE id=?""", (f["outcome"], ts, iid))
+    if inc["status"] == "verified":   # keep the accepted result; the officer sees the extra report and can reopen it
+        flags.append("filed_after_accept")
+        con.execute("UPDATE reports SET flags=? WHERE id=?", (json.dumps(flags), rid))
+    else:
+        con.execute("""UPDATE incidents SET status='visited', outcome=?, first_report_utc=coalesce(first_report_utc, ?)
+                       WHERE id=?""", (f["outcome"], ts, iid))
```

### H4. "Reached" trusts the phone's timestamp: an alert is reached before it existed, or in 2099
`app/server.py:349-360`

**What goes wrong**
- `ts = p.get("utc")` comes straight from the client and is never checked against the alert's time.
- Each position is tested against every alert that is open now, whenever the position was taken. So these all mark a new alert "reached" at a time before its first satellite point:
  - old points from a phone's offline queue (up to 2,000 kept);
  - a phone clock a day behind;
  - a crafted ping.
- A future time is accepted too.
- `reached` feeds proof (`not_auto_reached`), hours-to-reach in `/api/v1/beats/summary`, and pilot inspection.

**Reproduced:** `tests/t_positions.py` (`out_positions.txt`)
```
[P1 position from before the alert] reached=True | first_seen_utc=2026-04-12T19:41:13Z | arrived_utc=2026-03-01T00:00:00Z
[P1b position from the future] reached=True | arrived={'arrived_utc': '2099-01-01T00:00:00Z'}
```
**Patch** (covers H6 as well):
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -343,22 +343,33 @@
 def record_positions(con, staff_id, where, args, positions):
     reached = []
     open_inc = con.execute(f"""SELECT i.* FROM incidents i WHERE {where} AND i.status IN ('new','revisit')
                                AND i.arrived_utc IS NULL""", args).fetchall()
     places = {r["id"]: pilot.Place.of(con, r) for r in open_inc}   # fire points, or the predicted cell
-    for p in positions[:500]:
-        ts = p.get("utc") or firms.iso(now())
+    since = {r["id"]: (r["due_from_utc"] if r["kind"] == "predicted" else r["first_seen_utc"]) for r in open_inc}
+    t_now, stored = now(), []
+    for p in positions:
+        try:
+            t = firms.parse_utc(p["utc"]) if p.get("utc") else t_now
+        except ValueError:
+            continue                                   # skip one bad fix, never fail the batch (H6)
+        if t > t_now + timedelta(minutes=10) or not (-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180):
+            continue
+        ts = firms.iso(t); stored.append(ts)
         con.execute("INSERT INTO positions(staff_id,device_id,utc,lat,lon,acc_m) VALUES (?,?,?,?,?,?)",
                     (staff_id, p.get("device_id"), ts, p["lat"], p["lon"], p.get("acc_m")))
-        if p.get("acc_m") is not None and p["acc_m"] > 100:
+        if p.get("acc_m") is None or p["acc_m"] > 100:
             continue   # too rough to count as reaching the spot
         if p.get("mock_location") or p.get("acc_m") == 0:
             continue   # faked or fake-looking position
         for iid, pl in places.items():
-            if iid not in reached and pl.reached(p["lat"], p["lon"]):
+            if iid not in reached and ts >= since[iid] and pl.reached(p["lat"], p["lon"]):
                 con.execute("UPDATE incidents SET arrived_utc=?, arrived_by=? WHERE id=? AND arrived_utc IS NULL",
                             (ts, staff_id, iid))
                 reached.append(iid)
-    ts_ = [p.get("utc") or firms.iso(now()) for p in positions[:500]]
-    if ts_:   # positions from a phone's offline queue can change a visit's entry / exit time
-        pilot.refresh_sites(con, staff_id, min(ts_), max(ts_))
+    if stored:   # positions from a phone's offline queue can change a visit's entry / exit time
+        pilot.refresh_sites(con, staff_id, min(stored), max(stored))
     return reached
```

### H5. NaN or 0/0 coordinates turn a photo with no location into "strong" proof
`app/evidence.py:16-19, 27-29, 64-71`, `app/server.py:473, 491`

**What goes wrong**
- `float('nan')` passes every check, because `nan > 1.0` is False:
  - `km is None` is False, so there is no `no_location` flag;
  - `km > photo_km` is False, so there is no `far_from_fire` flag.
- There are two ways in:
  - `photo_meta` with `"dev_lat": NaN` (`json.loads` accepts NaN), or the form field `device_lat=nan`;
  - an EXIF GPS block with zero-denominator rationals. Some phones write 0/0 when they have no fix. `IFDRational(0,0)` becomes NaN.
- Either way the photo grades `strong`, while a photo with no position at all grades `none`. SQLite stores NaN as NULL, so the officer sees "no location" next to "strong".
- A NaN `device_lat` also makes the response 500 after the report is committed (JSON cannot carry NaN). The phone then retries and creates a duplicate (H1).

**Reproduced:** `tests/t_reports.py` (`out_reports2.txt`)
```
[R5a NaN photo position only] status=200 | body={"report_id":11,"evidence":"strong","flags":["not_auto_reached"],"distance_km":null,...}
[R5 control: no position at all] evidence=none | flags=['no_location', 'not_auto_reached']
[R5b EXIF GPS 0/0 and no phone fix] evidence=strong | flags=['not_auto_reached'] | stored=[{'exif_lat': None, 'distance_km': None, 'flags': '[]'}]
[R5 NaN phone + photo position] status=500 | body=Internal Server Error | stored=[{'id': 10, 'evidence': 'weak', ...}]
```
**Patch:**
```diff
--- a/app/evidence.py
+++ b/app/evidence.py
@@ -7,3 +7,13 @@
-import hashlib, io
+import hashlib, io, math
@@
+def num(x, lo=-180, hi=180):
+    """A finite float in [lo, hi], else None (NaN, inf, text, 0/0 EXIF rationals)."""
+    try:
+        x = float(x)
+    except (TypeError, ValueError, ZeroDivisionError):
+        return None
+    return x if math.isfinite(x) and lo <= x <= hi else None
+
 def _deg(v, ref):
     d, m, s = (float(x) for x in v)
     x = d + m / 60 + s / 3600
-    return -x if ref in ("S", "W") else x
+    return num(-x if ref in ("S", "W") else x)
@@ -24,10 +34,14 @@ def read_exif(img):
     out = {}
     try:
         ex = img.getexif()
         gps = ex.get_ifd(GPS_IFD)
         if gps and 2 in gps and 4 in gps:
-            out["lat"] = _deg(gps[2], gps.get(1, "N"))
-            out["lon"] = _deg(gps[4], gps.get(3, "E"))
+            lat, lon = _deg(gps[2], gps.get(1, "N")), _deg(gps[4], gps.get(3, "E"))
+            if lat is not None and lon is not None and abs(lat) <= 90 and not (lat == 0 and lon == 0):
+                out["lat"], out["lon"] = lat, lon
+    except Exception:
+        pass
+    try:   # time on its own, so a bad GPS block does not also drop the time
         t = ex.get_ifd(EXIF_IFD).get(36867) or ex.get(306)
@@ -62,5 +76,7 @@ def check_photo(meta, ex, place, first_seen, seen_hash):
     flags = []
+    meta = dict(meta, dev_lat=num(meta.get("dev_lat"), -90, 90), dev_lon=num(meta.get("dev_lon")))
     lat, lon = ex.get("lat"), ex.get("lon")
--- a/app/server.py
+++ b/app/server.py
@@ -472,2 +472,4 @@
     ts = firms.iso(now())
+    f["device_lat"], f["device_lon"] = evidence.num(f.get("device_lat"), -90, 90), evidence.num(f.get("device_lon"))
+    f["device_acc_m"] = evidence.num(f.get("device_acc_m"), 0, 1e6)
     report_km = place.km(f.get("device_lat"), f.get("device_lon"))
```

### H6. Positions are lost: the server keeps 500 per batch and the phone clears everything. One bad fix blocks the whole queue.
`app/server.py:348, 361`, `app/static/field.html:14-22`

**What goes wrong**
- `field.html` queues up to 2,000 positions (about 33 h offline) and POSTs them all at once.
- The server stores only `positions[:500]`, the oldest 500, and answers 200. The phone then clears its whole queue.
- The newest points are lost, and those are the arrival at the fire. So "reached", the route, and pilot site entry and exit go with them.
- A fix taken while the POST is in flight is also wiped by `setItem('fs-pos','[]')`.
- One entry with an unreadable `utc` makes the whole batch 500. The client keeps re-sending the same batch, so nothing more is stored for that phone (via v1 or a buggy client).
- `List[Position]` has no length limit: 100k positions (7 MB) were parsed and accepted with 200.

**Reproduced:** `tests/t_positions.py` and `tests/field_queue_test.js`
```
[P3 600 queued positions] status=200 | stored=500 | reached=False     (the 600th fix was at the fire)
[P2 batch with one odd time] status=500 | stored=0
[P6 100k positions] status=200 | seconds=2.5 | body_mb=7.3
[J5 fix queued during the POST] queue_after=[] (the 10:01 fix was never sent)
```
**Patch** (server side as in H4: no slice, skip bad fixes; and cap the request):
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -335,2 +335,4 @@ def post_positions(body: List[Position], me=Depends(current)):
+    if len(body) > 1000:
+        raise HTTPException(413, "send at most 1000 positions per request")
     where, args = scope_sql(me)
--- a/app/static/field.html
+++ b/app/static/field.html
@@ -20,3 +20,6 @@
-async function sendPos() { const q = posQ(); if (!q.length) return;
-  try { const r = await fetch('/api/positions', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(q)});
-    if (r.ok) { localStorage.setItem('fs-pos', '[]'); if ((await r.json()).reached.length) list(); } } catch (e) {} }
+async function sendPos() { if (sendPos.busy) return; sendPos.busy = true;
+  try { for (let q = posQ(); q.length; q = posQ()) { const batch = q.slice(0, 500);
+      const r = await fetch('/api/positions', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(batch)});
+      if (!r.ok) break;
+      localStorage.setItem('fs-pos', JSON.stringify(posQ().slice(batch.length)));   // drop only what was sent
+      if ((await r.json()).reached.length) list(); } } catch (e) {} finally { sendPos.busy = false; } }
```

### H7. Photos the server cannot decode (HEIC, a cut-off upload, any non-image) give 500. The report can never be delivered, and files are left behind.
`app/evidence.py:40-53`, `app/server.py:481-496`

**What goes wrong**
- `Image.open` fails on HEIC (iPhone's default format) and on non-images. `exif_transpose(...).convert()` fails on a truncated JPEG.
- Both raise an unhandled exception, so the answer is 500.
- The phone keeps the report and re-sends it on every flush, forever. The banner blames the signal.
- Earlier photos of the same report, and the original of the failing one, are already written to disk. They stay there as orphans after the rollback.

**Reproduced:** `tests/t_reports.py` and `field_queue_test.js`
```
[R3 HEIC photo] status=500 | body=Internal Server Error | reports=0 | orphan_files=['r9_0.jpg', 'r9_0_t.jpg']
[R3b truncated JPEG] status=500 | body=Internal Server Error | files=['r9_0.jpg']
[R3c text file as photo] status=500 | body=Internal Server Error
[J2 500 on a queued report] sends=3 | still_queued=1 | banner="1 report saved on this phone, will send when there is signal. Send now"
```
**Patch:** decode everything first, write files only after all photos pass, and answer with a clear 4xx. With C1 applied, the guard sees why.
```diff
--- a/app/evidence.py
+++ b/app/evidence.py
@@ -9,2 +9,8 @@
 from PIL import Image, ImageOps
+Image.MAX_IMAGE_PIXELS = 60_000_000   # phone photos are <= 50 MP; refuses decompression bombs (M1)
+try:
+    from pillow_heif import register_heif_opener   # iPhone HEIC
+    register_heif_opener()
+except ImportError:
+    pass
@@ -40,14 +46,22 @@
-def save_photo(raw, dest_dir, stem):
-    """Save original + 480 px thumbnail; return (path, thumb, sha256, exif dict)."""
+class BadPhoto(ValueError):
+    pass
+
+def load_photo(raw):
+    """Decode once, before anything is stored: (img, thumbnail, sha256, exif) or BadPhoto."""
     sha = hashlib.sha256(raw).hexdigest()
-    img = Image.open(io.BytesIO(raw))
-    ex = read_exif(img)
+    try:
+        img = Image.open(io.BytesIO(raw))
+        ex = read_exif(img)
+        img.draft("RGB", (960, 960))                     # JPEG: decode at reduced size
+        th = ImageOps.exif_transpose(img).convert("RGB")
+        th.thumbnail((480, 480))
+    except Exception as e:
+        raise BadPhoto(f"photo could not be read ({type(e).__name__}); send JPEG or PNG") from e
+    return img, th, sha, ex
+
+def save_photo(loaded, raw, dest_dir, stem):
+    img, th, sha, ex = loaded
     ext = (img.format or "jpg").lower().replace("jpeg", "jpg")
     dest_dir.mkdir(parents=True, exist_ok=True)
     path = dest_dir / f"{stem}.{ext}"
     path.write_bytes(raw)
-    th = ImageOps.exif_transpose(img).convert("RGB")
-    th.thumbnail((480, 480))
     thumb = dest_dir / f"{stem}_t.jpg"
--- a/app/server.py
+++ b/app/server.py
@@ -466,2 +466,7 @@ def record_report(con, inc, staff_id, f, photos, meta):
+    try:
+        loaded = [evidence.load_photo(raw) for raw in photos]   # every photo decodes before anything is written
+    except evidence.BadPhoto as e:
+        raise HTTPException(415, str(e))
     iid = inc["id"]
@@ -485 +490 @@
-        path, thumb, sha, ex = evidence.save_photo(raw, config.PHOTO_DIR / str(iid), f"r{rid}_{k}")
+        path, thumb, sha, ex = evidence.save_photo(loaded[k], raw, config.PHOTO_DIR / str(iid), f"r{rid}_{k}")
```
Files can still be orphaned if a later step raises. A cleanup of `photos/` rows with no DB match fixes that.

### H8. A guard never sees an alert sent back for a revisit once its last satellite point is over 14 days old
`app/static/field.html:59`, `app/server.py:221-223`

**What goes wrong**
- The phone asks `/api/incidents?days=14`, and the server filters on `last_seen_utc >= now - days`.
- An alert sent back after a slow review is status `revisit` with a fresh `due_utc`, but it drops off the guard's "To visit" list and shows as overdue in the control room only.
- The control room's default 7-day view has the same gap for open alerts.

**Reproduced:** `tests/t_guard_list.py` on the real-clock DB (one alert aged by 15 days) (`out_guard_list.txt`)
```
[G1 sent back, last point 15 days old] review=200 | status=revisit | due_utc=2026-10-21T16:11:47Z | in_guard_list_days14=False | guard_can_open_detail=200
```
**Patch:**
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -221,4 +221,5 @@ def incidents(days: float = 7, status: Optional[str] = None, me=Depends(current)):
     q = f"""SELECT i.*, (SELECT max(recheck) FROM reports WHERE incident_id=i.id) AS recheck
-            FROM incidents i WHERE {where} AND i.last_seen_utc >= ? AND i.first_seen_utc <= ?"""
-    args += [firms.iso(now() - timedelta(days=days)), firms.iso(now())]   # replays: nothing after the replay clock
+            FROM incidents i WHERE {where} AND i.first_seen_utc <= ?
+            AND (i.last_seen_utc >= ? OR i.status IN ('new','revisit'))"""   # open work is always listed
+    args += [firms.iso(now()), firms.iso(now() - timedelta(days=days))]   # replays: nothing after the replay clock
```

### H9. Migration errors are all swallowed, including "database is locked". The server then starts with missing columns.
`app/db.py:436-440`

**What goes wrong**
- Every `sqlite3.OperationalError` is treated as "column already there".
- Suppose another process holds a write lock while the server starts: a backup, `import_archive.py`, `add_staff.py`, or a second server.
- Each new `ALTER` waits 30 s, fails with `database is locked`, and is skipped. If the lock clears before `ANALYZE`, `init()` reports success.
- Every later report write then fails with `no such column`. The phones keep their reports, but nothing gets in until someone restarts the server.
- The base-schema upgrade itself works (M1 in `out_migrate.txt`).

**Reproduced:** `tests/t_migrate3.py`
- Setup: a previous-release DB with `people_met` and `enforcement` dropped, and a write lock held for 75 s.
- Output (`out_migrate3.txt`):
  ```
  [M3b previous-release DB, lock held 75 s (e.g. a backup or import script)] seconds 75 | stdout: init ok | stderr tail:
     reports.people_met present: False | enforcement present: False
     later report write fails: no such column: people_met
  ```
- With a longer lock it crashes at `ANALYZE` instead (`out_migrate2.txt`).

**Patch:**
```diff
--- a/app/db.py
+++ b/app/db.py
@@ -436,5 +436,8 @@ def init():
         for m in MIGRATIONS:
             try:
                 con.execute(m)
-            except sqlite3.OperationalError:
-                pass   # column already there
+            except sqlite3.OperationalError as e:
+                if "duplicate column name" in str(e) or "already exists" in str(e):
+                    continue   # column / index already there
+                raise          # locked, disk full, bad SQL: do not start half-migrated
```
A `PRAGMA user_version` per migration would be better still, so each one runs exactly once.

---

## Medium

### M1. Memory exhaustion from uploads and payloads
`app/server.py:397-399, 424, 459-483`, `app/api_v1.py:182`, `app/evidence.py:43-50`

**What goes wrong**
- Every photo is read whole into RAM (`await up.read()`) before the count (6) and size (15 MB) checks.
- A 164 KB PNG that decodes to 144 MP is accepted and fully decoded. PIL only refuses images above 179 MP.
- Six of either per request, plus a few parallel requests, will take the server down. Any guard login (C2) or the service key is enough.

**Reproduced:** `tests/t_bigupload.py` and `tests/t_bomb.py`
```
[U1 300 MB upload] status=400 | body={"detail":"photo over 15 MB"} | seconds=2.6 | rss_before_mb=794 | rss_peak_mb=1094
[U2 144 MP PNG] upload_kb=164 | status=200 | evidence=none | seconds=1.3 | rss_before_mb=794 | rss_peak_mb=1597
```
**Patch** (plus `MAX_IMAGE_PIXELS` and `draft` from H7, and the 1000-position cap from H6):
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -383,0 +384,11 @@
+MAX_PHOTO = 15 * 1024 * 1024
+
+async def read_photos(photos):
+    if len(photos) > 6:
+        raise HTTPException(400, "up to 6 photos")
+    out = []
+    for up in photos:   # Starlette has spooled the file to disk; read at most the limit + 1 byte into memory
+        b = await up.read(MAX_PHOTO + 1)
+        if len(b) > MAX_PHOTO:
+            raise HTTPException(413, "photo over 15 MB")
+        out.append(b)
+    return out
@@ -397,3 +408 @@ async def submit_report(...
-    raw = []
-    for up in photos:
-        raw.append(await up.read())
+    raw = await read_photos(photos)
```
Use the same helper in `chance_find`, `v1_report` and `v1_chance`. Also put a body-size limit in front of the app: uvicorn has none, so use the reverse proxy's `client_max_body_size 100m`.

### M2. Blind fire review: a reviewer can change their verdict after seeing the split. Reviewers from another range cannot see the photos.
`app/pilot.py:608-626, 628-661`, `app/server.py:542-553`

**What goes wrong**
- `add_verdict` upserts (`ON CONFLICT ... DO UPDATE`).
- The queue tells a reviewer who has voted "needs third reviewer (split)". That reviewer can re-vote to match the other, and the case closes "2 of 2" with no third reviewer.
- `/api/review/fires` is open to every ranger statewide, but `/api/photos/{id}` keeps range scope. A reviewer from another range sees the case but gets 404 on every photo.
- The case id is the alert id (`S<incident>`), which partly unblinds the case. The reviewer gets 404 on the detail, so the risk is small.

**Reproduced:** `tests/t_review.py`
```
[V5 split then flip] after_2=(None, 'third reviewer (split)') | after_flip=('confirmed_start', '2 of 2 reviewers: fresh ash | changed my mind')
[V5b other-range ranger] sees_case=True | case_id=S27 | photo_status=404 | alert_detail=404
```
**Patch:**
```diff
--- a/app/pilot.py
+++ b/app/pilot.py
@@ -617,2 +617,5 @@ def add_verdict(con, fid, reviewer_id, verdict, reason, now_utc):
     if done:
         raise ValueError("this fire is already decided")
+    if n >= 2 and con.execute("SELECT 1 FROM fire_verdicts WHERE fire_id=? AND reviewer_id=?", (fid, reviewer_id)).fetchone():
+        raise ValueError("verdicts are locked once two reviewers have answered; a third reviewer settles a split")
@@ -657,1 +660,1 @@ def review_queue(con, reviewer_id, scars=None):
-                    "verdicts_in": nv, "needs": "third reviewer (split)" if nv >= 2 else f"{2 - nv} more reviewer(s)",
+                    "verdicts_in": nv, "needs": "your verdict" if not mine else "other reviewers",
--- a/app/server.py
+++ b/app/server.py
@@ -550,3 +550,6 @@ def photo(pid: int, thumb: bool = True, me=Depends(current)):
     with db.tx() as con:
-        if not con.execute(f"SELECT 1 FROM incidents i WHERE i.id=? AND {where}", [p["incident_id"]] + args).fetchone():
+        in_scope = con.execute(f"SELECT 1 FROM incidents i WHERE i.id=? AND {where}", [p["incident_id"]] + args).fetchone()
+        in_review = me["role"] in ("ranger", "admin") and con.execute(
+            "SELECT 1 FROM reports r JOIN fires f ON f.fire_id=r.fire_id WHERE r.id=? AND f.queued=1", (p["report_id"],)).fetchone()
+        if not (in_scope or in_review):
             raise HTTPException(404)
```
Showing an opaque case number instead of `S<alert id>` would finish the blinding.

### M3. The phone clock is trusted for photo time, visit time and positions, though the page knows the server offset
`app/static/field.html:17, 157, 172`, `app/evidence.py:75-81`

**What goes wrong**
- `setClock` computes `CLOCK` (server minus phone), but positions, `dev_utc` and `visited_utc` all use `new Date()`.
- With a phone 2 days slow, an honest photo is flagged `photo_before_alert` (weak).
- A photo time days in the future is never flagged.
- A 2024 photo re-saved without EXIF (new sha256) grades strong, with no camera time or position at all.

**Reproduced:** `tests/t_reports.py` (`out_reports2.txt`) and `field_queue_test.js` (J6)
```
[R6 phone clock -2 days] evidence=weak | flags=['photo_before_alert', 'not_auto_reached']
[R6b photo time 5 days in the future] evidence=strong | flags=['not_auto_reached']
[R6c 2024 photo with EXIF] evidence=weak | flags=['photo_before_alert', 'not_auto_reached']
[R6d same 2024 photo re-saved (EXIF stripped)] evidence=strong | flags=['not_auto_reached']
```
**Patch:**
```diff
--- a/app/static/field.html
+++ b/app/static/field.html
@@ -17 +17 @@
-  const q = posQ(); q.push({lat: p.coords.latitude, lon: p.coords.longitude, acc_m: p.coords.accuracy, utc: new Date().toISOString().replace(/\.\d+Z$/, 'Z'), device_id: DEVICE});
+  const q = posQ(); q.push({lat: p.coords.latitude, lon: p.coords.longitude, acc_m: p.coords.accuracy, utc: new Date(nowMs()).toISOString().replace(/\.\d+Z$/, 'Z'), device_id: DEVICE});
@@ -157 +157 @@
-  SHOTS.push({file: f, dev_lat: HERE?.latitude ?? null, dev_lon: HERE?.longitude ?? null, dev_acc: HERE?.accuracy ?? null, dev_utc: new Date().toISOString()});
+  SHOTS.push({file: f, dev_lat: HERE?.latitude ?? null, dev_lon: HERE?.longitude ?? null, dev_acc: HERE?.accuracy ?? null, dev_utc: new Date(nowMs()).toISOString(), phone_utc: new Date().toISOString()});
--- a/app/server.py
+++ b/app/server.py
@@ -487,2 +487,6 @@
         km, fl, taken = evidence.check_photo(m, ex, place, first_seen, seen)
+        if taken and taken > now() + timedelta(minutes=10):
+            fl.append("photo_time_in_future")
+        if ex.get("lat") is None and ex.get("taken_utc") is None:
+            fl.append("no_camera_data")        # position and time come only from the page
```
Add `photo_time_in_future` to `bad` in `evidence.grade`. Weigh `no_camera_data` against how often browsers strip EXIF before deciding whether it alone makes a photo weak.

### M4. eNetra report JSON is not validated: 500s, or text stored in number columns
`app/api_v1.py:183, 189`, `app/server.py:473, 502-503`, `app/evidence.py:77`

**What goes wrong**
- These all give an unhandled 500:
  - `report` that is not JSON, or is a list;
  - `device_lat` sent as a string;
  - `device_acc_m: "abc"`;
  - `photo_meta` that is not a list of objects;
  - a naive or garbage `dev_utc` (same on the built-in endpoint);
  - garbage `visited_utc`.
- `area_ha: "lots"` and `crew: "many"` are stored as text in REAL and INTEGER columns. The CSV and the stats then carry them.

**Reproduced:** `tests/t_webhook_v1.py` and `tests/t_reports.py`
```
[W6 v1 report not json] status=500 ... [W6 v1 report list] status=500 ... [W6 v1 report lat as text] status=500 ... [W6 v1 report acc as text] status=500
[W6b text in numeric fields] status=200 | stored=[{'area_ha': 'lots', 'crew': 'many'}]
[R4 photo_meta bad json|dict|list of str|naive dev_utc|garbage dev_utc] status=500 (each)
[R4b visited_utc garbage] status=500
```
**Patch:** validate once in `record_report`, so both endpoints get it.
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -443,2 +443,18 @@ def record_report(con, inc, staff_id, f, photos, meta):
+    if not isinstance(f, dict) or not isinstance(meta, list) or not all(isinstance(m, dict) for m in meta):
+        raise HTTPException(400, "report must be a JSON object and photo_meta a list of objects")
+    for k in ("visited_utc", "fire_out_utc", "suppression_utc"):
+        if f.get(k):
+            try:
+                f[k] = firms.iso(firms.parse_utc(f[k]))
+            except (ValueError, TypeError):
+                raise HTTPException(400, f"{k} must be UTC like 2026-04-15T10:00:00Z")
+    for m in meta:
+        if m.get("dev_utc"):
+            try:
+                m["dev_utc"] = firms.iso(firms.parse_utc(m["dev_utc"]))
+            except (ValueError, TypeError):
+                m["dev_utc"] = None            # unreadable phone time: the photo gets no_time
+    f["area_ha"] = evidence.num(f.get("area_ha"), 0, 1e5)
+    f["crew"] = int(f["crew"]) if str(f.get("crew") or "").isdigit() and int(f["crew"]) <= 500 else None
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -182,2 +182,6 @@ async def v1_report(...
     raw = [await p.read() for p in photos]
-    f = json.loads(report)
+    try:
+        f, meta = json.loads(report), json.loads(photo_meta or "[]")
+    except ValueError:
+        raise HTTPException(400, "report and photo_meta must be JSON")
```
`firms.parse_utc` must accept `+00:00` and `Z`, and treat a naive time as UTC. If it does not, wrap it.

### M5. Built-in pages never send webhooks
`app/server.py:334-341, 384-410, 561-580`

**What goes wrong**
- Only `/api/v1/*` calls `webhook.send`. A report from `/field`, a review in the control room, or a "reached" through `/api/positions` is never pushed.
- If staff use the built-in pages at all during a mixed rollout or testing, eNetra misses those changes. Polling misses them too (C3).

**Reproduced:** `tests/t_webhook_v1.py`
```
[W2 field page + control room events] reached_reported_reviewed_in_engine={'status': 'verified', 'arrived_utc': '2026-04-15T12:30:00Z'} | webhooks_sent=[]
```
**Patch:**
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -339,3 +339,7 @@ def post_positions(body: List[Position], me=Depends(current)):
     with db.tx() as con:
-        return {"reached": record_positions(con, me["id"], where, args, [p.dict() for p in body])}
+        reached = record_positions(con, me["id"], where, args, [p.dict() for p in body])
+    _push("alert.reached", reached)
+    return {"reached": reached}
+
+def _push(event, ids):
+    from . import webhook
+    from .api_v1 import alert_json
+    with db.tx() as con:
+        for i in ids:
+            webhook.send(event, alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (i,)).fetchone()))
```
Call `_push("alert.reported", [iid])` after `submit_report` and `chance_find`, and `_push("alert.reviewed", [iid])` after `review`.

### M6. `/api/v1/alerts`: the division and range filters run after LIMIT
`app/api_v1.py:156-159`

**What goes wrong**
- The SQL takes the newest `limit` alerts statewide, then Python drops the ones outside the division.
- A division poll with a normal limit returns fewer alerts than exist, or none.
- `range_name` is also matched without its division, and 41 range names repeat across divisions (see M7).

**Reproduced:** `tests/t_webhook_v1.py`
```
[W5 division filter after limit] division=Sehore_Project | alerts_in_division=2 | returned_with_limit_20=0
```
**Patch:**
```diff
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -152,4 +152,10 @@ def v1_alerts(...
     if beat_uid:
         q += " AND i.id IN (SELECT incident_id FROM incident_beats WHERE beat_uid = ?)"
         args.append(beat_uid)
+    if division or range_name:
+        uids = [p["beat_uid"] for p in BEATS_REF().props
+                if (not division or p.get("division") == division) and (not range_name or p["range"] == range_name)]
+        q += f" AND i.beat_uid IN ({','.join('?' * len(uids)) or 'NULL'})"
+        args += uids
     with db.tx() as con:
         rows = con.execute(q + " ORDER BY i.first_seen_utc DESC LIMIT ?", args + [min(limit, 5000)]).fetchall()
         out = [alert_json(con, r) for r in rows]
-    if division or range_name:
-        out = [a for a in out if (not division or a["division"] == division) and (not range_name or a["range"] == range_name)]
```

### M7. A ranger made with a plain range name sees that range in every division. Unknown beats are accepted.
`app/geo.py:41-46`, `app/server.py:171-178`, `scripts/add_staff.py`

**What goes wrong**
- README's example (`--range Delawari`) and add_staff.py's docstring (`--range Obedullaganj`) use a plain range name.
- `in_range` then matches every division with that name. 41 of 501 MP range names repeat.
- A guard made with a mistyped `beat_uid` is accepted and silently sees nothing.

**Reproduced:** `tests/t_range.py` (`out_range.txt`)
```
[S1 ranger range 'Jamai'] beats=18 | divisions=['Chhindwara_Project', 'West_Chhindwara']
[S2 guard with unknown beat] created=13 | sees=0
```
**Patch** (and the same checks in `scripts/add_staff.py`):
```diff
--- a/app/server.py
+++ b/app/server.py
@@ -174,2 +174,6 @@ def add_staff(body: NewStaff, me=Depends(supervisor)):
         raise HTTPException(403, "admins add staff; role must be guard, ranger or admin")
+    if body.role == "guard" and body.beat_uid not in BEATS.by_uid:
+        raise HTTPException(400, "unknown beat_uid")
+    if body.role == "ranger" and len({BEATS.by_uid[u].get("division") for u in BEATS.in_range(body.range_name)}) != 1:
+        raise HTTPException(400, "range must be 'Division:Range' as in the beat layer")
```

### M8. `reached_utc` and `first_report_utc` never reach eNetra
`app/api_v1.py:69`

**What goes wrong**
- A misplaced comment swallows both keys:
  `"search_m": _search_m(con, r["id"]),   # search ... (half pixel + 100 m) "reached_utc": r["arrived_utc"], "first_report_utc": r["first_report_utc"],`
- INTEGRATION.md documents both fields. eNetra cannot show "reached" or time-to-report from the alert JSON.
- This is rated medium only because `/api/v1/beats/summary` still carries the aggregates. Treat it as part of the C3 data-loss picture.

**Reproduced:** `tests/t_webhook_v1.py`
```
[W1 v1 alert keys] has_reached_utc=False | has_first_report_utc=False | db_arrived=2026-04-15T12:30:00Z
```
**Patch:**
```diff
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -69 +69,2 @@
-        "search_m": _search_m(con, r["id"]),   # search this far around the point, all sides (half pixel + 100 m) "reached_utc": r["arrived_utc"], "first_report_utc": r["first_report_utc"],
+        "search_m": _search_m(con, r["id"]),   # search this far around the point, all sides (half pixel + 100 m)
+        "reached_utc": r["arrived_utc"], "first_report_utc": r["first_report_utc"],
```

### M9. Stored XSS in the control room through a v1 task's `score`
`app/static/control.html:163`, `app/pilot.py:233-237`

**What goes wrong**
- `add_tasks` stores `t.get("score")` as given. SQLite keeps text in a REAL column.
- The drawer renders `' · score ' + i.score` without `esc`.
- Anyone holding the service key (or a leaked key) can run script in an admin's session. The session cookie is HttpOnly, but the script can still call every API as the admin.

**Reproduced:** `tests/t_webhook_v1.py`
```
[W9 task score as HTML] stored_score=<img src=x onerror=alert(document.cookie)> | rendered_by=control.html:163 ' · score ' + i.score
```
Storage and API output are reproduced. That it renders unescaped is read from the code; no browser was run.

**Patch:**
```diff
--- a/app/static/control.html
+++ b/app/static/control.html
@@ -163 +163 @@
-...${i.score != null ? ' · score ' + i.score : ''}...
+...${i.score != null ? ' · score ' + esc(i.score) : ''}...
--- a/app/pilot.py
+++ b/app/pilot.py
@@ -237 +237 @@
-                 f"{grid}:{cid}", json.dumps(g), arm, ver["model_hash"], json.dumps(ver, sort_keys=True), t.get("score")))
+                 f"{grid}:{cid}", json.dumps(g), arm, ver["model_hash"], json.dumps(ver, sort_keys=True),
+                 None if t.get("score") is None else float(t["score"])))
```

### M10. "Reached" also counts fixes with no accuracy, and v1 pings with no beat list can reach any alert in MP
`app/server.py:352`, `app/api_v1.py:215-219`

**What goes wrong**
- A position without `acc_m` counts as reaching the spot. Only `acc_m > 100` is rejected.
- `/api/v1/positions` with an empty `beat_uids` matches every open alert in the state. One eNetra user's ping can mark another beat's alert reached.

**Reproduced:** `tests/t_positions.py`
```
[P4 no acc_m] reached=True
[P7 v1 positions, no beat_uids] reached=True
```
**Patch:**
- For the accuracy, see H4 (`acc_m is None` is treated as too rough).
- For v1, default `beat_uids` to the staff record's `beat_uid`, and refuse an empty list:
```diff
--- a/app/api_v1.py
+++ b/app/api_v1.py
@@ -215,5 +215,7 @@ def v1_positions(body: V1Positions):
-        if body.beat_uids:
-            where = ...
-        else:
-            where, args = "1=1", []
+        uids = body.beat_uids or [x for x in [con.execute("SELECT beat_uid FROM staff WHERE id=?", (sid,)).fetchone()[0]] if x]
+        if not uids:
+            raise HTTPException(400, "beat_uids is required (the beats this person covers)")
+        where = f"i.id IN (SELECT incident_id FROM incident_beats WHERE beat_uid IN ({','.join('?' * len(uids))}))"
+        args = list(uids)
```

---

## Low

| # | Where | What | Reproduced (test: output) | Proposed fix |
|---|---|---|---|---|
| L1 | `server.py:299-307` | A guard's `/api/detections.geojson` returns every point in MP, including incident ids of other beats. `beats.geojson?bbox=` returns any area, and a bad bbox gives 500. | `t_auth.py`: `A3 guard detections total=410, with_other_beats_incident=215`; `A3b bad bbox status=500` | For guards, filter to their beat's bbox plus a margin. Parse bbox in a try and answer 400. |
| L2 | `api_v1.py:26-32` | eNetra reporters and reviewers are created as role `guard`, `active=1`. They appear in the sign-in list (they cannot sign in: pin_hash `!`). | `t_webhook_v1.py`: `W7 names=[..., 'enetra-x', 'ro-1', 'w1', 'w3', 'w6', ...]` | Create them with `active=0` or role `external`, and exclude them from `/api/staff`. |
| L3 | `server.py:635-659` | CSV formula injection: `beats_touched` (free text) is exported as is. `=HYPERLINK(...)` opens as a formula in Excel. | `t_misc.py`: `X4 CSV cell starting with = found=True` | Prefix cells starting with `= + - @` with `'` in `export()`. |
| L4 | `server.py:143-144`, `db.py` sessions | Expired sessions are never deleted. The cookie has no `Secure` flag (HTTPS hosting is planned). | `t_misc.py`: `X3 expired_rows=1`; `t_auth.py` A8 cookie: `HttpOnly; SameSite=lax` only | Run `DELETE FROM sessions WHERE expires_utc < now` at login. Use `secure=True` when served over HTTPS (env switch). |
| L5 | `pilot.py:240-241` | Task import errors return server paths (`.../ratapani/grid_500m.geojson`). | `t_misc.py`: `X5 errors=[{'cell_id': 123456789, 'error': 'ratapani cell 123456789 not in /mnt/project-files/ratapani/grid_500m.geojson'}]` | Say "unknown cell_id for grid ratapani" without the path. |
| L6 | `server.py:441-478` | Negative area and crew, accuracy -1, and `visited_utc` in 2099 are accepted. Notes up to 1 MB per field are accepted (Starlette caps at 1 MB: `R8b 3 MB notes -> 400`). | `t_reports.py`: `R8 stored=[{'area_ha': -50.0, 'crew': -3, 'n': 900000, 'visited_utc': '2099-01-01T00:00:00Z', 'device_acc_m': -1.0}]` | Range checks as in M4. Cap notes at about 4 kB. Reject `visited_utc` later than now plus 10 min. |
| L7 | `server.py:508-510` | `phone_used_by_other_staff` relies on a client-made device id (localStorage UUID) and looks only at reports, not positions. Clearing site data evades it. | Read only (shown working in flow_test: `admin on guard phone ['no_photo', 'phone_used_by_other_staff']`) | Document it as advisory. A native eNetra app should send a hardware-backed id. |
| L8 | `evidence.py:82-83` | `photo_reused` is exact sha256 only. A re-save or crop defeats it (R6d gave a new hash and no flag). | `t_reports.py`: `R6d ... evidence=strong` | Add a perceptual hash (dHash on the thumbnail) and flag near-duplicates within, say, 90 days. |
| L9 | `scripts/pilot_test.py:147`, `INTEGRATION.md:133` | `pilot_test.py` fails when run after `flow_test.py` on the same DB, and passes alone. INTEGRATION.md says api_v1_test checks webhook delivery; it does not. | `pilot_test.out` (AssertionError line 147) vs `pilot_test_fresh.out` ("ALL PILOT CHECKS PASSED") | Have each test make its own DB (`demo_replay.py` into a temp dir). Add a webhook receiver to `api_v1_test.py` or fix the doc. |
| L10 | Integration | No CORS headers (preflight gives 405). That is right for server-to-server use, but INTEGRATION.md should say the service key must never be used from eNetra's browser code. | `t_auth.py`: `A9 CORS preflight status=405 acao=None` | Add one line to INTEGRATION.md. If a browser client is ever needed, use per-user tokens, not the service key. |

## Not reproduced (read only)

- **Same phone, two people.** Guard A queues a report offline, and guard B signs in on the same phone. `flush()` sends A's report with B's cookie, so it is filed as B's, or returns 404 and is deleted (C1). The outbox is not keyed by user, and sign-out does not warn about unsent reports. Fix: store `ME.id` with each item, and only flush items whose owner matches the current session.
- **Webhook ordering.** Each event gets its own thread with a 30 s timeout, so a slow eNetra can see `alert.reviewed` before `alert.reported`. Under bursts, threads are unbounded. The C3 patch delivers events in order from one worker.
- **Concurrent verdicts.** `add_verdict` reads the count and then inserts, in a deferred transaction. Two reviewers at the same instant could both be counted as second. Low, and fixed by `BEGIN IMMEDIATE` in `db.tx` for writes.

## Fixes applied (20 Oct 2026)

Checked against servers on ports 8030-8049 with fresh demo databases. The audit's reproductions were repointed to the fixed server and gathered in `/tmp/claude-0/fieldfix/ftests/verify_field.py` (69 of 69 checks pass; output in `/tmp/claude-0/fieldfix/verify_field.out`). `field_queue_test.js` is the Node harness for `field.html`. `scripts/run_tests.py` runs flow_test, api_v1_test, pilot_test and the new webhook_test, each on its own fresh database.

| Finding | Status | How checked |
|---|---|---|
| C1 phone deletes rejected report | fixed: refused items stay on the phone with the reason and a Discard button; 401, 5xx or no network keep the item for later; "Report sent" only on 2xx; items carry `owner` and `client_ref` | field_queue_test.js J1, J1b, J3, J4 |
| C2 PIN brute force, public staff list | fixed: lockout per account (5 fails) and per IP (20), 30 s doubling to 1 h, 429 while locked; empty or non 4-12 digit PIN refused; `/api/staff` admin only; sign-in by staff number | verify_field C2 rows, per-account and per-IP lockout |
| C3 eNetra loses status changes | fixed: durable `webhook_outbox`, one in-order worker with backoff, `X-Event-Id`, `X-Timestamp`, `X-Signature-Ts`; `updated_utc` (trigger) drives `since` | webhook_test.py (503 outage then redelivery, since poll, order, both signatures); verify_field C3/W3 |
| H1 duplicate reports on retry | fixed: `client_ref` unique per staff, a resend returns the stored answer with `duplicate: true` and sends no second event | verify_field H1 (serial, concurrent, chance find) |
| H2 review binds to newest report, races | fixed: review needs status `visited`, takes `report_id` (stale gives 409), own report 403, conditional UPDATE so a lost race gives 409 | verify_field H2/V1-V4, W8 |
| H3 late report reopens accepted alert | fixed: flagged `filed_after_accept`, status and outcome left alone | verify_field H3 |
| H4 reached trusts phone time | fixed: fixes more than 10 min in the future refused, a fix before the alert never reaches it | verify_field H4/P1, P1b |
| H5 NaN or 0/0 position as strong proof | fixed: `evidence.num` finite-and-range checks, EXIF 0/0 ignored, NaN device position 400 | verify_field H5 rows |
| H6 positions lost, one bad fix blocks queue | fixed: phone sends 500 at a time and drops only what was sent; bad fixes skipped one by one; over 1000 per request 413 | verify_field H6 rows; field_queue_test J5 |
| H7 undecodable photos give 500 | fixed: decode before storing, 415 with a plain message; optional HEIF support when pillow_heif is installed | verify_field H7 rows |
| H8 revisit hidden after 14 days | fixed: open work (new, revisit) is listed whatever its age | verify_field H8/G1 |
| H9 migration errors swallowed | fixed: only "duplicate column" and "already exists" are skipped, anything else stops start-up | t_migrate run: with the lock held init fails after 31 s, then succeeds (`/tmp/claude-0/fieldfix/out_migrate.txt`) |
| M1 memory exhaustion | fixed: body size cap (`FS_MAX_BODY_MB`) before reading, 15 MB per photo, 6 photos, `MAX_IMAGE_PIXELS`, draft decoding | verify_field M1 rows |
| M2 verdict change after split, other-range photos | fixed: verdicts locked once two reviewers answered, queue text no longer shows the split, blind-review reviewers may open the photos | verify_field M2/V5, V5b |
| M3 phone clock trusted | fixed: page stamps photos, visits and positions with the server-corrected clock; server flags `photo_time_in_future` and clamps a future `visited_utc` (not in replay mode) | field_queue_test J6; `/tmp/claude-0/fieldfix/out_m3.txt` |
| M4 v1 report JSON not validated | fixed: type and range checks, 400 with the field name | verify_field M4 rows |
| M5 built-in pages send no webhooks | fixed: reached, reported and reviewed from the field page and control room are queued | verify_field M5/W2; webhook_test.py |
| M6 division filter after LIMIT | fixed: in SQL before LIMIT, `Division:Range` supported | verify_field M6/W5 |
| M7 plain range name, unknown beats | fixed: add_staff checks the beat or range; a repeated range name needs `Division:Range` | verify_field M7 rows |
| M8 reached/first report times missing | fixed: `reached_utc`, `first_report_utc`, `updated_utc` in alert JSON | verify_field M8/W1 |
| M9 XSS via task score | fixed: score stored as a number, escaped in control.html | verify_field M9 |
| M10 fixes with no accuracy reach; v1 pings without beats | fixed: a fix without acc_m or over 100 m does not count; v1 defaults to the staff record's beat, else 400 | verify_field M10 rows |
| L1 guard detections statewide | fixed: guard sees points near their beat only; bad bbox 400 | verify_field L1 |
| L2 eNetra users in the sign-in list | fixed: list is admin only and leaves out accounts without a PIN | verify_field L2 |
| L3 CSV formula injection | fixed: `csv_cell` on every export | verify_field L3 |
| L4 sessions never deleted, no Secure flag | fixed: expired sessions deleted at login; `FS_SECURE_COOKIE=1` sets Secure (turn on with HTTPS) | verify_field L4 |
| L5 server paths in task import errors | fixed | verify_field L5 |
| L6 negative area or crew, 2099, 1 MB notes | fixed: range and length checks | verify_field L6 rows |
| L7 device id is advisory | not fixed (read only; owner decision) | - |
| L8 photo reuse is exact sha256 only | not fixed (a perceptual hash is an owner decision) | - |
| L9 pilot_test depends on run order | fixed: `scripts/run_tests.py` gives each test its own fresh database | run_tests.py: 4 of 4 pass |
| L10 CORS and service key | fixed in INTEGRATION.md: the key is server-only, there is no CORS on purpose | doc |

Needs an owner decision (not done):
- Sign-in now asks for the staff number instead of picking a name from a public list. Officials will see this change.
- PINs are 4-12 digits for everyone. Should admins need longer ones?
- Should `no_camera_data` alone make a photo weak?
- L7 (device id is only advisory) and L8 (a perceptual photo hash).
- eNetra should move to `X-Signature-Ts`, reject old timestamps and de-duplicate on `X-Event-Id`. `X-Signature` is still sent for compatibility.
- API changes eNetra will notice: a v1 review with no report gives 400; accept and send-back work only on `visited`; reviewing your own report gives 403.
- The server now refuses to start while the database is locked or a migration fails. The deployment needs a restart policy (service manager) for that.
