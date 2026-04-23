# Copernicus CDS ERA5 ingest — setup + troubleshooting

The Copernicus Climate Data Store (CDS) serves the full ECMWF ERA5 reanalysis
product line. For the JwalaNetra v17.5 fire-weather enrichment we use it to
unfreeze 6 of the 7 still-stale `wx_*` columns (`wx_dtr`, `wx_lst`,
`wx_lst_7d_max`, `wx_lst_air_diff`, `wx_srad`, `wx_srad_7d`) — the LST and
solar-radiation variables are not served by Open-Meteo.

Script: [`scripts/ingest_era5_cds.py`](../scripts/ingest_era5_cds.py)

## One-time setup (5 minutes)

### 1. Register a free account

→ https://cds.climate.copernicus.eu/

The CDS is free for research + operational use. Commercial use has separate terms.

### 2. Copy your API key

After login → **Profile** (top-right icon) → **API key** section.
You'll see:

```
url: https://cds.climate.copernicus.eu/api
key: 12345:abc1234e-56fg-7890-12hi-3456789jkl01
       ────  ──────────────────────────────────
        UID                  API key
```

### 3. Create `~/.cdsapirc`

```bash
# ~/.cdsapirc  (on Windows: C:\Users\<you>\.cdsapirc)
url: https://cds.climate.copernicus.eu/api
key: 12345:abc1234e-56fg-7890-12hi-3456789jkl01
```

Alternative: set environment variables `CDSAPI_URL` + `CDSAPI_KEY` (the script
checks these too).

### 4. Accept the ERA5-Land Terms of Use (one-time — REQUIRED)

→ https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=download#manage-licences

Scroll to the **"Manage licences"** section, accept all listed licences
(ECMWF, Copernicus products), then click **"Accept"**. Your account is
now authorised for subsequent API calls.

**If you skip this step the ingest script fails with:**
```
HTTPError: 403 Client Error: Forbidden … required licences not accepted
```
Re-visit the licence page above and accept.

## Run

```bash
# Default window: 2024-01 through current month (~28 monthly requests)
python scripts/ingest_era5_cds.py

# Custom window
python scripts/ingest_era5_cds.py --start 2025-01 --end 2026-04

# Keep NetCDF files after parsing (useful for debugging)
python scripts/ingest_era5_cds.py --keep-netcdf
```

Each monthly request takes ~30 seconds – 5 minutes depending on CDS queue
depth. Full 28-month window typically 30-60 minutes total.

## Output

`data_lake/fire_weather/era5_cds_per_cell_daily.parquet`

Schema: one row per (cell_id, date) with these per-cell fields populated
from the nearest ERA5-Land 0.1° grid cell:

| Column | Meaning |
|---|---|
| `temp_2m_max`, `temp_2m_min` | Daily 2m air temperature (°C) extremes |
| `dtr` | Diurnal temperature range = temp_2m_max − temp_2m_min |
| `skin_temp_max` | Daily max skin temperature (°C) — our LST proxy |
| `srad_mj` | Daily accumulated shortwave radiation (MJ/m²) |
| `skin_temp_7d_max` | Rolling 7-day max of skin_temp |
| `srad_7d` | Rolling 7-day mean of srad_mj |
| `lst_air_diff` | skin_temp_max − temp_2m_max (surface heating proxy) |

## How predict_ignition_v17.py uses it

`apply_live_weather_overrides()` (in `scripts/predict_ignition_v17.py`)
already expects this parquet at the path above. Once it lands, a new
**Stage 1e (ERA5-CDS per-cell)** override activates automatically — no
code change. The per-prediction JSON output will carry an `era5_cds_stage`
metadata block alongside the existing fwi/soil/beat stages.

**Note:** the predict script's current `era5_stage` code looks for the
*per-division* parquet at `era5_per_division_daily.parquet` (from the
Open-Meteo ingest). The CDS parquet is per-cell and at a different path;
the override logic needs a small extension to read both. Until that lands,
run `scripts/ingest_era5_cds.py` and the output is ready to be consumed —
the wiring on the predict side is a follow-up commit.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `HTTPError: 401 Unauthorized` | Re-check `~/.cdsapirc` UID:key formatting (colon-separated). |
| `Queue jobs still pending, please wait...` | Normal. CDS queues requests; wait 1-5 min. |
| `Exception: the request you have submitted is not valid` | Double-check date range (ERA5 has a 2-5 day lag for most-recent data). |
| Terms-of-use error | Visit the dataset page once and accept. |
| `cdsapi` import fails | `pip install cdsapi xarray netCDF4` |

## Why CDS over Open-Meteo for this project

| Dimension | Open-Meteo Archive | Copernicus CDS |
|---|---|---|
| Cost | Free | Free |
| Rate-limit | ~30 calls/min/IP (aggressive) | Queue-based, no per-minute cap |
| Resolution | ~11 km | 9 km (ERA5-Land) |
| Variables | ~20 daily aggregates | Full ERA5 variable set (100+) incl. LST, skin_temp, soil, radiation, fluxes |
| Auth | None | Free account + API key |
| Payload | Compact JSON per point | Gridded NetCDF/GRIB |
| Right tool for | Quick point-queries | Gridded bulk ingest |

For our use-case (MP-wide gridded ingest, 87 division centroids or 42K
cell centroids), CDS wins on rate-limit + variable coverage. Open-Meteo
was picked first because it needs no auth and is zero-setup — but it
blocks at rate limits hard.
