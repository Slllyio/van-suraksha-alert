"""Earth Engine pulls for one MP division grid (adapted from the Ratapani ee_export.py).
Usage: python mp_ee.py <division_dir> <step> [...]
steps: alphaearth modis lst era5 era5_06 static weathernext. Resumable: finished files/parts are skipped."""
import sys, time, json
from pathlib import Path
import ee
import pandas as pd
import geopandas as gpd

ROOT = Path(sys.argv[1])
OUT = ROOT / "ee"
PARTS = OUT / "_parts"
PARTS.mkdir(parents=True, exist_ok=True)
MODIS_CRS = "SR-ORG:6974"

ee.Initialize(project="van-suraksha-alert")

grid = gpd.read_file(ROOT / "grid_500m.geojson")[["cell_id", "geometry"]]
_aoi = gpd.read_file(ROOT / "aoi.geojson")
_aoi["geometry"] = _aoi.geometry.simplify(0.002).buffer(0)  # ~200 m tolerance keeps EE request payloads small
aoi_geom = ee.Geometry(json.loads(_aoi.to_json())["features"][0]["geometry"])


def fc_for(df):
    return ee.FeatureCollection(json.loads(df.to_json(drop_id=True)))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get(obj, tries=4):
    for k in range(tries):
        try:
            return obj.getInfo()
        except ee.EEException as e:
            msg = str(e).lower()
            if k == tries - 1 or "timed out" in msg or "memory" in msg or "too many" in msg or "too large" in msg:
                raise
            log("retry", k + 1, str(e)[:120])
            time.sleep(5 * 2 ** k)


def reduce_cells(img, scale, crs=None, batch=500, reducer=None):
    """reduceRegions over the grid in batches; halves the batch on timeout/memory errors."""
    reducer = reducer or ee.Reducer.mean()
    rows, i = [], 0
    while i < len(grid):
        sub = grid.iloc[i:i + batch]
        res = img.reduceRegions(collection=fc_for(sub), reducer=reducer, scale=scale, crs=crs, tileScale=4)
        res = res.map(lambda f: ee.Feature(None, f.toDictionary()))
        try:
            feats = get(res)["features"]
        except ee.EEException as e:
            if batch <= 25:
                raise
            batch //= 2
            log("shrinking batch to", batch, str(e)[:100])
            continue
        rows += [f["properties"] for f in feats]
        i += len(sub)
    return pd.DataFrame(rows)


def alphaearth():
    for y in range(2017, 2025):
        f = OUT / f"alphaearth_{y}.csv"
        if f.exists():
            continue
        img = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
               .filterDate(f"{y}-01-01", f"{y + 1}-01-01").filterBounds(aoi_geom).mosaic())
        df = reduce_cells(img, 10, "EPSG:32643", batch=500)
        cols = ["cell_id"] + [f"A{k:02d}" for k in range(64)]
        df.reindex(columns=cols).sort_values("cell_id").to_csv(f, index=False)
        log("wrote", f.name, len(df))


def years():
    return [("2012-10-01", "2013-01-01")] + [(f"{y}-01-01", f"{y + 1}-01-01") for y in range(2013, 2025)]


def melt_stack(df, names):
    """toBands columns '<YYYY_MM_DD>_<var>' -> long table (date, cell_id, var...)."""
    long = df.melt(id_vars="cell_id", var_name="k", value_name="v")
    long["date"] = pd.to_datetime(long["k"].str[:10], format="%Y_%m_%d").dt.date
    long["var"] = long["k"].str[11:]
    out = long.pivot_table(index=["date", "cell_id"], columns="var", values="v", dropna=False).reset_index()
    return out.reindex(columns=["date", "cell_id"] + names)


def modis_series(name, coll_id, prep, names, scale):
    final = OUT / name
    if final.exists():
        return
    parts = []
    for a, b in years():
        p = PARTS / f"{final.stem}_{a[:4]}{a[5:7]}.csv"
        if not p.exists():
            col = ee.ImageCollection(coll_id).filterDate(a, b).map(prep)
            df = reduce_cells(col.toBands(), scale, MODIS_CRS, batch=1000)
            melt_stack(df, names).to_csv(p, index=False)
            log("part", p.name, len(df))
        parts.append(pd.read_csv(p))
    out = pd.concat(parts).sort_values(["date", "cell_id"])
    out.to_csv(final, index=False)
    log("wrote", final.name, len(out))


def prep_sr(img):
    qa = img.select("StateQA")
    clear = qa.bitwiseAnd(3).eq(0).And(qa.rightShift(2).bitwiseAnd(1).eq(0))  # cloud state clear, no shadow
    b1, b2, b6 = [img.select(f"sur_refl_b0{k}").multiply(1e-4) for k in (1, 2, 6)]
    ndvi = b2.subtract(b1).divide(b2.add(b1)).rename("ndvi")
    ndmi = b2.subtract(b6).divide(b2.add(b6)).rename("ndmi")
    return ndvi.addBands(ndmi).updateMask(clear).copyProperties(img, ["system:time_start"])


def prep_lst(img):
    return img.select("LST_Day_1km").multiply(0.02).rename("lst_k").copyProperties(img, ["system:time_start"])


def aoi_series(name, col, bands, scale=11132):
    final = OUT / name
    if final.exists():
        return
    parts = []
    for a, b in years():
        p = PARTS / f"{final.stem}_{a[:4]}{a[5:7]}.csv"
        if not p.exists():
            c = col.filterDate(a, b).select(bands)
            fc = c.map(lambda im: ee.Feature(None, im.reduceRegion(ee.Reducer.mean(), aoi_geom, scale))
                       .set("time", im.date().format("YYYY-MM-dd'T'HH:mm")))
            df = pd.DataFrame([f["properties"] for f in get(fc)["features"]])
            df.reindex(columns=["time"] + bands).to_csv(p, index=False)
            log("part", p.name, len(df))
        parts.append(pd.read_csv(p))
    out = pd.concat(parts).sort_values("time")
    out.to_csv(final, index=False)
    log("wrote", final.name, len(out))


ERA_BANDS = ["temperature_2m", "dewpoint_temperature_2m", "u_component_of_wind_10m",
             "v_component_of_wind_10m", "volumetric_soil_water_layer_1"]


def era5():
    aoi_series("era5land_daily.csv", ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR"),
               ["temperature_2m_max"] + ERA_BANDS + ["total_precipitation_sum"])


def era5_06():
    col = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY").filter(ee.Filter.calendarRange(6, 6, "hour"))
    aoi_series("era5land_06utc.csv", col, ERA_BANDS + ["total_precipitation"])


def static():
    f = OUT / "terrain.csv"
    if not f.exists():
        dem = ee.Image("USGS/SRTMGL1_003").select("elevation")
        img = dem.rename("elev_m").addBands(ee.Terrain.slope(dem).rename("slope_deg"))
        red = ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
        df = reduce_cells(img, 30, "EPSG:32643", reducer=red, batch=1000)
        df.reindex(columns=["cell_id", "elev_m_mean", "elev_m_stdDev", "slope_deg_mean", "slope_deg_stdDev"]) \
          .sort_values("cell_id").to_csv(f, index=False)
        log("wrote", f.name, len(df))
    f = OUT / "worldcover.csv"
    if not f.exists():
        wc = ee.ImageCollection("ESA/WorldCover/v200").first()
        classes = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        img = ee.Image.cat([wc.eq(c).rename(f"wc_{c}") for c in classes])
        df = reduce_cells(img, 10, "EPSG:32643", batch=500)
        df.reindex(columns=["cell_id"] + [f"wc_{c}" for c in classes]).sort_values("cell_id").to_csv(f, index=False)
        log("wrote", f.name, len(df))
    f = OUT / "population.csv"
    if not f.exists():
        pop = ee.Image("JRC/GHSL/P2023A/GHS_POP/2020").select("population_count")
        red = ee.Reducer.mean().combine(ee.Reducer.sum(), sharedInputs=True)
        df = reduce_cells(pop, 100, pop.projection(), reducer=red, batch=1000)
        df = df.rename(columns={"mean": "pop_mean_per_100m", "sum": "pop_sum"})
        df.reindex(columns=["cell_id", "pop_mean_per_100m", "pop_sum"]).sort_values("cell_id").to_csv(f, index=False)
        log("wrote", f.name, len(df))


def weathernext():
    lines = []
    for name in ["weathernext_3_0_0_0p1deg", "weathernext_2_0_0"]:
        path = f"projects/gcp-public-data-weathernext/assets/{name}"
        try:
            c = ee.ImageCollection(path)
            info = get(ee.Dictionary({
                "n": c.size(),
                "first": c.aggregate_min("system:time_start"),
                "last": c.aggregate_max("system:time_start"),
                "props": c.first().propertyNames(),
                "bands": c.first().bandNames(),
            }))
            fmt = lambda ms: pd.to_datetime(ms, unit="ms", utc=True).isoformat() if ms else None
            lines.append(f"{path}: ACCESS OK, images={info['n']}, first={fmt(info['first'])}, last={fmt(info['last'])}")
            lines.append(f"  props={info['props']}")
            lines.append(f"  bands={info['bands']}")
        except Exception as e:
            lines.append(f"{path}: FAILED {type(e).__name__}: {str(e)[:300]}")
    (OUT / "weathernext_probe.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


STEPS = {
    "alphaearth": alphaearth,
    "modis": lambda: modis_series("modis_ndvi_ndmi.csv", "MODIS/061/MOD09A1", prep_sr, ["ndvi", "ndmi"], 463.3127),
    "lst": lambda: modis_series("modis_lst.csv", "MODIS/061/MOD11A2", prep_lst, ["lst_k"], 926.6254),
    "era5": era5, "era5_06": era5_06, "static": static, "weathernext": weathernext,
}

if __name__ == "__main__":
    for s in sys.argv[2:]:
        log("start", s)
        STEPS[s]()
        log("done", s)
