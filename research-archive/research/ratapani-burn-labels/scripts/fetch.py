"""Fetch clear-sky Sentinel-2 L2A and Landsat 8/9 C2 L2 observations over Ratapani.

Each observation date is reprojected to one 20 m grid (EPSG:32643) and saved as
int16 reflectance x 10000 for red, nir, swir1, swir2 on AOI pixels only.
Usage: python fetch.py <year> <outdir> [bg]   (season = Dec 1 of year-1 to Jun 20 of year;
       "bg" adds blue and green for dates already fetched; "six" fetches all 6 Prithvi bands)
Set RATAPANI_AOI to the AOI geojson path when running outside the project container.
"""
import os, sys, json, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import numpy as np, geopandas as gpd, rasterio, planetary_computer as pc, pystac_client
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from scipy.ndimage import binary_dilation

os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
                  GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="TRUE")
HERE = os.path.dirname(os.path.abspath(__file__))
AOI = os.environ.get("RATAPANI_AOI", "/mnt/project-files/ratapani/ratapani_aoi.geojson")
WORLDCOVER = os.environ.get("RATAPANI_WORLDCOVER", os.path.join(HERE, "..", "data", "worldcover.npy"))
CRS, RES = "EPSG:32643", 20.0


def grid():
    a = gpd.read_file(AOI).to_crs(CRS)
    x0, y0, x1, y1 = a.total_bounds
    x0, y0 = np.floor(x0 / RES) * RES - 200, np.floor(y0 / RES) * RES - 200
    x1, y1 = np.ceil(x1 / RES) * RES + 200, np.ceil(y1 / RES) * RES + 200
    w, h = int((x1 - x0) / RES), int((y1 - y0) / RES)
    tr = rasterio.transform.from_origin(x0, y1, RES, RES)
    inside = ~geometry_mask(a.geometry, (h, w), tr)
    return tr, w, h, inside


TR, W, H, INSIDE = grid()
BANDS = {"s2": dict(blue="B02", green="B03", red="B04", nir="B8A", swir1="B11", swir2="B12", qa="SCL"),
         "ls": dict(blue="blue", green="green", red="red", nir="nir08", swir1="swir16", swir2="swir22", qa="qa_pixel")}
KEYS = ("red", "nir", "swir1", "swir2")  # "bg" mode fetches ("blue", "green") into bg/*_bg.npz


def read(href, resamp):
    for attempt in range(4):
        try:
            with rasterio.open(href) as src, WarpedVRT(src, crs=CRS, transform=TR, width=W, height=H,
                                                       resampling=resamp, src_nodata=src.nodata) as v:
                return v.read(1)
        except Exception as e:
            err = e
    raise err


def obs_for(items, sensor, keys=KEYS):
    """Mosaic all tiles/scenes of one date; return dict of AOI-pixel int16 arrays + valid mask."""
    b = BANDS[sensor]
    out = {k: np.zeros(INSIDE.sum(), np.int16) for k in keys}
    valid = np.zeros(INSIDE.sum(), bool)
    for it in items:
        it = pc.sign(it)
        qa2 = read(it.assets[b["qa"]].href, Resampling.nearest)
        if sensor == "s2":
            # Sen2Cor often labels fresh burn scars as dark area (2) or cloud shadow (3);
            # keep those unless a cloud (8, 9, 10) lies within ~1 km.
            cloud = binary_dilation(np.isin(qa2, [8, 9, 10]), iterations=50)
            ok2 = np.isin(qa2, [2, 4, 5, 6, 7]) | (qa2 == 3)
            ok2 &= ~cloud
        else:
            cloud = (qa2 & (1 << 1) > 0) | (qa2 & (1 << 3) > 0) | (qa2 & (1 << 4) > 0)
            cloud = binary_dilation(cloud, iterations=17)
            ok2 = (qa2 > 0) & (qa2 & 1 == 0) & ~cloud
        ok = ok2[INSIDE]
        new = ok & ~valid
        if not new.any():
            continue
        with ThreadPoolExecutor(4) as ex:
            arrs = dict(zip(keys, ex.map(
                lambda k: read(it.assets[b[k]].href, Resampling.bilinear)[INSIDE].astype(np.float32), keys)))
        for k, a in arrs.items():
            if sensor == "s2":
                off = 1000 if float(it.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
                r = (a - off) / 10000.0
            else:
                r = a * 0.0000275 - 0.2
            out[k][new] = np.clip(r[new] * 10000, -1000, 15000).astype(np.int16)
        valid |= new
    return out, valid


def main(year, outdir, mode="core"):
    # core: 4 bands for detect.py; bg: blue+green beside existing core files; six: all 6 bands in one file
    keys, suffix = {"core": (KEYS, ""), "bg": (("blue", "green"), "_bg"), "six": (("blue", "green") + KEYS, "")}[mode]
    os.makedirs(outdir, exist_ok=True)
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    a = gpd.read_file(AOI)
    geom = json.loads(a.to_json())["features"][0]["geometry"] if len(a) == 1 else a.unary_union.__geo_interface__
    rng = f"{year-1}-12-01/{year}-06-20"
    groups = {}
    for col, sensor in (("sentinel-2-l2a", "s2"), ("landsat-c2-l2", "ls")):
        q = {"eo:cloud_cover": {"lt": 60}}
        if sensor == "ls":
            q["platform"] = {"in": ["landsat-8", "landsat-9"]}
        for it in cat.search(collections=[col], intersects=geom, datetime=rng, query=q).items():
            d = it.datetime.date().isoformat()
            groups.setdefault((d, sensor), []).append(it)
    log = []
    for (d, sensor), items in sorted(groups.items()):
        # bg files go in a bg/ subfolder so the other scripts' *.npz globs don't pick them up
        fn = os.path.join(outdir, "bg" if suffix else "", f"{d}_{sensor}{suffix}.npz")
        if os.path.exists(fn) or (suffix and not os.path.exists(os.path.join(outdir, f"{d}_{sensor}.npz"))):
            continue
        try:
            o, valid = obs_for(items, sensor, keys)
        except Exception as e:
            log.append(f"{d} {sensor} FAILED {e}")
            continue
        frac = valid.mean()
        log.append(f"{d} {sensor} tiles={len(items)} clear={frac:.2f}")
        if frac < 0.05:
            continue
        if suffix:
            np.savez_compressed(fn, **o)  # same valid mask as the core file
        else:
            np.savez_compressed(fn, valid=valid, **o)
        print(log[-1], flush=True)
    with open(os.path.join(outdir, f"fetch_log{suffix}.txt"), "a") as f:
        f.write("\n".join(log) + "\n")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], *sys.argv[3:4])
