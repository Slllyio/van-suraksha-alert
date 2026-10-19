"""Same-day weather from GFS (NOAA/GFS0P25) for every MP division, Oct-Jun 2018-19 .. 2025-26.
For IST day D: the 00Z run of D (out by ~10:00 IST on D), forecast hours 3..24 (3-hourly) ->
  t_mean, t_max (deg C), rh_mean (%), wind_mean (m/s), prcp (mm; sum of the 6-hourly buckets at hours 6/12/18/24).
Division means. Output E:/FIRE/mp/gfs/gfs_daily.csv (division, date, ...), monthly parts in E:/FIRE/mp/gfs/parts/."""
import time
from pathlib import Path
import geopandas as gpd
import ee
import pandas as pd

ee.Initialize(project="van-suraksha-alert")
MP = Path(r"E:\FIRE\mp"); OUT = MP / "gfs"; PARTS = OUT / "parts"; PARTS.mkdir(parents=True, exist_ok=True)
feats = []
for p in sorted(MP.glob("*/aoi.geojson")):
    geom = gpd.read_file(p).geometry.union_all().convex_hull   # outlines have thousands of parts; GFS cells are ~28 km
    feats.append(ee.Feature(ee.Geometry(geom.__geo_interface__), {"division": p.parent.name}))
DIVS = ee.FeatureCollection(feats)
GFS = ee.ImageCollection("NOAA/GFS0P25")
H3 = list(range(3, 25, 3))


def day_image(d):
    d = ee.Date(d)
    run = GFS.filterDate(d, d.advance(1, "hour"))
    met = run.filter(ee.Filter.inList("forecast_hours", H3))
    t = met.select("temperature_2m_above_ground")
    u, v = met.select("u_component_of_wind_10m_above_ground"), met.select("v_component_of_wind_10m_above_ground")
    wind = met.map(lambda i: i.expression("hypot(u, v)", {"u": i.select("u_component_of_wind_10m_above_ground"),
                                                       "v": i.select("v_component_of_wind_10m_above_ground")}))
    pr = run.filter(ee.Filter.inList("forecast_hours", [6, 12, 18, 24])).select("total_precipitation_surface").sum()
    img = ee.Image.cat(t.mean().rename("t_mean"), t.max().rename("t_max"),
                       met.select("relative_humidity_2m_above_ground").mean().rename("rh_mean"),
                       wind.mean().rename("wind_mean"), pr.rename("prcp"))
    return img.set("date", d.format("YYYY-MM-dd"))


def chunk(d0):
    f = PARTS / f"{d0:%Y%m%d}.csv"
    if f.exists():
        return
    days = ee.List([str(d.date()) for d in pd.date_range(d0, periods=STEP)])

    def one(d):                                   # server-side loop: the division geometries are sent once
        img = day_image(d)
        return img.reduceRegions(DIVS, ee.Reducer.mean(), 27830).map(
            lambda x: x.set("date", img.get("date")).setGeometry(None))
    for k in range(6):                            # 429 "too many concurrent aggregations": back off and retry
        try:
            rows = ee.FeatureCollection(days.map(one)).flatten().getInfo()["features"]; break
        except ee.EEException as e:
            if "no bands" in str(e):                 # a day without a GFS run: fetch day by day, skip empty days
                rows = []
                for d in pd.date_range(d0, periods=STEP):
                    try:
                        rows += ee.FeatureCollection(ee.List([str(d.date())]).map(one)).flatten().getInfo()["features"]
                    except ee.EEException:
                        print("no GFS run", d.date(), flush=True)
                break
            if k == 5:
                print("FAILED", f.name, str(e)[:100], flush=True); return
            time.sleep(30 * (k + 1))
    df = pd.DataFrame([r["properties"] for r in rows])
    df.to_csv(f, index=False)
    print(f.name, len(df), flush=True)


STEP = 5          # 5 days per request, one request at a time (larger requests hit "too many concurrent aggregations")
starts = [d for y in range(2018, 2026) for d in pd.date_range(f"{y}-10-01", f"{y + 1}-06-30", freq=f"{STEP}D")]
for d0 in starts:
    chunk(d0)
allx = pd.concat([pd.read_csv(f) for f in sorted(PARTS.glob("*.csv"))], ignore_index=True)
allx.to_csv(OUT / "gfs_daily.csv", index=False)
print(allx.shape, allx.isna().mean().round(3).to_dict())
