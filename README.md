# JwalaNetra / VanAagni — MP Forest Fire Early-Warning System

> Daily operational fire-risk prediction for **Madhya Pradesh state** — 87 forest
> divisions, 8,973 beats, ~94,000 km² forested area. Production model **v17.5**
> (LightGBM + Hawkes self-excitation + hurdle-blend re-ranker) pipes into a
> forest-officer portal with per-division coverage floor, field-response loop,
> and 2026-season backtested honest metrics.

**Production status** (2026-04-23):
- **v17.5 model** — v17_ba_pu × hurdle Stage A geometric blend (weight 0.7)
- **Coverage floor** live since 2026-04-22 (each of 87 divisions gets ≥1 CRITICAL; 2 in extreme weather)
- **2026 season backtest** (66 days): **45.5% unique-event recall**, 3.2% CRITICAL precision, median 2.3 km spatial offset, +3d temporal lead-time — directional offset is **random noise, not a correctable bias**
- CI: `test_operational_pipeline.py` 23/23 + `ci_static_ops_checks.py` 23/23 on every commit

For project-internal notes, development conventions, and the full list of
confirmed dead-ends (VLM, CLIP, S2 dNBR, Dynamic World LULC, PS-1 SAR) see
[`CLAUDE.md`](CLAUDE.md). For the latest 2026 season report see
[`outputs/validation_reports/2026_SEASON_REPORT.md`](outputs/validation_reports/2026_SEASON_REPORT.md).

---

## Architecture

```
                    ┌──────────────────┐
                    │  FIRMS VIIRS     │  (1.35 M MP detections
                    │  + MODIS         │   2014-2026, forest-clipped)
                    └────────┬─────────┘
                             │
                             ▼
        Hawkes self-excitation (74 % feature gain)
                             │
  ┌──────────────┐           │          ┌────────────────────┐
  │ Open-Meteo   │──▶ FWI ───┤          │ v8 base features   │
  │ (live + arch)│           │          │ (LULC, terrain,    │
  └──────────────┘           │          │  NDVI, anthropo)   │
                             │          └──────────┬─────────┘
                             ▼                     │
                   ┌───────────────────┐           │
                   │ v17 LightGBM      │◀──────────┘
                   │ (111 features)    │
                   └─────────┬─────────┘
                             │
                             ▼
                   ┌───────────────────┐
                   │ Hurdle Stage-A    │  geo-mean blend
                   │ × v17 re-ranker   │  (weight 0.7)
                   └─────────┬─────────┘
                             ▼
        ┌──────────────────────────────────────────┐
        │ Banding: CRITICAL / ALERT / WATCH        │
        │ + rolling-window rank calibration        │
        └─────────────┬────────────────────────────┘
                      ▼
        ┌──────────────────────────────────────────┐
        │ Operational alerts (build_op_alerts.py)  │
        │  • Trust tiers: HIGH / MEDIUM /          │
        │    COLD_START / DIVISION_FLOOR           │
        │  • Per-division coverage floor           │
        │  • Budget caps + weather/calendar banner │
        └─────────────┬────────────────────────────┘
                      ▼
        ┌──────────────────────────────────────────┐
        │ v3 Portal (dashboard/v3/serve.py, :8790) │
        │  Live Map + Divisions + Model Card +     │
        │  Validation + VIIRS + Season backtest    │
        └──────────────────────────────────────────┘
```

## Quickstart

```bash
# 1. One-off daily fire alert (runs the whole pipeline)
python scripts/daily_fire_alert.py

# 2. Or run the steps individually:
python scripts/predict_ignition_v17.py --use-hurdle-blend        # v17.5 model pass
python scripts/build_operational_alerts.py                       # decorate + coverage floor

# 3. Portal (forest-officer UI)
python dashboard/v3/serve.py                                     # opens on :8790
# then → http://localhost:8790/v3/

# 4. Regression gates (run on every commit via .github/workflows/ci.yml)
python scripts/ci_static_ops_checks.py                           # 23 static checks
python scripts/test_operational_pipeline.py                      # 23 portal + schema checks

# 5. Season-long backtest + report
python scripts/run_2026_backfill.py --execute                    # backfill 66 days (~3 min)
python scripts/validate_2026_season.py                           # compute metrics
python scripts/generate_2026_season_report.py                    # emit MD report
```

## Directory layout

| Path | Purpose |
|---|---|
| `src/analysis/` | Fire dynamics, smoke dispersion, burn estimator, prescriptive engine (25 files) |
| `src/data/` | FIRMS / Open-Meteo / GEE / EarthAccess ingestion (8 files) |
| `src/inference/` | Alert detection, severity classification, quantization (6 files) |
| `src/model/` | Prithvi, VanAagni DL, ROS-UNet architectures (14 files) |
| `src/train/` | Training loops for LightGBM, VanAagni, ROS-UNet (12 files) |
| `scripts/` | 170+ operational/utility scripts — see `docs/SCRIPTS_INDEX.md` |
| `dashboard/v3/` | **Production portal** (single-file vanilla JS, MapLibre 5.6) |
| `data_lake/` | Parquet/GeoJSON archive (FIRMS, FWI, beats, training patches) |
| `outputs/dashboard_feed/` | Latest + dated v17 predictions & operational alerts JSON |
| `outputs/predictive_fire_risk/predictive_v17_ba_pu/` | Production LightGBM model + calibration |
| `outputs/validation_reports/` | 2026 season backtest (summary.json + per-fire.csv + MD report) |
| `models/ignition/` | Trained LightGBM checkpoints |
| `tests/` | pytest suite (test_api, test_cell2fire_*, test_spread_predictor, ...) |
| `docs/` | ARCHITECTURE, SCRIPTS_INDEX, audits/ (dead-end post-mortems) |

## Key scripts (production)

| Script | Role |
|---|---|
| `scripts/daily_fire_alert.py` | End-to-end daily orchestrator (FWI → v17 → ops alerts → diagnostics) |
| `scripts/predict_ignition_v17.py` | v17.5 inference with `--use-hurdle-blend` (default in production) |
| `scripts/build_operational_alerts.py` | Trust-tier decoration + per-division coverage floor |
| `scripts/run_2026_backfill.py` | Parallel backfill of dated predictions + ops alerts |
| `scripts/validate_2026_season.py` | Full-season backtest (spatial + temporal + directional offset) |
| `scripts/generate_2026_season_report.py` | Emits `2026_SEASON_REPORT.md` (operator-readable) |
| `scripts/test_operational_pipeline.py` | 23-check regression harness (portal endpoints + schema + CI) |
| `scripts/ci_static_ops_checks.py` | 23-check static harness (compile + --help + wiring) |
| `dashboard/v3/serve.py` | Portal HTTP server (single-file Python stdlib) |

## Results — 2026 fire season

Per [`outputs/validation_reports/2026_SEASON_REPORT.md`](outputs/validation_reports/2026_SEASON_REPORT.md):

| Metric | Value |
|---|---:|
| Window | 2026-02-16 → 2026-04-22 (66 days) |
| Unique ignition events (forest-clipped) | 833 |
| **Unique-event recall (any banded alert)** | **45.5 %** |
| Unique-event recall (CRITICAL only) | 10.8 % |
| Statewide CRITICAL precision (FIRMS-only, 7-day window) | 3.2 % |
| HIGH-trust precision | 11.1 % |
| MEDIUM-trust precision | 12.5 % |
| COLD_START precision | 2.9 % |
| DIVISION_FLOOR precision | 1.7 % (caught 64 events otherwise silent) |
| Median spatial offset (caught events) | 2.30 km |
| Median temporal lead-time | +3 days |
| Directional bias significant at 95 % CI? | **No — random 2-D noise** |

## Tech stack

- **Python 3.12**, PyTorch 2.4.1 + torch-directml, LightGBM 4.6, scikit-learn 1.8
- **MapLibre GL JS 5.6** + NASA SRTM terrarium DEM (globe + 3D terrain opt-ins)
- **Open-Meteo** (live + archive weather, free, no key)
- **FIRMS VIIRS/MODIS** NRT + SP (NASA)
- **Google Earth Engine** (`van-suraksha-alert` project — satellite pipeline)
- **Prithvi-EO-2.0 300M / 600M** — frozen, used for embeddings only
- **GeoPandas + Shapely** — forest-beat spatial joins (`mp_beats_wgs84.geojson`, 8,973 polygons)

## Confirmed dead-ends (do NOT re-attempt)

All documented in `docs/audits/` with experimental evidence:

| Experiment | Result |
|---|---|
| VLM zero-shot on S2 chips (LLaVA-7b) | Image-agnostic; MW p=0.74 |
| CLIP-ViT-L/14 embeddings + classifier | ROC 0.562, perm p=0.095 |
| Temporal NDVI/BSI deltas | 5-fold ROC 0.539 |
| Hybrid Bayesian ranking (adaptive λ) | All variants worse than statewide |
| Dynamic World LULC at 2 km cells | Model ignored it (1/30 top features) |
| Sentinel-1 SAR amplitude | ρ ≈ 0.01, p > 0.3 |
| GDELT article geocoding | 0 % village-level yield |
| Prithvi-BurnScars US-pretrained transfer | Median F1 0.013 on MP |

The structural finding: 77 % of new ignitions happen in "cold-start" (no nearby
fires) regime where Hawkes self-excitation provides zero signal. Visual precursor
hypothesis (anthropogenic ground-clearing visible pre-ignition) is **comprehensively
falsified** across three independent feature extraction methods. **v17 is at the
information-theoretic ceiling for satellite + weather features alone.** Closing
the gap requires non-satellite data (patrol reports, NTFP schedules, mobile phone
density near forest fringes — see `docs/research/path_c_pilot_finding.md`).

## Development

```bash
# Install deps (NB: most are NOT version-pinned, see follow-up todo)
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt

# Run tests
pytest tests/                                          # unit tests
python scripts/ci_static_ops_checks.py                 # 23 static checks
python scripts/test_operational_pipeline.py            # 23 portal + schema checks

# Lint / type-check
python -m ruff check src/ scripts/
python -m pyright src/
```

## Links

- **Deep project notes:** [`CLAUDE.md`](CLAUDE.md) — authoritative working doc
- **System architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Script index:** [`docs/SCRIPTS_INDEX.md`](docs/SCRIPTS_INDEX.md)
- **Dead-end audits:** [`docs/audits/`](docs/audits/)
- **2026 season validation:** [`outputs/validation_reports/2026_SEASON_REPORT.md`](outputs/validation_reports/2026_SEASON_REPORT.md)

## License

Research + operational use for the Madhya Pradesh Forest Department. No public
distribution of FIRMS NRT credentials or Open-Meteo keys. Model weights in
`outputs/predictive_fire_risk/predictive_v17_ba_pu/model.txt` are LightGBM text
format, freely reproducible from the training pipeline.
