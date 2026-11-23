"""Settings, all from environment variables so nothing secret lives in files."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FS_DATA_DIR", BASE / "var"))
DB_PATH = DATA_DIR / "field.db"
PHOTO_DIR = DATA_DIR / "photos"
# All 8,973 MP beats (from E:\MP_Merge\Mp_Beat_Merge.shp) when present, else the Ratapani grid beats.
_mp = BASE / "data/beats_mp.geojson"
BEATS_PATH = Path(os.environ.get("FS_BEATS", _mp if _mp.exists() else BASE / "data/beats.geojson"))

# lon_min, lat_min, lon_max, lat_max. Default: a box around Madhya Pradesh.
BBOX = tuple(float(x) for x in os.environ.get("FS_BBOX", "74.0,21.0,82.9,26.9").split(","))
POLL_MINUTES = float(os.environ.get("FS_POLL_MINUTES", "15"))
FIRMS_REGION = os.environ.get("FS_FIRMS_REGION", "South_Asia")
# Optional. Only needed for archive imports through the FIRMS area API; the live
# feed uses NASA's public 24 h / 7 d files, which need no key.
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")
# FSI's open Fire Point Search portal: FSI's own alerts with beat + compartment tags. State 20 = Madhya Pradesh.
FSI_PORTAL = os.environ.get("FS_FSI_PORTAL", "1") == "1"
FSI_STATE = os.environ.get("FS_FSI_STATE", "20")
# NRSC's Bhuvan forest-fire panel: the same VIIRS/MODIS pixels as FIRMS, 1-5 h sooner (app/bhuvan.py).
BHUVAN = os.environ.get("FS_BHUVAN", "1") == "1"
# Burn scars for live alerts: run the burn-scar thread's live.py once a day after the poll (needs
# geopandas, rasterio, planetary-computer, pystac-client). Any AOI works; ~10-15 s per new fire event.
SCAR_LIVE = os.environ.get("FS_SCAR_LIVE", "1") == "1"
SCAR_SCRIPT = os.environ.get("FS_SCAR_SCRIPT", "/mnt/project-files/fire-alert-scars/scripts/live.py")
# All MP beats since 15 Oct 2026 (burn-scar thread; ~20-40 min a run in peak season). The older Ratapani-only
# results in fire-alert-scars/live/ are still read, see scars.py.
SCAR_AOI = os.environ.get("FS_SCAR_AOI", "/mnt/project-files/fire-alert-scars/mp/mp_beats_aoi.geojson")
SCAR_LIVE_DIR = os.environ.get("FS_SCAR_LIVE_DIR", "/mnt/project-files/fire-alert-scars/mp/live")
SCAR_EVERY_HOURS = float(os.environ.get("FS_SCAR_EVERY_HOURS", "24"))

# Detections join an open incident when they fall within this distance of one of
# its detections and within this many hours of its latest detection.
CLUSTER_KM = float(os.environ.get("FS_CLUSTER_KM", "1.5"))
CLUSTER_HOURS = float(os.environ.get("FS_CLUSTER_HOURS", "48"))
# Hours from the first detection by which a field visit is expected.
VISIT_DUE_HOURS = float(os.environ.get("FS_VISIT_DUE_HOURS", "24"))
# A photo taken farther than this from every detection of the incident is flagged.
MAX_PHOTO_KM = {"VIIRS": 1.0, "MODIS": 1.5}
SESSION_DAYS = 30
# Set FS_SECURE_COOKIE=1 when the app is served over HTTPS (cloud VM, tunnel): the session cookie is then sent only over HTTPS.
SECURE_COOKIE = os.environ.get("FS_SECURE_COOKIE", "") == "1"
# Sign-in: after this many wrong PINs in a row an account (or a client address) is locked, 30 s doubling up to 1 h.
LOGIN_FAILS_ACCOUNT = int(os.environ.get("FS_LOGIN_FAILS_ACCOUNT", "5"))
LOGIN_FAILS_IP = int(os.environ.get("FS_LOGIN_FAILS_IP", "20"))
# Largest request body (6 photos x 15 MB + form); bigger ones get 413 before they are read.
MAX_BODY = int(float(os.environ.get("FS_MAX_BODY_MB", "100")) * 2 ** 20)

# Forest filter (FSI keeps only points in forest). Share of ESA WorldCover tree + shrub
# 10 m pixels within the fire pixel's footprint; below this a point creates no field task.
# 0.10 keeps 93.5% of Ratapani's Feb-May 2024 VIIRS points and 15% of MP in-beat points in Oct 2026.
FOREST_FILTER = os.environ.get("FS_FOREST_FILTER", "1") == "1"
FOREST_MIN = float(os.environ.get("FS_FOREST_MIN", "0.10"))
# Phone within this distance of a fire point counts as "reached" (Odisha uses 200 m).
ARRIVE_KM = float(os.environ.get("FS_ARRIVE_KM", "0.2"))
# A report filed farther than this from the fire is flagged (Uttarakhand only allows updates within 500 m).
REPORT_KM = float(os.environ.get("FS_REPORT_KM", "0.5"))
# Share of submitted visits picked at random for an in-person re-check by the ranger.
RECHECK_SHARE = float(os.environ.get("FS_RECHECK_SHARE", "0.07"))
MASK_PATH = Path(os.environ.get("FS_MASK", BASE / "data/industry_mask.geojson"))
# Integration with another platform (e.g. eNetra). Keys and secrets come only from the environment.
SERVICE_KEYS = {k.strip() for k in os.environ.get("FS_SERVICE_KEYS", "").split(",") if k.strip()}
WEBHOOK_URL = os.environ.get("FS_WEBHOOK_URL", "")
WEBHOOK_SECRET = os.environ.get("FS_WEBHOOK_SECRET", "")
# Persistent heat (static sources: kilns, flares, furnaces OSM misses): a point with fire seen on at least
# this many distinct days within PERSIST_KM over the past PERSIST_DAYS creates no task.
PERSIST_DAYS = int(os.environ.get("FS_PERSIST_DAYS", "365"))
PERSIST_MIN_DAYS = int(os.environ.get("FS_PERSIST_MIN_DAYS", "8"))
PERSIST_KM = float(os.environ.get("FS_PERSIST_KM", "0.4"))
# Demo replay of a past day: the server treats this UTC time as "now". Leave unset in real use.
DEMO_NOW = os.environ.get("FS_DEMO_NOW", "")

# Forecast-led patrol pilot (research/reframe/pilot/PROTOCOL.md). Beat -> arm table, and the 500 m grids for cell tasks.
BEAT_ARMS = os.environ.get("FS_BEAT_ARMS", "/mnt/project-files/research/reframe/pilot/beat_arms.csv")
RATAPANI_GRID = os.environ.get("FS_RATAPANI_GRID", "/mnt/project-files/ratapani/grid_500m.geojson")
RATAPANI_CELL_BEAT = os.environ.get("FS_RATAPANI_CELL_BEAT", "/mnt/project-files/ratapani/beats/cell_beat.csv")
MP_GRID = os.environ.get("FS_MP_GRID", "/mnt/project-files/ratapani/mp_grid/mp_grid.json")
MP_CELLS = os.environ.get("FS_MP_CELLS", "/mnt/project-files/ratapani/mp_grid/mp_cells.parquet")   # square -> beat
# Officials' 2-day list (app/daily_list.py): "pool" = 50% division floor + 25% quiet reserve + statewide pool
# (research/ceiling/DAILY_RULE_SPEC.md); "division" = each division fills its own danger-scaled count.
DAILY_RULE = os.environ.get("FS_DAILY_RULE", "pool")
# Quiet-square share of the floor and of the pool (Akkshay 21 Oct 2026: 35%; the PC's live-rule curve, vanagni c04a9e1) and
# k, the multiplier on the danger-scaled count that keeps the ground flagged-or-next equal to the hindsight yardstick's.
# k = 0.58740234375 is the PC's own value at 35% (bisected on 2026, ground covered 21.9%; its 25% k was 0.60322265625).
# The app's own fit on the five 2026 check days, used until the PC's arrived, was 0.5844.
QUIET_SHARE = float(os.environ.get("FS_QUIET_SHARE", "0.35"))
DAILY_K = float(os.environ.get("FS_DAILY_K", "0.58740234375"))
# A photo or report this far outside a predicted cell is flagged (the cell is 500 m; GPS is +-10-30 m in forest).
CELL_MARGIN_KM = float(os.environ.get("FS_CELL_MARGIN_KM", "0.1"))
# A cell check counts as an inspection (not just an arrival) when photos inside the cell, taken in the task window,
# plus the phone's positions inside it, span at least this many metres.
INSPECT_SPREAD_M = float(os.environ.get("FS_INSPECT_SPREAD_M", "100"))

# Cause check on late-Feb alerts (Akkshay, 17 Oct 2026): from this season on, the guard must give the likely cause on every
# alert tagged "possible control burn" and on an equal-sized random sample of untagged 15-28 Feb alerts.
CAUSE_FROM_YEAR = int(os.environ.get("FS_CAUSE_FROM_YEAR", "2027"))
