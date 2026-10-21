"""Burn scars for live alerts: run the burn-scar thread's live.py once a day after the FIRMS/FSI poll.

live.py (in /mnt/project-files/fire-alert-scars/scripts/) pulls the last 7 days of FIRMS points in its
AOI, groups them into fire events, looks for each event's scar in Sentinel-2/Landsat, and re-checks
events still waiting for a clear image or with a provisional scar for up to 45 days. It takes about
10-15 s per new event, so it runs in a background thread. scars.py reads its live/ files.
The first scar usually shows ~3 days after the alert (95% within 5), confirmation within ~5 days (90% within 8).
After each run, alerts whose scar changed get an alert.updated webhook.
"""
import logging, os, subprocess, sys, threading
from datetime import datetime, timedelta, timezone
from . import config, db, scars

log = logging.getLogger("scar_live")
_lock = threading.Lock()
SOURCE = "SCAR_LIVE"


def _last_run(con):
    r = con.execute("SELECT max(utc) FROM ingest_log WHERE source=? AND error IS NULL", (SOURCE,)).fetchone()
    return r[0]


def _snapshot(con):
    """Scar result per alert seen in the last 46 days."""
    since = (datetime.now(timezone.utc) - timedelta(days=46)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {}
    for i in con.execute("SELECT id FROM incidents WHERE last_seen_utc >= ?", (since,)).fetchall():
        pts = con.execute("SELECT lat, lon, acq_utc FROM detections WHERE incident_id=?", (i["id"],)).fetchall()
        out[i["id"]] = scars.for_points(pts)
    return out


def run():
    """Run live.py once, now. Returns the number of alerts whose scar changed."""
    with db.tx() as con:
        before = _snapshot(con)
    cmd = [sys.executable, config.SCAR_SCRIPT, config.SCAR_AOI, config.SCAR_LIVE_DIR]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600, cwd=os.path.dirname(config.SCAR_SCRIPT))
        err = None if p.returncode == 0 else (p.stderr or p.stdout)[-500:]
    except subprocess.TimeoutExpired:
        err = "live.py timed out after 6 h"
    changed = []
    with db.tx() as con:
        if not err:
            after = _snapshot(con)
            changed = [i for i, s in after.items() if s != before.get(i)]
        con.execute("INSERT INTO ingest_log(utc,source,new_rows,error) VALUES (?,?,?,?)", (now, SOURCE, len(changed), err))
    if err:
        log.error("live.py failed: %s", err)
        return 0
    if changed and config.WEBHOOK_URL:
        from . import webhook
        from .api_v1 import alert_json
        with db.tx() as con:
            for iid in changed:
                webhook.send("alert.updated", alert_json(con, con.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()))
    return len(changed)


def run_if_due():
    """Start a background run when the last good run is older than FS_SCAR_EVERY_HOURS."""
    if not config.SCAR_LIVE or _lock.locked():
        return False
    with db.tx() as con:
        last = _last_run(con)
    if last and datetime.now(timezone.utc) - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) \
            < timedelta(hours=config.SCAR_EVERY_HOURS):
        return False

    def go():
        with _lock:
            try:
                n = run()
                log.info("scar check done, %d alerts changed", n)
            except Exception:
                log.exception("scar check failed")
    threading.Thread(target=go, daemon=True).start()
    return True
