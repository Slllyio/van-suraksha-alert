"""ERA5-Land hourly at native 0.1 deg points over Ratapani (+10 km), Dec-Jun seasons 2017..2026 -> CSV per season."""
import ee, json, sys, time, pandas as pd
ee.Initialize(project="van-suraksha-alert")
gj = json.load(open(r"E:\FIRE\ratapani_burn\data\ratapani_aoi.geojson"))
geoms = [ee.Geometry(f["geometry"]) for f in gj["features"]]
aoi = ee.FeatureCollection([ee.Feature(g) for g in geoms]).geometry().buffer(10000)
BANDS = ["temperature_2m", "dewpoint_temperature_2m", "u_component_of_wind_10m", "v_component_of_wind_10m",
         "total_precipitation_hourly", "volumetric_soil_water_layer_1", "surface_solar_radiation_downwards_hourly"]
ic = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY").select(BANDS)
for y in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
    out = rf"E:\FIRE\ratapani\ee\era5\era5land_hourly_{y}.csv"
    frames = []
    # one month per request keeps getRegion under its row limit
    for m0, m1 in [(f"{y-1}-12-01", f"{y}-01-01"), (f"{y}-01-01", f"{y}-02-01"), (f"{y}-02-01", f"{y}-03-01"),
                   (f"{y}-03-01", f"{y}-04-01"), (f"{y}-04-01", f"{y}-05-01"), (f"{y}-05-01", f"{y}-06-01"), (f"{y}-06-01", f"{y}-07-01")]:
        for attempt in range(4):
            try:
                rows = ic.filterDate(m0, m1).getRegion(aoi, 11132).getInfo(); break
            except Exception as e:
                print("retry", m0, e, flush=True); time.sleep(10 * (attempt + 1))
        df = pd.DataFrame(rows[1:], columns=rows[0]); frames.append(df)
        print(y, m0, len(df), flush=True)
    df = pd.concat(frames)
    df["datetime_utc"] = pd.to_datetime(df.time, unit="ms")
    df = df.drop(columns=["id", "time"])
    df["point_id"] = df.groupby(["longitude", "latitude"]).ngroup()
    df.to_csv(out, index=False)
    print("wrote", out, len(df), "points", df.point_id.nunique(), flush=True)
