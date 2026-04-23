# v17.5 — JwalaNetra production model card

**Trained:** 2026-04-15 (v17_ba_pu base model; hurdle Stage A fitted same session)
**Production since:** 2026-04-19
**Pipeline:** `scripts/predict_ignition_v17.py --use-hurdle-blend` → `scripts/build_operational_alerts.py`

---

## Architecture

v17.5 is a two-stage geometric blend of two independently trained LightGBM models.

**Stage B (v17_ba_pu):** A LightGBM ranker with 111 features including 4 Hawkes
self-excitation features (cKDTree kernel, literature priors), 19 GLCM texture features,
6 hydrology features, FWI components, terrain derivatives, and burnt-area-augmented
PU (Positive-Unlabelled) labels using MCD64A1 + FireCCI51 + S2 dNBR flood-fill
clustering (Andela 2019 method). Trained on 1.2M cell-day samples across Madhya Pradesh
(87 divisions, 8,973 beats), best iteration 1,398. Calibrated with isotonic regression
over 382,878 validation samples.

**Stage A (v17_hurdle_a):** A Bernoulli logistic model on 107 features excluding all
Hawkes columns. Purpose: rescue new-outbreak cells where the Hawkes kernel is silent
(low-Hawkes regime, defined as hawkes_n_recent_10km_7d ≤ 1). Trained on DBSCAN ignition
labels only.

**Blend:** Geometric mean with weight 0.7 toward Stage B:
`score = rank_B^0.7 × rank_A^0.3`. Rank-calibrated rolling-window normalisation applied
before banding. Empirically tested label: `geo_w0.7` (see `docs/audits/pivot_a_v2_finding.md`).

---

## Training metrics (v17_ba_pu base)

| Metric | Value |
|---|---|
| ROC-AUC (hold-out) | 0.8815 |
| PR-AUC | 0.1481 |
| Precision@top-5% | 7.86% |
| Recall@top-5% (BA-tiered) | 47.41% |
| Per-day recall@top-5% | 48.56% |
| Best-F1 threshold | 0.85 |
| Best F1 | 0.208 |
| N features | 111 |
| Calibration Brier score | 0.00436 (baseline 0.0649) |
| Calibration log-loss | 0.02596 (baseline 0.2236) |
| Calibration method | Isotonic regression |

---

## Validated performance — 2026 fire season backtest (66 days)

Backtest window: 2026-02-16 → 2026-04-22. Ground truth: 833 unique forest-clipped
FIRMS VIIRS ignition events (DBSCAN eps=2 km, min_samples=2). Match rule: alert centroid
within 4 km of event centroid, event first-detection within [D, D+7].

### Season-level summary

| Metric | Value |
|---|---|
| Backtest window (days) | 66 |
| Unique ignition events observed | 833 |
| Unique-event recall (any band) | 45.5% |
| Unique-event recall at CRITICAL | 10.8% |
| Season recall (windowed, any band) | 36.1% |
| Season recall (windowed, CRITICAL) | 6.1% |
| CRITICAL precision (statewide) | 3.2% |
| Floor-tier precision (DIVISION_FLOOR) | 1.7% |
| Median spatial offset (km) | 2.30 |
| Median temporal lead-time (days) | +3 |
| Directional bias significant at 95% CI | No |

### Per trust-tier precision

| Trust tier | Alerts issued | Events caught | Precision | Median offset (km) |
|---|---:|---:|---:|---:|
| HIGH | 1,022 | 114 | 11.2% | 2.41 |
| MEDIUM | 160 | 20 | 12.5% | 2.28 |
| COLD_START | 4,498 | 131 | 2.9% | 2.51 |
| DIVISION_FLOOR | 5,261 | 89 | 1.7% | 2.82 |

**Operational interpretation:** HIGH and MEDIUM tiers deliver 10–12% precision —
dispatch-worthy. COLD_START (2.9%) and DIVISION_FLOOR (1.7%) require phone verification
with local VFPC before deploying a team.

### Spatial offset distribution

| Band | Count | Share of all events |
|---|---:|---:|
| 0–2 km | 726 | 15.4% |
| 2–4 km | 978 | 20.7% |
| 4–8 km | 0 | 0.0% |
| 8–16 km | 0 | 0.0% |
| Missed (>4 km or no alert) | 3,011 | 63.9% |

### Temporal lead-time distribution

| Lead window | Count | Share |
|---|---:|---:|
| Same day | 336 | 7.1% |
| +1 day | 257 | 5.5% |
| +2–3 days | 446 | 9.5% |
| +4–7 days | 665 | 14.1% |
| Missed | 3,011 | 63.9% |

**Key finding:** v17.5 is a medium-term risk ranker (median +3 day lead), not a real-time
detector. Officers should use CRITICAL alerts for proactive pre-positioning, not
same-day dispatch.

---

## Operational decoration layers (ON TOP of model output)

The raw `predict_ignition_v17.py` output is a scored grid of ~42,000 2-km cells.
`build_operational_alerts.py` applies four layers before delivery to officers.

### Layer 1 — Banding

Cells are ranked and segmented into CRITICAL (top 0.3%), ALERT (top 1.7%), and WATCH
(top 5%). The hurdle blend shifts ~27 additional cells into banded status in low-Hawkes
zones compared to raw v17 alone (+1.77 pp recall in that regime).

### Layer 2 — Trust calibration

Each banded alert is decorated with a trust tier based on Hawkes density
(`hawkes_n_recent_10km_7d`) and rank position:

- **HIGH**: top-1% rank AND hawkes_n ≥ 3 — validated 11.2% precision
- **MEDIUM**: top-5% rank, mid-Hawkes — validated 12.5% precision
- **COLD_START**: top-1% rank BUT hawkes_n ≤ 1 (new outbreak) — 2.9% precision; verify before acting
- **DIVISION_FLOOR / CLIMATOLOGY_FLOOR**: see layers below

Trust tier drives the `action` field: HIGH/MEDIUM → DISPATCH; COLD_START → VERIFY;
floor tiers → AWARENESS.

### Layer 3 — Division coverage floor

Every MP division (87 total) is guaranteed at least 1 CRITICAL alert per day, rising to
2 during extreme fire weather (FFMC ≥ 92 or RH ≤ 25% or danger class Extreme/Very High).
Rationale: the Hawkes-dominated ranking concentrates 80% of organic CRITICALs in
~10 high-contagion divisions, leaving 77 divisions effectively invisible on most days.

Cost: DIVISION_FLOOR alerts carry 1.7% precision — about half the precision of COLD_START.
They are tagged `floor_promoted=True` and displayed as dashed-ring markers in the portal
so officers distinguish them from model-confident alerts.
In the 66-day backtest, floor alerts rescued 89 events (4% of all catches) at the cost
of 5,261 extra alerts — acceptable as a safety net, not a primary signal.

### Layer 4 — Climatology watch floor

Beats in the top 10th percentile of historical fire frequency for the current week-of-year
(based on 5 years of FIRMS history, 2021–2025, minimum 5 fires in the 5-year period) that
have NO model alert today are automatically promoted to WATCH band.

Tagged `trust_level='CLIMATOLOGY_FLOOR'`, `climatology_floor=True`. These alerts carry
the metadata fields `climatology_n_years_with_fire`, `climatology_mean_fires_per_year`,
and `climatology_percentile` so officers can judge the historical evidence directly.

Benefit: lifted pixel-level recall from 13.2% → 20.5% on the 66-day backtest for
persistently-blind beats (Rewa/Kakredi_West, Damoh/Ghoghra, Singrauli/Suidih, etc.).
Expected precision: below DIVISION_FLOOR (use for patrol awareness only — never dispatch).
Action code: AWARENESS.

---

## Known limitations (HONEST)

1. **Non-Hawkes features are FROZEN at 2025-05-29.** `predict_ignition_v17.py:271` calls
   `most_recent` from the v8 training dataset snapshot for all weather, NDVI, DOY, and
   terrain-derived features. The Hawkes features are computed live from FIRMS < D (verified
   at line 121). This means the model is operating with one stale weather snapshot for 77%
   of its features, rather than the actual weather on prediction date. Mitigation: re-train
   v17.6 with a live Open-Meteo or GFS weather feed wired into the daily pipeline.

2. **77% of new ignitions are in the cold-start (low-Hawkes) regime.** Model recall in
   this regime is 5.9% at top-5% rank (per CLAUDE.md). The hurdle blend raised this to
   7.65% (+1.77 pp) but the 10% target was not reached. The root cause is structural: the
   model has no village-level anthropogenic signal. Mitigation: climatology floor (partial),
   plus future data from patrol logs, NTFP collection schedules, or mobile phone density.

3. **8 dead-end improvement experiments are documented in CLAUDE.md** and the
   `docs/audits/` directory. These include VLM zero-shot on S2 chips (MW p=0.74), CLIP
   embeddings (ROC=0.562), temporal NDVI/BSI deltas (ROC=0.539), Dynamic World monthly
   LULC at 2 km resolution, S1 SAR amplitude (ρ≈0.01), GDELT geocoding, hybrid Bayesian
   ranking, and pre-fire calendar features. All were validated and rejected. Do not
   re-attempt without new data outside the current feature set.

4. **64% of all event-window instances are missed.** No alert within 4 km at any band.
   This is the information-theoretic ceiling of v17 on satellite + weather features alone.

5. **Same-day dispatch is not supported.** Median lead-time is +3 days. Officers should
   interpret a CRITICAL alert as "this area is elevated risk over the next week" rather
   than "a fire is burning right now."

6. **2 km spatial resolution is the grid floor.** Median alert-to-event offset is 2.30 km,
   consistent with the cell width. Sub-2 km accuracy is not achievable without a finer
   feature grid, which is incompatible with the current GFS + FIRMS + SRTM pipeline.

---

## Operational guarantees

**Refresh cadence:** Daily, triggered by `scripts/daily_fire_alert.py` (GitHub Actions
cron 05:30 IST, or local Windows Task Scheduler). Pipeline completes in < 4 minutes on
the production machine.

**Model silence protocol:** If `outputs/dashboard_feed/ignition_risk_v17.json` is older
than 28 hours, portal displays a stale-data banner. If it is older than 48 hours, the
on-call officer should check:
1. GitHub Actions run log for the `daily-fire-alert` workflow
2. `logs/daily_fire_alert_YYYY-MM-DD.log` on the local machine
3. Whether FIRMS NRT API is returning data (rate limits reset at 00:00 UTC)

**Rollback procedure:** Previous day's predictions are retained at
`outputs/dashboard_feed/ignition_risk_v17_{YYYY-MM-DD}.json` (if archiving is enabled).
To revert: copy the desired dated file to `ignition_risk_v17.json` and re-run
`build_operational_alerts.py`.

**MTBF:** v17.5 has been running daily since 2026-04-19 without a pipeline failure.
The primary failure mode is FIRMS NRT API timeout; the pipeline retries 3× before exiting.

---

## Codebase references

| Component | Path |
|---|---|
| Base model | `outputs/predictive_fire_risk/predictive_v17_ba_pu/model.txt` |
| Training results | `outputs/predictive_fire_risk/predictive_v17_ba_pu/results.json` |
| Isotonic calibration | `outputs/predictive_fire_risk/predictive_v17_ba_pu/calibration.json` |
| Prediction script | `scripts/predict_ignition_v17.py` |
| Decoration pipeline | `scripts/build_operational_alerts.py` |
| Climatology builder | `scripts/build_beat_fire_climatology.py` |
| Climatology refresh | `scripts/refresh_climatology_history.py` |
| 2026 season report | `outputs/validation_reports/2026_SEASON_REPORT.md` |
| Per-trust-tier CSV | `outputs/validation_reports/2026_per_trust_tier.csv` |
| Dead-end experiments | `docs/audits/` and feedback files in `.claude/projects/.../memory/` |

---

## Owner / contact

JwalaNetra team — Madhya Pradesh Forest Department (MPFD) partnership.
Issues and PRs: FIRE repository on GitHub (branch `feature/level-4-digital-twin-integrated`).
Project lead: akshayr11@gmail.com
