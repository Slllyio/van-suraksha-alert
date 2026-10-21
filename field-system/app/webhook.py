"""Push alert changes to another platform (eNetra). POST JSON, signed with HMAC-SHA256 of the body
in the X-Signature header (hex) when FS_WEBHOOK_SECRET is set.

Events are queued durably (webhook_outbox) and one worker delivers them in order with backoff, so nothing is
lost while eNetra is down and events never overtake each other. Each POST also carries X-Event-Id (de-duplicate
on it: a retry after a lost answer sends the same id again), X-Timestamp (unix s) and X-Signature-Ts = HMAC of
X-Timestamp + "." + body (check it and reject old timestamps to stop replays)."""
import hashlib, hmac, json, logging, threading, time, urllib.request
from . import config

log = logging.getLogger("webhook")
_wake = threading.Event()
_started = False
UTC = "%Y-%m-%dT%H:%M:%SZ"


def _now(dt=0):
    return time.strftime(UTC, time.gmtime(time.time() + dt))


def send(event, payload):
    """Queue the event (call it outside an open write transaction); never blocks on eNetra."""
    if not config.WEBHOOK_URL:
        return
    from . import db
    with db.tx() as con:
        cur = con.execute("INSERT INTO webhook_outbox(event, body, created_utc, next_utc) VALUES (?,?,?,?)", (event, b"", _now(), _now()))
        body = json.dumps({"id": cur.lastrowid, "event": event, "queued_utc": _now(), "data": payload}, default=str).encode()
        con.execute("UPDATE webhook_outbox SET body=? WHERE id=?", (body, cur.lastrowid))
    start()
    _wake.set()


def start():
    global _started
    if config.WEBHOOK_URL and not _started:
        _started = True
        threading.Thread(target=_worker, daemon=True).start()


def _headers(r):
    ts = str(int(time.time()))
    h = {"Content-Type": "application/json", "X-Event": r["event"], "X-Event-Id": str(r["id"]), "X-Timestamp": ts}
    if config.WEBHOOK_SECRET:
        k = config.WEBHOOK_SECRET.encode()
        h["X-Signature"] = hmac.new(k, r["body"], hashlib.sha256).hexdigest()
        h["X-Signature-Ts"] = hmac.new(k, ts.encode() + b"." + r["body"], hashlib.sha256).hexdigest()
    return h


def deliver_due():
    """Send what is due, oldest first; stop at the first failure so later events wait their turn. Returns how many went."""
    from . import db
    with db.tx() as con:
        rows = con.execute("SELECT * FROM webhook_outbox WHERE sent_utc IS NULL ORDER BY id LIMIT 100").fetchall()
    n = 0
    for r in rows:
        if r["next_utc"] > _now():
            break                                      # the oldest is backing off: keep the order
        try:
            urllib.request.urlopen(urllib.request.Request(config.WEBHOOK_URL, data=r["body"], headers=_headers(r)), timeout=30)
            with db.tx() as con:
                con.execute("UPDATE webhook_outbox SET sent_utc=?, tries=tries+1 WHERE id=?", (_now(), r["id"]))
            n += 1
        except Exception as e:
            delay = min(3600, 15 * 2 ** min(r["tries"], 8))
            log.warning("webhook %s #%s failed (try %s, next in %s s): %s", r["event"], r["id"], r["tries"] + 1, delay, e)
            with db.tx() as con:
                con.execute("UPDATE webhook_outbox SET tries=tries+1, last_error=?, next_utc=? WHERE id=?",
                            (str(e)[:200], _now(delay), r["id"]))
            break
    return n


def _worker():
    from . import db
    while True:
        _wake.clear()
        try:
            while deliver_due() == 100:
                pass
            with db.tx() as con:   # sent events are kept 30 days for tracing
                con.execute("DELETE FROM webhook_outbox WHERE sent_utc IS NOT NULL AND sent_utc < ?", (_now(-30 * 86400),))
        except Exception:
            log.exception("webhook worker")
        _wake.wait(15)
