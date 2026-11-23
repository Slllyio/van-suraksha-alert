"""Keep a per-alert scar ledger up to date for new fire alerts.

Each run:
 1. pulls the last 7 days of FIRMS near-real-time detections (MODIS, VIIRS S-NPP, NOAA-20, NOAA-21;
    public files, no key) and keeps those inside the AOI;
 2. groups alerts on the same day within 1 km into one fire event;
 3. runs alert_scar.py on every event that is new or still 'waiting' for a clear post-fire image
    (events give up after 45 days without one: status 'no_clear_image').

Files (in <outdir>, default /mnt/project-files/fire-alert-scars/live/):
  alerts.csv   every alert seen, with its event_id
  events.csv   one row per event: status, scar_ha, severity, image pair, dist_m, beat, last_checked.
               A scar with persist_checked False is provisional (no later clear look yet) and is re-checked.
  scars.geojson  scar polygons, one feature per event with a scar
Usage: python live.py [aoi.geojson] [outdir]
"""
import os, sys, io, json, datetime as dt, warnings
import numpy as np, pandas as pd, geopandas as gpd, requests
from shapely.geometry import shape
from scipy.spatial import cKDTree
from pyproj import Transformer

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alert_scar

FEEDS = {"modis": "modis-c6.1/csv/MODIS_C6_1_South_Asia_7d.csv",
         "viirs-snpp": "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_Asia_7d.csv",
         "viirs-noaa20": "noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_Asia_7d.csv",
         "viirs-noaa21": "noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_Asia_7d.csv"}
BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
GIVE_UP_DAYS = 45
TO = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def pull(aoi):
    fr = []
    for s, path in FEEDS.items():
        try:
            r = requests.get(BASE + path, timeout=120)
            r.raise_for_status()
            a = pd.read_csv(io.StringIO(r.text), dtype={"acq_time": str, "confidence": str})
        except Exception as ex:
            print("feed failed", s, ex)
            continue
        x0, y0, x1, y1 = aoi.total_bounds
        a = a[a.latitude.between(y0, y1) & a.longitude.between(x0, x1)]
        if len(a):
            pts = gpd.GeoSeries(gpd.points_from_xy(a.longitude, a.latitude), crs=4326)
            a = a[pts.within(aoi.union_all()).values]
        a["sensor"] = s
        a = forest_only(a)
        a = not_industry(a)
        fr.append(a[["latitude", "longitude", "acq_date", "acq_time", "sensor", "confidence", "frp", "scan", "track"]])
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


FOREST_MIN = float(os.environ.get("LIVE_FOREST_MIN", "0.10"))
THREADS = int(os.environ.get("LIVE_THREADS", "8"))
_wc = None


def forest_only(a):
    """Drop NASA points with < 10% tree+shrub (ESA WorldCover) within 375 m, as FSI and the field system do:
    MP beats hold farmland and most other points are crop burning. FSI points are already forest-masked."""
    global _wc
    if FOREST_MIN <= 0 or not len(a):
        return a
    import time
    if _wc is None:
        sys.path.insert(0, "/mnt/project-files/field-system/app")
        from landcover import WorldCover
        _wc = WorldCover(3000)

    def ok(la, lo):
        for k in range(4):
            try:
                return _wc.share(la, lo, 0.375)[1] >= FOREST_MIN
            except Exception as ex:
                err = ex
                time.sleep(2 ** k)
        print("forest check failed, point left for the next run", la, lo, err)
        return False   # fail closed: an unchecked point is not recorded, so the 7-day feed brings it back next run
    keep = [ok(la, lo) for la, lo in zip(a.latitude, a.longitude)]
    return a[keep]


_ind = None


def not_industry(a):
    """Drop NASA points inside the field system's mine/industry/solar mask (OSM, 500 m): steady heat sources,
    e.g. 22% of Singrauli's VIIRS points are FIRMS static-source points. They have no forest scar to find."""
    global _ind
    if not len(a):
        return a
    if _ind is None:
        _ind = gpd.read_file("/mnt/project-files/field-system/data/industry_mask.geojson").to_crs(4326).union_all()
    pts = gpd.GeoSeries(gpd.points_from_xy(a.longitude, a.latitude), crs=4326)
    return a[~pts.within(_ind).values]


FSI_URL = "https://fsiforestfire.gov.in/FirePointSearch/DownloadCsv?FromDate={d0}&ToDate={d1}&Source=Both&State=20"


def pull_fsi(aoi, days=7):
    """FSI's own alerts (open Fire Point Search portal, Madhya Pradesh), so FSI-only alerts get a scar too.
    FSI dates and times are IST; kept as FSI gives them. sensor fsi-viirs / fsi-modis."""
    today = dt.date.today()
    import time
    for k in range(4):   # the portal sometimes resets a request; retry with backoff
        try:
            r = requests.get(FSI_URL.format(d0=(today - dt.timedelta(days)).isoformat(), d1=(today + dt.timedelta(1)).isoformat()),
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=120)   # the portal resets requests without a browser UA
            r.raise_for_status()
            a = pd.read_csv(io.StringIO(r.text), dtype=str)
            break
        except Exception as ex:
            print("FSI portal failed", k + 1, ex)
            if k == 3:
                return pd.DataFrame()
            time.sleep(5 * 2 ** k)
    if not len(a):
        return pd.DataFrame()
    a = a.rename(columns={"Lat": "latitude", "Lon": "longitude", "Fire_Date": "acq_date"})
    a["latitude"], a["longitude"] = a.latitude.astype(float), a.longitude.astype(float)
    a["acq_time"] = a.Fire_Time.str.replace(":", "").str[:4]
    a["sensor"] = np.where(a.Source_Type.str.strip().str.upper().str.startswith("MODIS"), "fsi-modis", "fsi-viirs")
    a["confidence"], a["frp"], a["scan"], a["track"] = "fsi", np.nan, np.nan, np.nan
    pts = gpd.GeoSeries(gpd.points_from_xy(a.longitude, a.latitude), crs=4326)
    a = a[pts.within(aoi.union_all()).values]
    return a[["latitude", "longitude", "acq_date", "acq_time", "sensor", "confidence", "frp", "scan", "track"]]


def assign_events(A, E):
    """Same day, within 1 km of an existing event seed -> that event; else a new event."""
    A = A.copy()
    A["x"], A["y"] = TO.transform(A.longitude.values, A.latitude.values)
    A["event_id"] = A.get("event_id")
    for day, g in A[A.event_id.isna()].groupby("acq_date"):
        seeds = E[E.acq_date == day] if len(E) else pd.DataFrame()
        for i, r in g.iterrows():
            if len(seeds):
                sx, sy = TO.transform(seeds.longitude.values, seeds.latitude.values)
                d = np.hypot(sx - r.x, sy - r.y)
                if d.min() <= 1000:
                    A.at[i, "event_id"] = seeds.event_id.values[d.argmin()]
                    continue
            eid = f"E{day.replace('-', '')}-{r.latitude:.4f}-{r.longitude:.4f}"
            A.at[i, "event_id"] = eid
            new = pd.DataFrame([dict(event_id=eid, acq_date=day, latitude=r.latitude, longitude=r.longitude,
                                     sensor=r.sensor, scan=r.scan, track=r.track, status="new")])
            E = pd.concat([E, new], ignore_index=True)
            seeds = E[E.acq_date == day]
    return A.drop(columns=["x", "y"]), E


def main(aoi_path="/mnt/project-files/ratapani/ratapani_aoi.geojson", outdir="/mnt/project-files/fire-alert-scars/live/"):
    aoi_path, outdir = os.path.abspath(aoi_path), os.path.abspath(outdir)   # any working directory
    os.makedirs(outdir, exist_ok=True)
    fa, fe, fg = (os.path.join(outdir, f) for f in ("alerts.csv", "events.csv", "scars.geojson"))
    aoi = gpd.read_file(aoi_path).to_crs(4326)
    old = pd.read_csv(fa, dtype=str) if os.path.exists(fa) else pd.DataFrame()
    E = pd.read_csv(fe) if os.path.exists(fe) else pd.DataFrame(columns=["event_id", "acq_date", "status"])
    for c in ("last_error", "last_checked", "status", "beat_uid", "division", "range", "beat"):   # all-blank columns load as float
        if c in E:
            E[c] = E[c].astype(object)
    new = pull(aoi)
    fsi = pull_fsi(aoi)
    new = pd.concat([x for x in (new, fsi) if len(x)], ignore_index=True) if len(new) or len(fsi) else new
    if len(new):
        # VIIRS seeds events first, then MODIS, then FSI points (they join a NASA event within 1 km)
        new = new.iloc[new.sensor.map(lambda s: 2 if s.startswith("fsi") else 1 if s == "modis" else 0).argsort(kind="stable")]
        new = new.astype({"acq_time": str})
        if len(old):
            k = ["latitude", "longitude", "acq_date", "acq_time", "sensor"]
            seen = set(map(tuple, old[k].astype(str).values))
            new = new[[tuple(v) not in seen for v in new[k].astype(str).values]]
        new, E = assign_events(new, E)
        old = pd.concat([old, new.astype(str)], ignore_index=True)
    feats = json.load(open(fg))["features"] if os.path.exists(fg) else []
    today = dt.date.today()
    # scars not yet confirmed by a later clear look are provisional and get re-checked
    prov = E.status.astype(str).str.startswith("scar") & (E.get("persist_checked", pd.Series(True, E.index)).astype(str) == "False")
    young = pd.to_datetime(E.acq_date) >= pd.Timestamp(dt.date.today() - dt.timedelta(GIVE_UP_DAYS))
    todo = E[E.status.isin(["new", "waiting", "no_pre", "error"]) | (prov & young)]
    def find(e):
        try:
            return alert_scar.alert_scar(float(e.latitude), float(e.longitude), e.acq_date,
                                         "modis" if str(e.sensor).endswith("modis") else "viirs", float(e.scan), float(e.track),
                                         radius_m=400 if str(e.sensor) == "fsi-viirs" and str(e.acq_date) < "2026-04-27" else None)
        except Exception as ex:
            return ex
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(THREADS) as ex_:
        found = list(ex_.map(find, [e for _, e in todo.iterrows()]))
    for (i, e), r in zip(todo.iterrows(), found):
        age = (today - dt.date.fromisoformat(str(e.acq_date))).days
        if isinstance(r, Exception):
            ex = r
            # a failed re-check (network, Planetary Computer) never wipes an earlier result:
            # keep it, note the error, try again next run
            E.loc[i, "last_error"] = f"{today.isoformat()}: {str(ex)[:200]}"
            if str(e.status) in ("new", "nan", ""):
                E.loc[i, "status"] = "error"
            print(e.event_id, "error, kept", e.status, str(ex)[:120])
            continue
        E.loc[i, "last_error"] = ""
        if str(e.status).startswith("scar") and r["status"] in ("waiting", "no_pre"):
            E.loc[i, "last_checked"] = today.isoformat()   # no new clear image: keep the scar we have
            continue
        if r["status"] in ("waiting", "no_pre") and age > GIVE_UP_DAYS:
            r["status"] = "no_clear_image"
        g = r.pop("geometry", None)
        for k, v in r.items():
            if k not in ("lat", "lon", "date", "sensor"):
                E.loc[i, k] = v
        E.loc[i, "last_checked"] = today.isoformat()
        if g:
            feats = [f for f in feats if f["properties"]["event_id"] != e.event_id]
            feats.append({"type": "Feature", "geometry": g,
                          "properties": {"event_id": e.event_id, **{k: v for k, v in r.items() if np.isscalar(v)}}})
        print(e.event_id, r["status"], r.get("scar_ha", ""))
    if len(E):  # forest beat of each event (all 8,973 MP Forest Department beats)
        b = gpd.read_file("/mnt/project-files/ratapani/beats/mp_beats.geojson").to_crs(4326)
        pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(E.longitude.astype(float), E.latitude.astype(float)), crs=4326, index=E.index)
        j = gpd.sjoin(pts, b[["beat_uid", "Division", "Range", "Beat", "geometry"]], how="left", predicate="within")
        j = j[~j.index.duplicated()]
        E[["beat_uid", "division", "range", "beat"]] = j[["beat_uid", "Division", "Range", "Beat"]].values
    E.to_csv(fe, index=False)
    old.to_csv(fa, index=False)   # written with the events, so a crash never marks alerts seen without their event
    json.dump({"type": "FeatureCollection", "features": feats}, open(fg, "w"))
    print("alerts", len(old), "events", len(E), E.status.value_counts().to_dict() if len(E) else {})


if __name__ == "__main__":
    main(*sys.argv[1:3])
