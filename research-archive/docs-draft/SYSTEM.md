# What this system does

A complete description of VanAagni / JwalaNetra: the satellite-and-weather monitoring system for
**Guna forest division, Madhya Pradesh** — 8 ranges, 139 beats, 747 forest compartments, about
2,144 km² of jurisdiction of which roughly 1,550 km² is legally notified forest.

This document is the map. It explains what the system watches, what it produces, how each number
is arrived at, how well each part has been shown to work, and what it deliberately does not do.
Every figure quoted here was measured on real data and can be reproduced with the command named
beside it. Where a part of the system is unfinished or unverified, this document says so.

Companion documents go deeper on single topics: `WEATHERNEXT.md` (the weather forecast and its
verification), `OBSERVED_WEATHER.md` (the observed weather series), `FIRE_OCCURRENCE.md` (the fire
probability models), `FIRE_EVAL.md` (the fire side tested against twelve real seasons),
`CODEBASE_REVIEW.md` (an end-to-end review of every file, including what is broken),
`CONSOLIDATION.md` (how four GitHub repositories were folded into this one; summarised in §10).

---

## 1. The two problems

The division loses forest in two different ways, on two different clocks, and the system has one
half for each.

| | **Fire** | **Felling and encroachment** |
|---|---|---|
| The loss | A fire burns for hours to days | Trees are cut, or forest is converted to cropland, over weeks |
| The question | *Where will it burn, and where is it burning right now?* | *Where did the canopy disappear since last time?* |
| The clock | Twice a day, plus a 15-day outlook | Every day, comparing against a seasonal baseline |
| Main inputs | Weather forecasts, weather reanalysis, satellite thermal detections | Optical, radar and land-cover satellite imagery |
| Maturity | **Working and measured** — this is what recent work has built | **Working, unmeasured** — runs daily, never scored against ground truth |
| Entry point | `scripts/nrt_alert_pipeline.py`, `src/analysis/fwi.py` | `src/inference/generate_alerts.py`, `scripts/guna_ews_daemon.py` |

The two halves share the geography (`src/utils/beats.py`), the database, the API, the dashboards
and the notifier, but they do not share a model or a decision. They are described separately below.

---

## 2. The geography everything hangs on

Three nested units, from `data/aoi/`:

- **Division** — Guna, the whole area of responsibility. One number for the whole division is what
  the daily bulletin leads with.
- **Range** (8) and **beat** (139) — the administrative units. A beat is the patrol unit, median
  17.0 km², and is the finest unit the system reports at. `Range::Beat` is the key used everywhere
  (for example `Aron::Goumukh`), because beat names alone are not unique.
- **Compartment** (747, about 1,547 km² by geometry, `data/aoi/gunafinal.geojson`) — the legally
  notified forest.
  Each compartment is assigned to the beat it lies inside, by geometric overlap rather than by name,
  because the two layers spell names differently.

**"Forest" means inside a compartment.** This is the single most consequential definition in the
system, and it is the Department's own boundary rather than a satellite land-cover guess. It
matters because the beat polygons contain about 693 km² of non-forest — villages, fields, roads — and a
fire in a wheat stubble field inside a beat is not a forest fire. Measured over twelve seasons:
of 28,087 satellite fire detections inside the division's bounding box, only **2,167 (8%)** are
inside a compartment. Before this rule existed, all 28,087 would have been graded as forest fires.

---

## 3. Part one — the fire half

The fire half answers four questions, in order of how far ahead they look.

```
  15 days ahead        7 days ahead        1-7 days ahead         right now
  ─────────────        ───────────         ──────────────         ─────────
  How dangerous        Will there be       Which beats are        Where is it
  will the weather     a fire at all?      most likely?           burning?
  be?
  ↓                    ↓                   ↓                      ↓
  FWI outlook          Occurrence index    Beat panel             NRT bulletin
  (ensemble)           (+ fire memory)     (patrol list)          (VIIRS + ledger)
```

### 3.1 Fire danger from weather: the Canadian FWI

The system's danger rating is the **Canadian Forest Fire Weather Index**, the same family of
indices the Forest Survey of India uses. It is a chain of six numbers computed from four weather
values taken at local noon — temperature, relative humidity, wind speed, and rain in the previous
24 hours:

| Code | What it tracks | Reacts in |
|---|---|---|
| **FFMC** — Fine Fuel Moisture Code | Dryness of litter and fine twigs: what actually ignites | Hours |
| **DMC** — Duff Moisture Code | Moisture in loosely packed organic layers | Days |
| **DC** — Drought Code | Deep, compact organic matter: seasonal drought | Weeks |
| **ISI** — Initial Spread Index | FFMC and wind combined: how fast a fire would spread | Hours |
| **BUI** — Buildup Index | DMC and DC combined: how much fuel is available | Days |
| **FWI** | ISI and BUI combined: the headline danger number | — |

Because each code carries forward from the day before, the chain has memory: a single hot afternoon
does not produce an extreme rating, but three dry weeks do. Danger classes used here are Low,
Moderate, High, **Very High at FWI 21.3** and **Extreme at 38.0**.

The implementation is vectorised (`src/analysis/fwi.py`) and checked to 1e-13 against the original
scalar implementation (`scripts/compute_fwi.py`), so the fast path and the reference path cannot
drift.

**An important honest finding.** In Guna's fire season the FWI crosses 21.3 on **75%** of days and
38.0 on **52%**. A rating that says "Very High" three days in four describes the season rather than
warning about it: saying it every day scores a perfect hit rate and a skill score of exactly zero.
This is why the system adds the fitted probabilities of §3.4 rather than relying on the index alone.

### 3.2 Where the weather comes from

Two separate weather streams feed the chain, and keeping them in the same convention turned out to
matter more than either one individually.

**Observed weather (what happened).** Two sources:

- **NASA POWER** (`scripts/compute_fwi.py`) — one division-wide point series from 2013 to today.
  It is *daily means*, and it lags about a week. This is still the bulletin's headline observed
  value, for continuity.
- **Open-Meteo reanalysis archive** (`src/data/openmeteo_archive.py`, `src/analysis/fwi_observed.py`)
  — hourly ERA5-Land and ECMWF analysis, fetched once per 0.1° cell (45 cells cover the division),
  reduced to **the value at 06:00 UTC = 11:30 IST**, which is the FWI's noon convention. Rolled per
  cell and expanded to beats, this gives every beat its own moisture state, at most one day old.

  Measured at the POWER point over 2013-2026: the noon series runs **3.5 °C warmer** and **7.6 FWI
  points higher** than the daily-mean series (correlation 0.90). Neither is wrong — they are
  different quantities. The danger is mixing them, which the system used to do.

**Forecast weather (what will happen).** A chain of providers, each falling through to the next
with the reason recorded (`src/data/weathernext_ingest.py`):

1. **WeatherNext** (Google DeepMind, via Earth Engine) — used when those credentials exist.
2. **Open-Meteo ensemble** (`src/data/openmeteo_ensemble.py`) — **the default, and it needs no
   credentials at all.** ECMWF IFS at 0.25° (51 members, 15 days) plus NOAA GEFS (31 members,
   10 days), fetched once per grid cell: the 139 beats fall into 14 cells, so one morning's fetch
   is about 600 API call-weights instead of 5,200.
3. **Open-Meteo deterministic** — a single forecast, no spread.
4. **Climatology** — the day-of-year average of the observed record, labelled **NOT A FORECAST**.
   The bulletin will not raise a watch from it.

### 3.3 The 15-day outlook, with real probabilities

`make fwi-forecast` rolls the FWI chain forward for **every beat and every ensemble member
separately** — 139 beats × 82 members × 16 days — starting each beat from its own observed
moisture state. Because every member is rolled individually, the outlook reports genuine
probabilities rather than a single line with error bars drawn around it:

- **`fwi_p10 / p50 / p90`** per beat and day — percentiles of the FWI itself.
- **`p_very_high` / `p_extreme`** per beat and day — the share of members crossing 21.3 / 38.0.
- **`p_very_high_3d`** and the 7- and 15-day versions — the share of members whose *maximum over
  the horizon* crosses the threshold. This is a true "at least one dangerous day in the next three"
  probability, not a daily probability re-used.
- Four named scenarios (`median`, `mean`, `dry_extreme`, `wet_mild`) for readers who want one
  line rather than a distribution.

The two models are weighted **equally as models**, not per member, so the percentiles do not jump
on day 11 when GEFS runs out and ECMWF continues alone.

Every issued run is archived (`data_lake/fire_weather/archive/`) with all of its probabilities.
That archive *is* the forecast log: it is what verification scores later, so skill accrues from the
day the system starts running rather than from the day someone remembers to start logging.

### 3.4 Will there be a fire? The occurrence models

The FWI is a physical index, not a statistical prediction of ignition. Guna's fires are almost all
lit by people — during mahua and tendu collection, and after the wheat harvest — so the system also
fits models directly on the fire record: **twelve complete fire seasons, 2013-2024, 1,803 season
days, 549 of them fire days**, labelled from NASA FIRMS VIIRS detections inside a compartment.

Everything is scored **leave-one-year-out**: every number below comes from a model that never saw
the season it is scoring.

Two facts in the record shape the models:

- **Recent fire is the strongest single predictor there is.** The count of in-forest detections in
  the previous seven days separates fire days from quiet ones at AUC 0.86, against 0.70 for the
  FWI. Fires come in spells: the chance of a fire day is **64% when yesterday had one and 16% when
  it did not**.
- **Where fires happen is stable over the long run, though not year to year.** Comparing single
  years suggests no pattern (rank correlation 0.02), and an earlier version of this analysis
  concluded there was none. That was the wrong test — one season is too few fires spread over 139
  beats. Pooling the other eleven years predicts the held-out year's burning beats at **AUC 0.795**
  (0.90 for beats with three or more fire days). The geography is real; it is just slow.

Four models are fitted (`make fire-occurrence`, `make fire-panel`):

| Model | Question | Held-out AUC | Notes |
|---|---|---:|---|
| **Weather index** | Fire day in the division today? | 0.807 | Humidity, fine-fuel moisture, season. FWI scores 0.702 on the same days |
| **Memory index** | Same, knowing recent fires | **0.897** | Beats the FWI in **12 of 12** seasons; Brier 0.118; best cut 0.30 |
| **Weekly figure** | Any fire day in the next 7? | **0.919** | Fitted directly, not multiplied up from daily odds |
| **Beat panel** | *Which* beats? | **0.900** pooled | Where-skill 0.78: on a fire day it ranks the beats that actually burn |

The **beat panel** deserves a note because per-beat prediction is where such systems usually
overreach. Beat-fire-days are rare — 1,366 in 250,617 beat-days, 0.55% — so no per-beat model can
be fitted. Instead one pooled model is fitted over every beat-day, using: the division's own
probability for that day, each beat's long-run fire rate computed from *other* years, its own and
its neighbours' fires in the previous week, and its forest area. Elevation and the mahua/tendu
collection windows were offered as candidates and admitted only where they improved held-out skill.

Its output is honestly framed as **a ranked patrol list, not a per-beat alarm**:

| Beats patrolled per day | Share of burning beats caught | Precision |
|---:|---:|---:|
| 10 | 26% | 7.6% |
| 20 | 47% | 6.9% |
| 40 | 70% | 5.1% |
| 60 | 81% | 4.0% |

Reading that plainly: catching seven in ten of the beats that will burn means visiting forty of the
139 every fire season day, and nineteen of every twenty on that list will not burn. Whether that
trade is worth making is the Department's judgement, not the software's.

**Every model carries an honest lead table.** For a forecast issued *k* days ahead, the model is
re-scored with every input as it was actually known on the issue day. The memory index falls from
0.897 to 0.832 over seven days; the FWI falls from 0.702 to 0.591. A forecast-driven probability
has to beat that lagged bar to be worth anything, and the system reports both.

**When the fire record is not fresh, the models say so.** Memory features need the detection stream.
If the newest detection is more than two days old, the memory features become **unknown — never
zero**, the weather-only variants are served instead, and the outlook records which model served
which field and why. A zero would read as "no fires", which is the opposite of "we don't know".

### 3.5 Where is it burning now? The bulletin

`scripts/nrt_alert_pipeline.py` runs twice a day and produces the operational bulletin. Four
behaviours in it were rebuilt after the twelve-season evaluation showed the originals could not
work:

1. **Selection by acquisition time, not calendar date.** The old run asked for "today's" IST date at
   03:30 IST, but FIRMS timestamps in UTC and that UTC day had not begun. Replayed over twelve
   seasons it would have carried **0% of detections**. It now selects by a rolling acquisition
   window and runs at 06:30 and 18:00 IST, one run per satellite overpass: **100% carried, median
   4.5 hours from overpass to bulletin.**
2. **Only in-compartment fires are dispatched.** Everything else is counted, summarised with a
   distance-to-forest histogram, and named in one line. Alerts over twelve seasons fell from
   **23,861 to 2,033**, and days the division reads CRITICAL from 405 to 314.
3. **A de-duplication ledger and event memory.** Each detection gets a stable identity, and events
   are linked across runs, so a fire that was burning yesterday is marked `continuing` rather than
   raised as new. 13% of in-forest detections continue a known event.
4. **The forecast wins when the observation is stale.** Scoring today's fire with a six-day-old
   observed FWI cost real skill (Peirce 0.38 → 0.25). Past two days, the beat forecast valid for
   today is used instead, and the bulletin says which it used.

Each dispatched fire carries its compartment number, its beat, distance to the forest boundary,
fire radiative power, day or night, its event id and status, and a combined severity. **No alert
threshold was changed** by any of this work: WATCH still fires at FWI 21.3, and the severity gate
is still 38 / 21.3 / 11.2, because those cuts are the Department's to move.

### 3.6 Is any of it actually any good? Verification

The system carries its own scoring machinery (`src/analysis/fwi_verify.py`) and refuses to grade
itself on a curve. Two free baselines set the bar: **persistence** ("as dangerous as today") and
**climatology** ("as dangerous as this date usually is", computed leave-one-year-out). A forecast
that cannot beat the better of those at a given lead should not be used at that lead.

Lead-time verification does not wait a month for live data. `src/data/openmeteo_previous_runs.py`
fetches what ECMWF and GFS *forecast 1 to 7 days earlier for every past hour*, archived back to
January 2024, rolls each into an FWI forecast from the moisture state as it stood on that issue
day, and writes it into the same archive layout the verifier reads.

Results from 123 daily forecasts of the 2024 fire season, scored per beat against each beat's own
noon observed series:

| Lead | MAE (FWI) | Error removed vs persistence | vs climatology | Danger class right |
|---:|---:|---:|---:|---:|
| 1 day | 5.4 | **29%** | **47%** | 90% |
| 3 days | 7.3 | 26% | 29% | 89% |
| 7 days | 10.5 | 21% | −1% | 87% |

Useful out to **7 days against persistence and 6 against climatology**, with all eight ranges
showing the same skill. And the fire probability driven by that forecast:

| Lead | Weather index (forecast-driven) | its persistence bar | Memory index | its bar |
|---:|---:|---:|---:|---:|
| 1 day | **0.902** | 0.792 | 0.867 | 0.884 |
| 7 days | 0.838 | 0.756 | 0.841 | 0.832 |

Three things this measurement established, each of which changes how the system should be read:

- **The weather forecast genuinely adds skill** to the weather-only index — 0.90 against a bar of
  0.79 at one day — and sits at its perfect-forecast ceiling, so at short leads it is the better
  daily probability.
- **The memory index's short-lead skill is the fire spell, not the weather.** Its persistence bar is
  already 0.88; the forecast only overtakes it from about day six.
- **Convention matters as much as accuracy.** Scored against NASA POWER daily means, the very same
  forecasts look 5 to 14 FWI points biased and never beat persistence. That is the noon-versus-mean
  mismatch, not forecast error. Verify noon forecasts against noon truth.

GFS's archived forecasts are unusable as issued for this purpose (+12 to +24 FWI, drier and
windier than reality), which is why ECMWF leads the model list.

Two further checks run continuously: **band coverage** asks whether the observed FWI actually falls
inside the ensemble's p10-p90 band about 80% of the time, and **threshold sheets** per lead give the
Department the hit rate, false-alarm rate and days-per-season for every candidate cut, at the lead
they would act on.

---

## 4. Part two — the felling and encroachment half

The other half watches for canopy that disappears without a fire: illicit felling, and conversion
of forest to cropland.

### 4.1 The five-signal rules engine

`src/inference/rules_engine.py` runs almost entirely server-side on Google Earth Engine, so no
imagery is downloaded. For a beat and a date it builds five independent signals:

| Signal | Source | What it catches |
|---|---|---|
| **NDVI z-score** | Sentinel-2 composite (MODIS fallback) against a per-range **harmonic phenology model** | Greenness far below what this range should look like on this day of year |
| **Dynamic World deltas** | Google Dynamic World land-cover probabilities | Tree probability dropping ≥ 10 points, or crop probability rising ≥ 10 points, between two passes |
| **NBR** | MODIS | Burn-like spectral change |
| **Sentinel-1 VH drop** | Radar backscatter | Structural canopy loss — works through cloud |
| **Sentinel-1 CuSum** | Cumulative-sum trend on radar | Slow, sustained change a single pair would miss |

The phenology model is what makes this work in a dry deciduous forest, where the canopy legitimately
browns off every year. Comparing today against the seasonal expectation for *this range on this day
of year* separates real loss from the normal cycle.

The signals are fused into a candidate mask, cleaned morphologically, masked to the Hansen forest
baseline, vectorised into patches, and each patch scored in a single batched sampling call. Zone
risk adds a boost where forest density and radar trend agree. Alerts are written as GeoJSON, PDF and
KMZ, appended to a log, pushed to PostGIS, and optionally sent to Telegram.

**What the daily job actually runs.** The scheduled felling job (`scripts/ews_scheduler.py` →
`scripts/guna_ews_daemon.py`) does not call this engine. It harvests Dynamic World probabilities
and scores them with its own lighter scorer (`scripts/_simple_dw_score.py`: a day-of-year baseline
per range and a multi-threat score), so the alerts officers receive each morning come from the
Dynamic World signal alone. The full five-signal engine runs on demand through
`src/inference/generate_alerts.py` (`run_pipeline.py --steps alerts`). Making the daemon call the
engine is a deliberate decision still to be made, because it changes what officers are sent.

### 4.2 The neural model, and its status

`src/model/vanaagni.py` implements **VanAgni**: a Prithvi-EO-2.0 vision-transformer encoder over
Harmonised Landsat-Sentinel imagery, with a four-scale FiLM-conditioned UNet decoder that folds in
weather, seven-day weather history, terrain, burn age and land cover, and returns both a prediction
and its own uncertainty. Training code and configs exist (`src/train/train_vanaagni.py`).

**It is not in service.** No trained checkpoint exists, and `detection_mode: rules` is what runs.
The fire-risk raster step that the daily pipeline's documentation describes is absent from the code,
which is why that layer of the bulletin is structurally empty. This is stated plainly here because
the architecture diagram in the paper implies otherwise.

### 4.3 What is not measured

The fire half has been scored against twelve seasons of real fires. **The felling half has not been
scored against anything.** There is no labelled ground-truth set of verified felling events in the
repository, so precision and recall are unknown. It runs daily and produces alerts that officers
have found useful; that is field experience, not measurement. Building that ground truth is the
single highest-value piece of work outstanding on this half.

---

## 5. Data flow, end to end

Every arrow below is a file on disk or a table in PostGIS, so each stage can be re-run or inspected
on its own.

```
 EXTERNAL SOURCES                    PROCESSING (this repository)                OUTPUTS
 ────────────────                    ────────────────────────────                ───────
 Open-Meteo ensemble ──┐
 (ECMWF 51 + GEFS 31)  ├─► weathernext_ingest ─► per-cell forecast ─┐
 WeatherNext (opt.) ───┘   provider chain        (14 cells)         │
                                                                    ▼
 Open-Meteo archive ────► fwi_observed ─► per-beat noon FWI ──► fwi.py: roll FWI per ──► fwi_outlook_latest.json
 (ERA5-Land, hourly)      (45 cells)      moisture state         beat × member × day      beat forecast Parquet
 NASA POWER ────────────► compute_fwi ─► division FWI series        │                     run archive (forecast log)
                                                                    ▼
 NASA FIRMS VIIRS ──┬───► fire_memory ─► recent in-forest fires ─► fire_occurrence ──► memory / weather index
 (active fires)     │                                              fire_panel           weekly figure, beat panel
                    │                                                                   │
                    └───► nrt_alert_pipeline: window select, ──► fire bulletin (JSON) ◄─┘
                          forest test, dedupe ledger, events          │
                                                                      ▼
 data/aoi (beats,                                               PostGIS ─► FastAPI ─► dashboards
 compartments) ─────────► beats.py: Range::Beat, forest test       │                 notifier (Slack,
                                                                   │                 Telegram, email)
 Earth Engine: S2, S1, ─► guna_ews_daemon (Dynamic World score) ─► felling alerts ───┘
 Dynamic World, MODIS,    rules_engine (five signals, on demand)   GeoJSON / PDF / KMZ
 Hansen

 Run archive + observed series ─► fwi_verify ─► skill tables, coverage, threshold sheets
```

Three properties of this flow matter more than any single box:

- **The geography is the join key.** Every stage keys on `Range::Beat` and the compartment test
  from `src/utils/beats.py`, so a forecast, a detection and a felling alert for the same place
  line up without fuzzy matching.
- **Forecasts are logged before they are scored.** The run archive is written at issue time and is
  the only input verification reads for forecasts, so no forecast can be revised after the fact.
- **The two halves meet only at the outputs.** The fire chain and the felling chain share
  geography, database, API, dashboards and notifier, and nothing upstream of those.

---

## 6. What comes out, and where it goes

| Output | Form | Consumers |
|---|---|---|
| **Fire bulletin** | JSON + printed summary | Officers; the outlook block carries division danger, top beats, probabilities, the weekly figure and the "which beats" table |
| **FWI outlook** | `fwi_outlook_latest.json` (version 2) | API, dashboard, notifier, database |
| **Beat forecast table** | Parquet, per beat / day / scenario / member | Verification, database |
| **Run archive** | One Parquet per issued run | Verification — this is the forecast log |
| **Felling alerts** | GeoJSON, PDF, KMZ, JSONL log | Field officers, PostGIS |
| **REST API** | FastAPI over PostGIS | `/alerts`, `/beats`, `/stats`, `/fwi/outlook`, `/fwi/forecast/{Range::Beat}` |
| **Dashboards** | Streamlit and MapLibre/deck.gl | Choropleths of danger and probability, fan charts with the ensemble band, patrol lists |
| **Notifications** | Slack, Discord, Telegram, email | Daily digest and outlook summary |

The **API** and **dashboard** both expose ranking by any of the probabilities, so an officer can ask
for the ten beats with the highest chance of fire in the next three days as easily as the ten with
the highest raw danger index.

---

## 7. How it runs

```
01:00 UTC (06:30 IST)   Full chain: refresh observed weather → per-beat series →
                        fetch ensemble → 15-day outlook → fire bulletin → pipeline
12:30 UTC (18:00 IST)   Evening: re-fetch the ensemble (newer runs are out),
                        rebuild the outlook, second bulletin — one per overpass
21:30 UTC (03:00 IST)   Felling daemon → dashboard rebuild → digest
03:00 UTC, monthly      Ensemble band coverage check
```

Deployment is either Docker Compose (PostGIS, migration, API, scheduler, dashboard) or systemd
timers on a bare host; the original Windows workstation schedule still runs unchanged. Every network
fetch is cached, resumable and budgeted, and a quota response stops a run cleanly so the next one
picks up where it left off rather than starting over.

Credentials are optional by design. **The entire fire-weather path — ensemble, per-beat observed
series, outlook, probabilities, verification — runs with no credentials whatsoever.** Earth Engine
is needed only for the felling half and for WeatherNext; a FIRMS key is needed only for live fire
memory and for seasons after 2024.

---

## 8. Honest limits

- **Labels are satellite detections, not reported fires.** VIIRS misses small, short and
  cloud-covered fires. The models predict what the satellite sees, which is a proxy.
- **The fire base rate swings hard between years** — 6% of season days in 2015, 52% in 2024. One
  fixed threshold behaves very differently in a quiet year and a busy one; the sheets are pooled
  across twelve seasons and say so.
- **The ensemble is 25 km and the observed series 11 km.** Beats sharing a grid cell share weather;
  per-beat contrast comes from each beat's own moisture state, and skill is reported per range so
  grid noise is not mistaken for beat-level skill.
- **Lead-time skill is one season of forecasts** (2024). It should be re-tested on 2025-26 once the
  FIRMS key is in place.
- **The felling half is unmeasured**, as described in §4.3.
- **The neural fire-risk model is not in service**, as described in §4.2.
- **Nothing here dispatches on a fitted probability.** Every alert threshold is unchanged from what
  the Department set.

---

## 9. Decisions this system puts to the Forest Department

Each of these is a policy choice the code deliberately does not make, and each comes with a sheet
of numbers to make it on:

1. **Does the bulletin's headline observed FWI move to the noon convention?** It is the physically
   correct one and matches the forecast, but it reads about 7 points higher, so a fixed threshold
   fires more often.
2. **What probability cut, at what lead?** The memory index peaks in usefulness around 0.30, which
   catches 86% of fire days while being wrong on 37% of its warnings, about 63 days a season.
3. **How many beats to patrol from the ranked list**, given the capture-and-precision table in §3.4.
4. **Should any fitted probability ever gate an alert**, or remain reported-only beside the FWI.
5. **Which Open-Meteo tier** a government deployment should use.

---

## 10. The four repositories and how they relate

The work began in four GitHub repositories. They were consolidated into this one on 2026-09-04
(`docs/CONSOLIDATION.md` has the commit-by-commit record and the proofs); this is what each was and
where it went.

| Repository | What it held | Relationship to this system | Status |
|---|---|---|---|
| **`Slllyio/vanagni`** | Everything described in §1-§9 | **This repository: the single home of the system** | Active |
| `Slllyio/jwala_gemini` | One commit (`29d3e2c`, 2026-03-10), the first snapshot of the JwalaNetra codebase | It is the *root commit* of `vanagni`; same tree object. Everything in it is already here, plus all later work | README points here; to be archived |
| `Slllyio/wildfire-prediction` | A separate Chhindwara-district fire-risk research codebase (three commits, Jan-Feb 2026) | Grafted with full history into `wildfire-prediction/` in this repository. Shares no code with the system above | README points here; to be archived |
| `Slllyio/wildfire` | Nothing: no commits, no branches | None | Empty; delete it, or rename `vanagni` to `wildfire` |

Inside this repository there are therefore **two lineages that do not share code**:

- **The Guna system** (the repository root) — everything in §1-§9.
- **The Chhindwara lineage** (`wildfire-prediction/`) — an earlier attempt at the same question,
  "will this place burn in the coming weeks", for Chhindwara district and its Bichua beats. It
  extracts about 85 features per sample on Earth Engine, labels them from FIRMS active fires (an
  older path used MODIS MCD64A1 burnt area), and fits two models: a Random Forest on per-patch
  spectral statistics (the working path) and a classifier head on a frozen Prithvi-EO-2.0 encoder
  (trained on Colab, never finished). It runs from inside its own folder with its own
  `requirements.txt`. **Its README's "AUC-ROC 0.92" is not an evaluation**: the ROC is built from a
  hand-typed array, and the Random Forest's oversampling happens before the train/validation split
  (`docs/CODEBASE_REVIEW.md` §9). Nothing in the Guna system depends on it. Its Earth Engine
  feature utilities are the part worth porting.

Two other bodies of code sit beside the main line and are **not** part of the running system:

- **The Punjab-era layer** inside `src/` (`full_model.py`, `prithvi_mae.py`, `train.py`,
  `detect.py`, `predict.py`, `viz/`): a forest-to-agriculture change detector for Fatehgarh Sahib,
  Punjab, from before the work moved to Guna. `detect.py` and `predict.py` do not import. It is
  slated for removal.
- **The branch `feature/level-4-digital-twin-integrated`** (eleven commits, 2026-03-14): a
  fire-spread simulator, a 3D digital twin, carbon ledger and several "AI" panels. It breaks
  training and detection at its head, carries about 150 MB of binaries, and some of its panels
  display random or hard-coded numbers as measurements, so it is kept as a branch and not merged.
  `docs/CODEBASE_REVIEW.md` §8 lists the five pieces worth taking from it.

---

## 11. Where things live

```
src/analysis/    fwi.py            the FWI chain, member rolling, the outlook
                 fwi_observed.py   per-beat observed series in the noon convention
                 fwi_verify.py     baselines, lead-time, probabilistic and coverage verification
                 fire_occurrence.py  the division probability models
                 fire_panel.py     the per-beat panel: which beats
                 fire_memory.py    recent fire activity as a live input
                 fire_eval.py      the system replayed against twelve real seasons
src/data/        openmeteo_ensemble.py / _archive.py / _previous_runs.py / _ingest.py
                 weathernext_ingest.py   the provider chain
                 climatology_provider.py the last resort
src/inference/   rules_engine.py   the five-signal felling detector
                 generate_alerts.py
src/model/       vanaagni.py       Prithvi-EO-2.0 + FiLM (not in service)
src/utils/       beats.py          beats, compartments, the forest test, grid cells
scripts/         nrt_alert_pipeline.py  the fire bulletin
                 compute_fwi.py    the NASA POWER observed series
                 guna_ews_daemon.py     the daily felling job
data/aoi/        division, range, beat and compartment boundaries
docs/            this file and the deeper documents named at the top
wildfire-prediction/  the separate Chhindwara lineage (§10), run from inside its own folder
```

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **Beat** | The patrol unit; 139 in the division. Written `Range::Beat` |
| **Compartment** | A legally notified forest parcel; 747 in the division. "Forest" means inside one |
| **FWI** | Canadian Forest Fire Weather Index; Very High at 21.3, Extreme at 38 |
| **Fire day** | A day with at least one satellite fire detection inside a compartment |
| **AUC** | How well a score separates fire days from quiet days. 0.5 is a coin toss, 1.0 is perfect |
| **Brier score** | How accurate stated probabilities are. Lower is better |
| **Peirce skill** | Hit rate minus false-alarm rate. 0 means no better than chance |
| **Leave-one-year-out** | Fit on eleven seasons, score the twelfth; repeat. No model is scored on data it saw |
| **Lagged bar** | What you would score by assuming today's conditions persist. A forecast must beat this |
| **Where-skill** | On a day fires occurred, how well the beats that burned were ranked |
| **Ensemble member** | One of 82 alternative forecasts; their spread is the uncertainty |
| **NRT** | Near-real-time — satellite detections available within about three hours |
