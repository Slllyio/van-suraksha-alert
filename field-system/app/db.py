import sqlite3, time
from contextlib import contextmanager
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,            -- VIIRS_SNPP | VIIRS_NOAA20 | VIIRS_NOAA21 | MODIS | archive
  instrument TEXT NOT NULL,        -- VIIRS | MODIS
  satellite TEXT, lat REAL NOT NULL, lon REAL NOT NULL,
  acq_utc TEXT NOT NULL, confidence TEXT, frp REAL, daynight TEXT,
  bright REAL, scan REAL, track REAL,
  beat_uid TEXT, incident_id INTEGER,
  ingested_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  UNIQUE(instrument, satellite, lat, lon, acq_utc)
);
CREATE INDEX IF NOT EXISTS det_time ON detections(acq_utc);
CREATE INDEX IF NOT EXISTS det_latlon ON detections(lat, lon);
CREATE INDEX IF NOT EXISTS det_inc ON detections(incident_id);

CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY,
  beat_uid TEXT NOT NULL,
  lat REAL NOT NULL, lon REAL NOT NULL,
  first_seen_utc TEXT NOT NULL, last_seen_utc TEXT NOT NULL,
  n_detections INTEGER NOT NULL DEFAULT 0, max_frp REAL, sensors TEXT,
  status TEXT NOT NULL DEFAULT 'new',  -- new | visited | verified | revisit
  outcome TEXT,                        -- from the accepted field report
  due_utc TEXT NOT NULL,
  first_report_utc TEXT,
  large INTEGER NOT NULL DEFAULT 0,    -- FSI large fire: 3+ adjacent VIIRS pixels in one pass
  created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS inc_beat ON incidents(beat_uid, status);

-- Every beat an alert is sent to. As in FSI's FAST 3, a fire pixel that overlaps a
-- beat junction goes to all the beats it touches.
CREATE TABLE IF NOT EXISTS incident_beats (
  incident_id INTEGER NOT NULL, beat_uid TEXT NOT NULL, PRIMARY KEY (incident_id, beat_uid)
);
CREATE INDEX IF NOT EXISTS ib_beat ON incident_beats(beat_uid);

CREATE TABLE IF NOT EXISTS staff (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL, role TEXT NOT NULL,   -- guard | ranger | admin
  beat_uid TEXT, range_name TEXT, phone TEXT,
  pin_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, staff_id INTEGER NOT NULL, expires_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY,
  incident_id INTEGER NOT NULL, staff_id INTEGER NOT NULL,
  submitted_utc TEXT NOT NULL, visited_utc TEXT,
  device_lat REAL, device_lon REAL, device_acc_m REAL,
  outcome TEXT NOT NULL,    -- active_fire | burnt_out | no_fire | outside_forest | controlled_burn
  land_type TEXT, fire_type TEXT, area_ha REAL, cause TEXT, action TEXT, crew INTEGER, notes TEXT,
  distance_km REAL, evidence TEXT, flags TEXT
);

CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY,
  report_id INTEGER NOT NULL, path TEXT NOT NULL, thumb TEXT, sha256 TEXT NOT NULL,
  taken_utc TEXT, exif_lat REAL, exif_lon REAL,
  dev_lat REAL, dev_lon REAL, dev_utc TEXT, distance_km REAL, flags TEXT
);
CREATE INDEX IF NOT EXISTS photo_hash ON photos(sha256);

CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY,
  incident_id INTEGER NOT NULL, report_id INTEGER, reviewer_id INTEGER NOT NULL,
  decision TEXT NOT NULL, note TEXT,
  utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Phone positions while the field page is open: the route to the fire, and auto "reached".
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY, staff_id INTEGER NOT NULL, device_id TEXT,
  utc TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, acc_m REAL
);
CREATE INDEX IF NOT EXISTS pos_staff ON positions(staff_id, utc);

-- Crew-day log for the patrol pilot: staff-hours include travel and idle time between checks.
CREATE TABLE IF NOT EXISTS shifts (
  id INTEGER PRIMARY KEY, staff_id INTEGER NOT NULL, start_utc TEXT NOT NULL, end_utc TEXT,
  crew_size INTEGER NOT NULL DEFAULT 1, start_lat REAL, start_lon REAL, end_lat REAL, end_lon REAL,
  device_id TEXT, notes TEXT, auto_closed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS shift_staff ON shifts(staff_id, start_utc);

-- Patrol pilot shadow lists (e.g. the recent-fire ranker): stored for scoring after the season, never sent as tasks.
CREATE TABLE IF NOT EXISTS shadow_lists (
  id INTEGER PRIMARY KEY, issue_date TEXT NOT NULL, list_name TEXT NOT NULL, model_version TEXT NOT NULL,
  cells TEXT NOT NULL, received_utc TEXT NOT NULL, UNIQUE(issue_date, list_name)
);

-- Protocol v3: one row per unique fire found on the ground (reports within 500 m and 2 days with no satellite event are
-- one fire; fires on or next to a satellite event take that event's id). Provisional until the post-season grouping.
CREATE TABLE IF NOT EXISTS fires (
  fire_id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, lat REAL, lon REAL, credited_report_id INTEGER,
  discovered_utc TEXT, credited_stream TEXT, class_auto TEXT, class_final TEXT, final_reason TEXT,
  grouping TEXT, fire_first_utc TEXT, est_ignition_utc TEXT, chips TEXT, merged_into TEXT, queued INTEGER NOT NULL DEFAULT 0,
  queue_reason TEXT, grouping_utc TEXT
);

-- Blind post-season adjudication of fires where field burn age and the satellite grouping disagree.
CREATE TABLE IF NOT EXISTS fire_verdicts (
  id INTEGER PRIMARY KEY, fire_id TEXT NOT NULL, reviewer_id INTEGER NOT NULL, verdict TEXT NOT NULL, reason TEXT NOT NULL,
  utc TEXT NOT NULL, UNIQUE(fire_id, reviewer_id)
);

-- big-fire points per alert, kept once the first look is complete (app/big_fire.py), so restarts and big lists don't rescore
CREATE TABLE IF NOT EXISTS big_fire_score (incident_id INTEGER PRIMARY KEY, data TEXT NOT NULL);

-- 30 m direction hint per alert (app/direction.py): last check and, when found, the arrow
CREATE TABLE IF NOT EXISTS fire_direction (
  incident_id INTEGER PRIMARY KEY, checked_utc TEXT NOT NULL, status TEXT NOT NULL, data TEXT
);

-- "which side runs farther" hint per new fire (app/runway.py)
CREATE TABLE IF NOT EXISTS fire_runway (
  incident_id INTEGER PRIMARY KEY, checked_utc TEXT NOT NULL, status TEXT NOT NULL, data TEXT
);

CREATE TABLE IF NOT EXISTS ingest_log (
  id INTEGER PRIMARY KEY, utc TEXT NOT NULL, source TEXT, fetched INTEGER,
  in_bbox INTEGER, new_rows INTEGER, new_incidents INTEGER, error TEXT
);
"""


def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def locked(e):
    return isinstance(e, sqlite3.OperationalError) and "locked" in str(e)


def write(fn, tries=3):
    """fn(con) in its own transaction, tried again a few times when the database stays locked past the 30 s busy wait
    (a guard's report or position must not fail on a busy minute). Returns fn's result."""
    for i in range(tries):
        try:
            with tx() as con:
                return fn(con)
        except sqlite3.OperationalError as e:
            if not locked(e) or i == tries - 1:
                raise
            time.sleep(1 + 2 * i)


MIGRATIONS = [
    "ALTER TABLE detections ADD COLUMN forest_share REAL",
    "ALTER TABLE detections ADD COLUMN mask_kind TEXT",
    "ALTER TABLE incidents ADD COLUMN arrived_utc TEXT",
    "ALTER TABLE incidents ADD COLUMN arrived_by INTEGER",
    "ALTER TABLE reports ADD COLUMN device_id TEXT",
    "ALTER TABLE reports ADD COLUMN first_known_by TEXT",
    "ALTER TABLE reports ADD COLUMN fire_out_utc TEXT",
    "ALTER TABLE reports ADD COLUMN recheck INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE detections ADD COLUMN fsi_division TEXT",
    "ALTER TABLE detections ADD COLUMN fsi_range TEXT",
    "ALTER TABLE detections ADD COLUMN fsi_beat TEXT",
    "ALTER TABLE detections ADD COLUMN fsi_compartment TEXT",
    # patrol pilot (pilot.py): kind = alert | predicted | chance
    "ALTER TABLE incidents ADD COLUMN kind TEXT NOT NULL DEFAULT 'alert'",
    "ALTER TABLE incidents ADD COLUMN task_ref TEXT",
    "ALTER TABLE incidents ADD COLUMN issue_date TEXT",
    "ALTER TABLE incidents ADD COLUMN due_from_utc TEXT",
    "ALTER TABLE incidents ADD COLUMN cell_id TEXT",
    "ALTER TABLE incidents ADD COLUMN cell_geom TEXT",
    "ALTER TABLE incidents ADD COLUMN arm TEXT",
    "ALTER TABLE incidents ADD COLUMN model_hash TEXT",
    "ALTER TABLE incidents ADD COLUMN near_active_fire INTEGER",
    "ALTER TABLE incidents ADD COLUMN score REAL",
    "CREATE UNIQUE INDEX IF NOT EXISTS inc_task_ref ON incidents(task_ref)",
    "ALTER TABLE reports ADD COLUMN burn_age TEXT",
    "ALTER TABLE reports ADD COLUMN linked_alerts TEXT",
    # protocol amendments (Akkshay's review, 15 Oct): task stream, full version record, inspection vs arrival, cross-beat fires
    "ALTER TABLE incidents ADD COLUMN stream TEXT",
    "ALTER TABLE incidents ADD COLUMN model_version TEXT",
    "ALTER TABLE incidents ADD COLUMN cause_required INTEGER",   # 2027 cause check, see control_burn.cause_check
    "ALTER TABLE incidents ADD COLUMN cause_group TEXT",
    "ALTER TABLE incidents ADD COLUMN cause_p REAL",
    "ALTER TABLE reports ADD COLUMN inspection TEXT",
    # protocol v2: stream per report (ignition / response), spillover between beats, suppression
    "ALTER TABLE reports ADD COLUMN stream TEXT",
    "ALTER TABLE reports ADD COLUMN crosses_beat_boundary TEXT",
    "ALTER TABLE reports ADD COLUMN beats_touched TEXT",
    "ALTER TABLE reports ADD COLUMN suppression TEXT",
    "ALTER TABLE reports ADD COLUMN suppression_utc TEXT",
    # protocol v3
    "ALTER TABLE reports ADD COLUMN fire_id TEXT",
    "ALTER TABLE reports ADD COLUMN site_entry_utc TEXT",
    "ALTER TABLE reports ADD COLUMN site_exit_utc TEXT",
    "ALTER TABLE shifts ADD COLUMN crew_logged INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS rep_fire ON reports(fire_id)",
    # protocol 0.9 (exploratory deterrence dose, optional per inspection)
    "ALTER TABLE reports ADD COLUMN people_met INTEGER",
    "ALTER TABLE reports ADD COLUMN enforcement TEXT",
    # audit 20 Oct 2026: updated_utc for `since` polling (every change bumps it), durable webhook outbox, report idempotency key
    "ALTER TABLE incidents ADD COLUMN updated_utc TEXT",
    """CREATE TRIGGER IF NOT EXISTS inc_touch AFTER UPDATE ON incidents WHEN NEW.updated_utc IS OLD.updated_utc
       BEGIN UPDATE incidents SET updated_utc = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = NEW.id; END""",
    "CREATE INDEX IF NOT EXISTS inc_updated ON incidents(updated_utc)",
    """CREATE TABLE IF NOT EXISTS webhook_outbox (id INTEGER PRIMARY KEY, event TEXT NOT NULL, body BLOB NOT NULL,
       created_utc TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0, next_utc TEXT NOT NULL, sent_utc TEXT, last_error TEXT)""",
    "ALTER TABLE reports ADD COLUMN client_ref TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS rep_client_ref ON reports(staff_id, client_ref) WHERE client_ref IS NOT NULL",
    # ingest audit 20 Oct 2026: points kept unfiltered because WorldCover could not be read; every beat FSI sent a pixel to
    "ALTER TABLE ingest_log ADD COLUMN forest_unknown INTEGER",
    """CREATE TABLE IF NOT EXISTS fsi_tags (detection_id INTEGER NOT NULL, division TEXT, range TEXT, beat TEXT NOT NULL,
       compartment TEXT, PRIMARY KEY (detection_id, beat)) WITHOUT ROWID""",
]


def init():
    with tx() as con:
        con.executescript(SCHEMA)
        from .daily_list import SCHEMA as DL
        if sum(r[5] > 0 for r in con.execute("PRAGMA table_info(daily_list)")) == 2:   # first version keyed (day, cell)
            con.execute("ALTER TABLE daily_list RENAME TO daily_list_v1")
            con.executescript(DL)
            con.execute("INSERT OR IGNORE INTO daily_list SELECT * FROM daily_list_v1")
            con.execute("DROP TABLE daily_list_v1")
        con.executescript(DL)
        from .big_watch_list import SCHEMA as BW
        sz = con.execute("SELECT sql FROM sqlite_master WHERE name='size_score'").fetchone()
        if sz and "WITHOUT ROWID" not in sz[0]:          # 3 nights of scores, sent again every night: rebuild in the new layout
            con.execute("ALTER TABLE size_score RENAME TO size_score_old")
            con.executescript(BW)
            con.execute("INSERT INTO size_score SELECT * FROM size_score_old")
            con.execute("DROP TABLE size_score_old")
        con.executescript(BW)
        for m in MIGRATIONS:
            try:
                con.execute(m)
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e) or "already exists" in str(e):
                    continue   # column / index already there
                raise          # locked, disk full, bad SQL: do not start half-migrated
        con.execute("ANALYZE")   # query plans: without statistics SQLite scans every VIIRS point for the box-and-time queries
