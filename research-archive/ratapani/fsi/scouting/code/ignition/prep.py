"""Assemble, for every event scar, the satellite fire detections that could belong to it.

Inputs (read only):
  fire-alert-scars/event_scars.geojson         one scar polygon per event (pre_date, post_date)
  fire-alert-scars/alerts/*.csv                raw FIRMS points (MODIS, S-NPP, NOAA-20, NOAA-21) with scan/track
  fire-alert-scars/out/af/af_pixels_clean.csv  Sentinel-2 / Landsat 20-30 m fire pixels (~10:45 IST)
Out (scratch):
  prep/scars.pkl   GeoDataFrame in EPSG:32643 with window times
  prep/dets.pkl    all detections in UTM with footprint half-sizes and UTC time
  prep/passes.pkl  catalogue of satellite passes over the box (any detection in the bbox = a pass happened)
  prep/links.pkl   (scar index, detection index) pairs: footprint intersects scar and time in (pre, post]
Usage: python -I prep.py <outdir>
"""
import sys, os, glob
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import box
from pyproj import Transformer

R = "/mnt/project-files/fire-alert-scars/"
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
TO = Transformer.from_crs(4326, 32643, always_xy=True)
IMG_UTC_H = 5.25  # S2 / Landsat look at ~05:15 UTC (10:45 IST)


def load_firms():
    rows = []
    for f in sorted(glob.glob(R + "alerts/*.csv")):
        name = os.path.basename(f)
        sensor = name.rsplit("_", 1)[0]
        try:
            d = pd.read_csv(f, dtype={"acq_time": str})
        except Exception:
            continue
        if "latitude" not in d.columns or len(d) == 0:
            continue
        d["sensor"] = sensor
        rows.append(d)
    d = pd.concat(rows, ignore_index=True)
    d = d[d.acq_time.notna()].copy()
    d["acq_time"] = d.acq_time.str.zfill(4)
    d["t"] = pd.to_datetime(d.acq_date + " " + d.acq_time.str[:2] + ":" + d.acq_time.str[2:], utc=True)
    # 2026 Earth Engine rows lack scan/track: use typical values
    viirs = d.sensor.str.startswith("viirs")
    d["scan"] = pd.to_numeric(d.scan, errors="coerce").fillna(pd.Series(np.where(viirs, 0.45, 1.2), index=d.index))
    d["track"] = pd.to_numeric(d.track, errors="coerce").fillna(pd.Series(np.where(viirs, 0.42, 1.1), index=d.index))
    # half footprint in metres (scan ~ E-W, track ~ N-S for a sun-synchronous polar orbit at 23 N)
    d["hx"] = d.scan * 500.0
    d["hy"] = d.track * 500.0
    d = d.drop_duplicates(["latitude", "longitude", "t", "sensor"])
    d["type"] = pd.to_numeric(d.get("type"), errors="coerce")
    d = d[(d.type.isna()) | (d.type == 0)]
    d["src"] = "firms"
    return d[["sensor", "latitude", "longitude", "t", "hx", "hy", "frp", "confidence", "daynight", "src"]]


def load_af():
    a = pd.read_csv(R + "out/af/af_pixels_clean.csv")
    a["t"] = pd.to_datetime(a.date + " " + a.time_utc, utc=True)
    half = np.where(a.sensor == "s2", 10.0, 15.0)
    a = a.rename(columns={"lat": "latitude", "lon": "longitude"})
    a["sensor"] = "af-" + a.sensor
    a["hx"] = half; a["hy"] = half
    a["frp"] = np.nan; a["confidence"] = ""; a["daynight"] = "D"; a["src"] = "af"
    return a[["sensor", "latitude", "longitude", "t", "hx", "hy", "frp", "confidence", "daynight", "src"]]


def main():
    F = load_firms()
    A = load_af()
    D = pd.concat([F, A], ignore_index=True)
    D["x"], D["y"] = TO.transform(D.longitude.values, D.latitude.values)
    D = D.reset_index(drop=True)
    # pass catalogue: FIRMS detections of one sensor within 20 min = one pass
    P = []
    for s, g in F.groupby("sensor"):
        ts = np.sort(g.t.values.astype("datetime64[m]").astype(np.int64))
        brk = np.r_[True, np.diff(ts) > 20]
        grp = np.cumsum(brk)
        tt = pd.Series(ts).groupby(grp).median()
        P.append(pd.DataFrame(dict(sensor=s, t=pd.to_datetime(tt.values, unit="m", utc=True))))
    P = pd.concat(P, ignore_index=True)
    S = gpd.read_file(R + "event_scars.geojson").to_crs(32643)
    S = S[S.geometry.notna() & ~S.geometry.is_empty].reset_index(drop=True)
    S["t_pre"] = pd.to_datetime(S.pre_date, utc=True) + pd.Timedelta(hours=IMG_UTC_H)
    S["t_post"] = pd.to_datetime(S.post_date, utc=True) + pd.Timedelta(hours=IMG_UTC_H)
    # spatial join of footprint rectangles with scars
    fp = gpd.GeoDataFrame(D[["t"]].copy(), geometry=[box(x - a, y - b, x + a, y + b)
                          for x, y, a, b in zip(D.x, D.y, D.hx, D.hy)], crs=32643)
    J = gpd.sjoin(fp, S[["geometry", "t_pre", "t_post"]], predicate="intersects", how="inner")
    J = J[(J.t > J.t_pre) & (J.t <= J.t_post)]
    links = pd.DataFrame(dict(scar=J.index_right.values, det=J.index.values))
    S.to_pickle(OUT + "/scars.pkl"); D.to_pickle(OUT + "/dets.pkl"); P.to_pickle(OUT + "/passes.pkl")
    links.to_pickle(OUT + "/links.pkl")
    n = links.groupby("scar").size()
    print("scars", len(S), "dets", len(D), "passes", len(P), "links", len(links))
    print("detections per scar:", n.describe().round(1).to_dict(), "scars with 0:", len(S) - len(n))
    print(P.sensor.value_counts().to_dict())


if __name__ == "__main__":
    main()
