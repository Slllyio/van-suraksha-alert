"""The fire history the live models saw, as MP-grid cell-days: one row per (IST date, row, col) with >= 1 VIIRS type-0
detection, 2013-12-01 .. 2026-06-30, from the same archives as the 2026 feature tables (S-NPP consolidated, NOAA-20/21
Oct-May 2018-24, S-NPP/NOAA-20/NOAA-21 SP Oct 2024 - May 2026). Out: E:/FIRE/mp/pc_models/fire_celldays.parquet"""
import numpy as np
import pandas as pd
import geopandas as gpd

SOURCES = [r"E:\FIRE\data_lake\fire_detections\firms_mp_viirs\firms_mp_consolidated.parquet",
           r"E:\FIRE\mp\firms_noaa\firms_noaa_mp.parquet", r"E:\FIRE\mp\firms_fwd\firms_fwd_mp.parquet"]
X0, Y1, S = 399000.0, 2996000.0, 500.0


def to_celldays(v: pd.DataFrame) -> pd.DataFrame:
    """FIRMS rows (latitude, longitude, acq_date, acq_time, type) -> unique (date, row, col), type 0 only, IST date."""
    v = v[v.type == 0]
    xy = gpd.GeoSeries(gpd.points_from_xy(v.longitude, v.latitude), crs=4326).to_crs(32643)
    col = np.floor((xy.x.to_numpy() - X0) / S).astype(np.int32)
    row = np.floor((Y1 - xy.y.to_numpy()) / S).astype(np.int32)
    utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m")
    date = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize().to_numpy()
    return pd.DataFrame({"date": date, "row": row, "col": col}).drop_duplicates()


if __name__ == "__main__":
    v = pd.concat([pd.read_parquet(p, columns=["latitude", "longitude", "acq_date", "acq_time", "type"]) for p in SOURCES],
                  ignore_index=True)
    c = to_celldays(v)
    c = c[(c.date >= "2013-12-01") & (c.date <= "2026-06-30")].sort_values(["date", "row", "col"]).reset_index(drop=True)
    c.to_parquet(r"E:\FIRE\mp\pc_models\fire_celldays.parquet", index=False, compression="zstd")
    print(len(c), c.date.min(), c.date.max())
