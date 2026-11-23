"""Active-fire pixels in every Sentinel-2 and Landsat 8/9 scene over Ratapani (Planetary Computer, 20 m grid of
the season scar maps). A fire burning at overpass (~10:30-10:45 IST) dates the scar under it to the exact day,
including small fires VIIRS never reports.

Rules (surface reflectance; the papers use TOA, close enough for this hot-pixel test):
  Sentinel-2 (Gui et al. 2026, step 1): (B12-B8A)/(B12+B8A) > 0.5  and  -0.05 < B8A-B4 < 0.15, plus B12 > 0.10
  Landsat (same test on SWIR2/NIR/red), or Schroeder et al. 2016 unambiguous: B7/B5 > 2.5, B7-B5 > 0.3, B7 > 0.5
Only WorldCover tree/shrub/grass pixels. Pixels firing on > 4 dates over all seasons are fixed sources (Gui step 4)
and are dropped later in af_link.py. No cloud mask: hot pixels often get flagged as cloud/saturated.

Usage: python af_scan.py <season> [threads]   -> out/af/af_<season>.csv
"""
import os, sys, datetime as dt, warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling

warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts")
import fetch  # TR, W, H, INSIDE, WORLDCOVER, AOI

os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
                  GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2")
OUT = "/mnt/project-files/fire-alert-scars/out/af/"
B = {"s2": dict(red="B04", nir="B8A", swir1="B11", swir2="B12"),
     "ls": dict(red="red", nir="nir08", swir1="swir16", swir2="swir22")}
ELIG = np.zeros(fetch.INSIDE.shape, bool)
ELIG[fetch.INSIDE] = np.isin(np.load(fetch.WORLDCOVER), (10, 20, 30))


def read(href):
    for k in range(4):
        try:
            with rasterio.open(href) as src, WarpedVRT(src, crs=fetch.CRS, transform=fetch.TR, width=fetch.W,
                                                       height=fetch.H, resampling=Resampling.nearest,
                                                       src_nodata=src.nodata) as v:
                return v.read(1).astype(np.float32)
        except Exception as e:
            err = e
    raise err


def scene(it, sensor):
    it = pc.sign(it)
    r = {}
    for k, a in B[sensor].items():
        x = read(it.assets[a].href)
        if sensor == "s2":
            off = 1000 if float(it.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
            r[k] = np.where(x > 0, (x - off) / 10000.0, np.nan)
        else:
            r[k] = np.where(x > 0, x * 0.0000275 - 0.2, np.nan)
    with np.errstate(all="ignore"):
        ndfi = (r["swir2"] - r["nir"]) / (r["swir2"] + r["nir"])
        dnr = r["nir"] - r["red"]
        fire = (ndfi > 0.5) & (dnr > -0.05) & (dnr < 0.15) & (r["swir2"] > 0.10)
        if sensor == "ls":
            fire |= (r["swir2"] / r["nir"] > 2.5) & (r["swir2"] - r["nir"] > 0.3) & (r["swir2"] > 0.5)
    fire &= ELIG
    rr, cc = np.where(fire)
    return pd.DataFrame(dict(row=rr, col=cc, swir2=r["swir2"][rr, cc].round(3), swir1=r["swir1"][rr, cc].round(3),
                             nir=r["nir"][rr, cc].round(3), ndfi=ndfi[rr, cc].round(3)))


def main(season, threads=6):
    os.makedirs(OUT, exist_ok=True)
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    import geopandas as gpd
    geom = gpd.read_file(fetch.AOI).to_crs(4326).union_all().__geo_interface__
    rng = f"{season - 1}-12-01/{season}-06-20"
    jobs = []
    for col, s in (("sentinel-2-l2a", "s2"), ("landsat-c2-l2", "ls")):
        q = {"eo:cloud_cover": {"lt": 80}}
        if s == "ls":
            q["platform"] = {"in": ["landsat-8", "landsat-9"]}
        jobs += [(it, s) for it in cat.search(collections=[col], intersects=geom, datetime=rng, query=q).items()]

    def one(j):
        it, s = j
        try:
            d = scene(it, s)
        except Exception as e:
            print("fail", it.id, str(e)[:80], flush=True)
            return None
        d["date"], d["sensor"], d["scene"] = it.datetime.date().isoformat(), s, it.id
        d["time_utc"] = it.datetime.strftime("%H:%M")
        return d

    with ThreadPoolExecutor(threads) as ex:
        res = [d for d in ex.map(one, jobs) if d is not None]
    D = pd.concat(res, ignore_index=True) if res else pd.DataFrame()
    if len(D):
        x, y = rasterio.transform.xy(fetch.TR, D.row.values, D.col.values)
        from pyproj import Transformer
        D["lon"], D["lat"] = Transformer.from_crs(fetch.CRS, "EPSG:4326", always_xy=True).transform(x, y)
        D = D.drop_duplicates(["date", "row", "col"])
    D.to_csv(OUT + f"af_{season}.csv", index=False)
    print(season, "scenes", len(jobs), "af pixels", len(D), "dates", D.date.nunique() if len(D) else 0, flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), *(int(a) for a in sys.argv[2:3]))
