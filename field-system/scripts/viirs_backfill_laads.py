"""Backfill VIIRS fire points for MP from NASA's per-granule fire files (VNP14IMG / VJ114IMG / VJ214IMG collection 2, LP DAAC,
Earthdata secret via the proxy), for months the FIRMS archive copy in fire-alert-scars/alerts_mp lacks (it holds Jan-Jun only).
Usage: python viirs_backfill_laads.py 2025-10-01 2025-12-31 out.csv
Writes FIRMS-style columns (latitude, longitude, acq_date, acq_time = granule start UTC, satellite N/1/2, confidence l/n/h, frp,
daynight, type). FIRMS 'type' is not in the granules: a point within 200 m of a past FIRMS type-2 (static land source) point is
type 2, else 0. Check on 1-3 Mar 2025 vs the FIRMS archive: 96.4% of its type-0 fire square-days found, 99.3% of ours are in it."""
import io, sys, json, time, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

BB = "74,21,82.9,26.9"
PRODS = {"VNP14IMG": "N", "VJ114IMG": "1", "VJ214IMG": "2"}
CONF = {7: "l", 8: "n", 9: "h"}
ARCH = Path("/mnt/project-files/fire-alert-scars/alerts_mp")


def get(url, tries=5):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return r.read()
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))


def granules(prod, d0, d1):
    out, page = [], 1
    while True:
        u = (f"https://cmr.earthdata.nasa.gov/search/granules.json?short_name={prod}&version=002&bounding_box={BB}"
             f"&temporal={d0}T00:00:00Z,{d1}T23:59:59Z&page_size=2000&page_num={page}")
        e = json.loads(get(u))["feed"]["entry"]
        out += [l["href"] for g in e for l in g["links"] if l["href"].startswith("https://data.lpdaac") and l["href"].endswith(".nc")]
        if len(e) < 2000:
            return out
        page += 1


def points(href, sat):
    import h5py
    f = h5py.File(io.BytesIO(get(href)), "r")
    if "FP_latitude" not in f or len(f["FP_latitude"]) == 0:
        return None
    t = pd.Timestamp(f.attrs["PGE_StartTime"].decode() if isinstance(f.attrs["PGE_StartTime"], bytes) else str(f.attrs["PGE_StartTime"]))
    lat, lon = f["FP_latitude"][:], f["FP_longitude"][:]
    ok = (lon >= 74) & (lon <= 82.9) & (lat >= 21) & (lat <= 26.9)
    if not ok.any():
        return None
    return pd.DataFrame({"latitude": lat[ok], "longitude": lon[ok], "acq_date": t.strftime("%Y-%m-%d"), "acq_time": t.hour * 100 + t.minute,
                         "satellite": sat, "instrument": "VIIRS", "confidence": [CONF.get(int(c), "n") for c in f["FP_confidence"][:][ok]],
                         "frp": f["FP_power"][:][ok], "daynight": np.where(f["FP_day"][:][ok] == 1, "D", "N")})


def main(d0, d1, out):
    fr = []
    for prod, sat in PRODS.items():
        hs = granules(prod, d0, d1)
        print(prod, len(hs), "granules", flush=True)
        for i, h in enumerate(hs):
            p = points(h, sat)
            if p is not None:
                fr.append(p)
            if i % 100 == 0:
                print(" ", prod, i, flush=True)
    v = pd.concat(fr, ignore_index=True)
    from scipy.spatial import cKDTree
    from pyproj import Transformer
    tf = Transformer.from_crs(4326, 32643, always_xy=True).transform
    st = pd.concat([pd.read_csv(f, usecols=["latitude", "longitude", "type"]) for f in ARCH.glob("viirs-*.csv")])
    st = st[st.type == 2].drop_duplicates()
    tree = cKDTree(np.c_[tf(st.longitude.values, st.latitude.values)])
    d, _ = tree.query(np.c_[tf(v.longitude.values, v.latitude.values)], distance_upper_bound=200)
    v["type"] = np.where(np.isfinite(d), 2, 0)
    v.to_csv(out, index=False)
    print("points", len(v), "type0", int((v.type == 0).sum()), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
