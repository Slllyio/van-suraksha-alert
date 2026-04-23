"""Ingest ERA5-Land daily gridded weather from the Copernicus CDS API.

Fills the 7 wx_* columns that remain frozen after the Open-Meteo fallback:
  wx_dtr          (daily temp range — from 2m_temperature hourly min/max)
  wx_lst          (skin_temperature daily max)
  wx_lst_7d_max   (rolling 7d max of skin_temperature)
  wx_lst_air_diff (skin_temperature - 2m_temperature)
  wx_srad         (surface_solar_radiation_downwards daily sum in MJ/m²)
  wx_srad_7d      (rolling 7d mean of srad)

Higher quality than Open-Meteo for this project:
  * Official ECMWF reanalysis — 9 km resolution (ERA5-Land vs Open-Meteo ~11 km)
  * No aggressive per-minute rate-limits (CDS uses async job queue)
  * One monthly NetCDF request covers all MP + all variables

Output: data_lake/fire_weather/era5_cds_per_cell_daily.parquet
  Schema (per cell × date):
    cell_id, date, lat, lon,
    temp_2m_max, temp_2m_min, dtr,
    skin_temp_max,
    srad_mj,
    -- rolling (7d):
    skin_temp_7d_max, srad_7d, lst_air_diff

== Setup (one-time) ==

1. Register (free) at https://cds.climate.copernicus.eu/
2. Profile -> "API key" -> copy UID + key
3. Create ~/.cdsapirc:
     url: https://cds.climate.copernicus.eu/api
     key: <UID>:<API-KEY>
   OR set env vars CDSAPI_URL + CDSAPI_KEY
4. Accept Terms of Use for "ERA5-Land hourly data" and
   "ERA5-Land post-processed daily" on the CDS site (one-time).

Then:
  python scripts/ingest_era5_cds.py
  python scripts/ingest_era5_cds.py --start 2024-01 --end 2026-04

Each month fetches ~10-30 MB NetCDF, processes to ~5 MB parquet rows.
Full window (28 months) takes 20-60 minutes depending on queue depth.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
CELLS_CSV = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_DIR = ROOT / "data_lake" / "fire_weather"
OUT_PATH = OUT_DIR / "era5_cds_per_cell_daily.parquet"
TMP_DIR = ROOT / "tmp" / "era5_cds"

# MP bbox [N, W, S, E] (CDS area format — north, west, south, east)
MP_AREA = [27.0, 74.0, 21.0, 83.0]

# ERA5-Land hourly variables we need
# (from https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-land)
CDS_VARIABLES = [
    "2m_temperature",
    "skin_temperature",
    "surface_solar_radiation_downwards",
]


def _check_credentials() -> tuple[bool, str]:
    """Return (available, message) for CDS API credentials."""
    rc_path = Path.home() / ".cdsapirc"
    if rc_path.exists():
        return True, f"using {rc_path}"
    url = os.environ.get("CDSAPI_URL")
    key = os.environ.get("CDSAPI_KEY")
    if url and key:
        return True, f"using env vars CDSAPI_URL + CDSAPI_KEY (prefix {key[:8]}…)"
    return False, (
        "NO CREDENTIALS FOUND. Register at https://cds.climate.copernicus.eu/, "
        "then create ~/.cdsapirc with:\n"
        "    url: https://cds.climate.copernicus.eu/api\n"
        "    key: <UID>:<API-KEY>\n"
        "OR set env vars CDSAPI_URL + CDSAPI_KEY."
    )


def month_range(start: str, end: str) -> list[tuple[str, str]]:
    """Return list of (YYYY, MM) strings in [start_month, end_month]."""
    import pandas as pd
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    out = []
    cur = s
    while cur <= e:
        out.append((str(cur.year), f"{cur.month:02d}"))
        cur = cur + 1
    return out


def fetch_month_netcdf(client, year: str, month: str, out_nc: Path) -> bool:
    """Submit CDS request for one month of ERA5-Land hourly data for MP."""
    if out_nc.exists():
        log.info("  %s-%s already downloaded, skipping", year, month)
        return True
    out_nc.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
        days_in_month = pd.Period(f"{year}-{month}", freq="M").days_in_month
        days = [f"{d:02d}" for d in range(1, days_in_month + 1)]
        log.info("  Submitting CDS request for %s-%s (%d days)...", year, month, len(days))
        client.retrieve(
            "reanalysis-era5-land",
            {
                "variable": CDS_VARIABLES,
                "year": year,
                "month": month,
                "day": days,
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": MP_AREA,
                "format": "netcdf",
            },
            str(out_nc),
        )
        return True
    except Exception as exc:
        log.error("  %s-%s CDS fetch failed: %s", year, month, exc)
        if out_nc.exists():
            out_nc.unlink()
        return False


def netcdf_to_daily_df(nc_path: Path) -> "pd.DataFrame | None":
    """Parse a monthly NetCDF, aggregate hourly -> daily per grid cell."""
    import pandas as pd
    try:
        import xarray as xr
    except ImportError:
        log.error("xarray not installed: pip install xarray netCDF4")
        return None
    try:
        ds = xr.open_dataset(nc_path)
    except Exception as exc:
        log.error("  failed to open %s: %s", nc_path.name, exc)
        return None

    # ERA5 names variables slightly differently depending on the run
    var_map = {}
    for name in ("t2m", "tas", "2t"):
        if name in ds.data_vars:
            var_map["t2m"] = name
            break
    for name in ("skt", "slk"):
        if name in ds.data_vars:
            var_map["skt"] = name
            break
    for name in ("ssrd",):
        if name in ds.data_vars:
            var_map["ssrd"] = name
            break

    if not var_map:
        log.warning("  %s: no expected variables found; data_vars = %s",
                    nc_path.name, list(ds.data_vars))
        ds.close()
        return None

    # Determine the time dimension name (ERA5 uses 'valid_time' in new format)
    time_dim = next((d for d in ("valid_time", "time") if d in ds.dims), None)
    if time_dim is None:
        log.warning("  %s: no time dim found", nc_path.name)
        ds.close()
        return None

    # Kelvin -> °C for temperature variables; J/m² -> MJ/m² for srad
    if "t2m" in var_map:
        ds[var_map["t2m"]] = ds[var_map["t2m"]] - 273.15
    if "skt" in var_map:
        ds[var_map["skt"]] = ds[var_map["skt"]] - 273.15

    # Daily aggregates
    daily = xr.Dataset()
    if "t2m" in var_map:
        daily["temp_2m_max"] = ds[var_map["t2m"]].resample({time_dim: "1D"}).max()
        daily["temp_2m_min"] = ds[var_map["t2m"]].resample({time_dim: "1D"}).min()
    if "skt" in var_map:
        daily["skin_temp_max"] = ds[var_map["skt"]].resample({time_dim: "1D"}).max()
    if "ssrd" in var_map:
        # ERA5 SSRD is accumulated J/m²; we want daily SUM in MJ/m² => divide by 1e6
        daily["srad_mj"] = ds[var_map["ssrd"]].resample({time_dim: "1D"}).sum() / 1e6

    # Convert to long DataFrame
    df = daily.to_dataframe().reset_index()
    # Rename time column to "date"
    if time_dim in df.columns:
        df = df.rename(columns={time_dim: "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    # Normalise lat/lon column names
    if "latitude" in df.columns:
        df = df.rename(columns={"latitude": "lat"})
    if "longitude" in df.columns:
        df = df.rename(columns={"longitude": "lon"})
    ds.close()
    return df


def sample_to_cells(grid_df: "pd.DataFrame", cells_df: "pd.DataFrame") -> "pd.DataFrame":
    """For each (date, cell), look up nearest ERA5 grid point."""
    import numpy as np
    import pandas as pd

    # Build a (lat, lon) -> index map on the unique grid
    grid_unique = grid_df[["lat", "lon"]].drop_duplicates().reset_index(drop=True)
    grid_lats = grid_unique["lat"].to_numpy()
    grid_lons = grid_unique["lon"].to_numpy()

    # For each cell find nearest ERA5 grid point index
    cell_lats = cells_df["centroid_lat"].to_numpy()
    cell_lons = cells_df["centroid_lon"].to_numpy()
    nearest_idx = np.zeros(len(cells_df), dtype=np.int32)
    for i in range(len(cells_df)):
        dlat = grid_lats - cell_lats[i]
        dlon = grid_lons - cell_lons[i]
        nearest_idx[i] = int(np.argmin(dlat * dlat + dlon * dlon))
    cells_df = cells_df.copy()
    cells_df["_grid_lat"] = grid_lats[nearest_idx]
    cells_df["_grid_lon"] = grid_lons[nearest_idx]

    # JOIN cells with grid on nearest (lat, lon) across all dates
    merged = cells_df[["cell_id", "_grid_lat", "_grid_lon"]].merge(
        grid_df, left_on=["_grid_lat", "_grid_lon"],
        right_on=["lat", "lon"], how="inner",
    )
    merged["dtr"] = merged.get("temp_2m_max") - merged.get("temp_2m_min")
    if "skin_temp_max" in merged.columns and "temp_2m_max" in merged.columns:
        merged["lst_air_diff"] = merged["skin_temp_max"] - merged["temp_2m_max"]
    return merged.drop(columns=["_grid_lat", "_grid_lon", "lat", "lon"])


def add_rolling(df: "pd.DataFrame") -> "pd.DataFrame":
    import pandas as pd
    df = df.sort_values(["cell_id", "date"]).reset_index(drop=True)
    g = df.groupby("cell_id", group_keys=False)
    if "skin_temp_max" in df.columns:
        df["skin_temp_7d_max"] = g["skin_temp_max"].apply(lambda s: s.rolling(7, min_periods=1).max())
    if "srad_mj" in df.columns:
        df["srad_7d"] = g["srad_mj"].apply(lambda s: s.rolling(7, min_periods=1).mean())
    return df


def main() -> int:
    import pandas as pd

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01", help="YYYY-MM first month")
    ap.add_argument("--end", default=None, help="YYYY-MM last month (default: current)")
    ap.add_argument("--keep-netcdf", action="store_true", help="Don't delete NetCDFs after parsing")
    args = ap.parse_args()

    # Credential check
    ok, msg = _check_credentials()
    if not ok:
        log.error("CDS API credentials missing.\n%s", msg)
        return 2
    log.info("CDS credentials: %s", msg)

    try:
        import cdsapi
    except ImportError:
        log.error("cdsapi not installed: pip install cdsapi")
        return 2

    try:
        import xarray  # noqa: F401
    except ImportError:
        log.error("xarray not installed: pip install xarray netCDF4 cfgrib")
        return 2

    client = cdsapi.Client(quiet=True)

    end_month = args.end or pd.Timestamp.now().strftime("%Y-%m")
    months = month_range(args.start, end_month)
    log.info("Window: %s -> %s (%d months)", args.start, end_month, len(months))

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    all_dfs = []
    for yr, mo in months:
        nc_path = TMP_DIR / f"era5_land_{yr}-{mo}_mp.nc"
        if not fetch_month_netcdf(client, yr, mo, nc_path):
            continue
        df = netcdf_to_daily_df(nc_path)
        if df is not None:
            all_dfs.append(df)
        if not args.keep_netcdf:
            nc_path.unlink(missing_ok=True)

    if not all_dfs:
        log.error("No data fetched.")
        return 1

    grid_df = pd.concat(all_dfs, ignore_index=True)
    log.info("Combined grid rows: %d", len(grid_df))

    log.info("Loading cell centroids...")
    cells = pd.read_csv(CELLS_CSV)
    log.info("  %d cells", len(cells))

    log.info("Sampling ERA5 grid at each cell centroid (nearest-neighbour)...")
    cell_df = sample_to_cells(grid_df, cells)
    log.info("  %d (cell, date) rows", len(cell_df))

    log.info("Computing rolling stats (7d max LST, 7d mean srad)...")
    cell_df = add_rolling(cell_df)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cell_df.to_parquet(OUT_PATH, index=False)
    log.info("Wrote %s (%d rows, %d cols)", OUT_PATH.relative_to(ROOT),
             len(cell_df), len(cell_df.columns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
