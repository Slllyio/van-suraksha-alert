# Van Agni fire engine: handover for the eNetra team

Written 5 Nov 2026 for the developers who will plug the Madhya Pradesh forest fire work into eNetra.
Start here, then read `field-system/INTEGRATION.md` (the API spec) and `field-system/deploy/README.md` (the server).

## 1. What you are getting, in one paragraph

A **fire alert engine** that runs on one Linux server and talks to eNetra over HTTP. Every 15 minutes it pulls
satellite fire points (NRSC Bhuvan, FSI's portal, NASA FIRMS), keeps the ones in forest, gives each to its MP beat
(all 8,973 beats), groups pixels into one alert per fire, and grades the field visit (photos, GPS, "reached" at 200 m).
Every evening at 17:15 IST it also makes a **2-day outlook**: the 500 m squares most likely to burn in the next two
days, one LightGBM model per forest division (87 models), plus an officials-only **big-fire watch list**.
eNetra keeps its own users, app, dashboard, SMS/push and officer lists; the engine only does the fire side.

## 2. What is live and what is research

| Part | State | Where |
|---|---|---|
| Alert engine (ingest, forest filter, beat tagging, one alert per fire, visit proof, review) | Built and tested, **not hosted yet** | `field-system/app/` |
| eNetra API `/api/v1` + signed webhook | Built, spec frozen | `field-system/INTEGRATION.md` |
| Evening 2-day outlook (87 division models, 35% quiet-square share) | Built, checked against the PC run (99.6-99.9% same squares) | `field-system/pc_models/`, `scripts/cloud_daily.py` |
| Big-fire watch list (fixed per-division score cut) | Built, officials only | `field-system/app/big_watch_list.py` |
| Hints on each alert (big-fire points, burn scar, spread direction, runway, control-burn tag) | Built, officials only (`view=guard` hides them) | `field-system/app/*.py` |
| One-server Docker hosting (app + evening run + HTTPS) | Built, rehearsed from a fresh clone; Docker build and HTTPS cert not yet run on a real server | `field-system/deploy/` |
| Built-in pages `/` (control room) and `/field` (guard phone) | **Demo and test harness only**: eNetra's own app replaces them | `field-system/app/static/` |
| Research: model design, burn scars, spread, fuel maps, Prithvi, control burning, fire lines | Finished studies, results in the full report | see section 6 |

## 3. Code: which repository, which branch

| Repository | Use it? | What is in it |
|---|---|---|
| **Slllyio/van-suraksha-alert** (private) | **Yes, this is the one** | `field-system/` = the engine. `mp/` = the 87-division model study (PR #1, merged). PR #3 (draft) adds the hosting bundle, the server's seed data, the fixed-cut watch list and the 35% reference days: it must be merged before you deploy. PR #4 (draft) is a separate forest-loss monitor still in progress. |
| same repo, top-level `src/`, `dashboard/`, `scripts/`, `models/`, `*.png` | No, history | The earlier Guna-division Streamlit system (Feb-Jun 2026). Not used by the engine. A GitHub Action on `main` still commits a daily Guna alert file; it can be switched off. |
| Slllyio/vanagni (private) | Reference only | Research history. Draft PR #7 has `docs/SYSTEM.md` (system description), #8 the Prithvi fine-tune, #9 the burn-scar answer key. |
| Slllyio/jwala_gemini, wildfire-prediction, wildfire | **No** | Old copies, folded into vanagni in Sep 2026. Do not clone them for this work. |

Large files in van-suraksha-alert are in **Git LFS** (93 files, ~380 MB: model files, seed series, parquets).
Install `git lfs` before cloning. Each full clone downloads all of it, which counts against the repo owner's
monthly LFS bandwidth; if several people clone, one person can pull once and share the folder.

## 4. How eNetra connects (short version of INTEGRATION.md)

- Auth: every call sends `X-Api-Key`. Keys live only on the server in `FS_SERVICE_KEYS`. Server to server only (no CORS on purpose).
- Users stay in eNetra: each call passes eNetra's user id as `staff_external_id`.

| Call | What for |
|---|---|
| `GET /api/v1/alerts?since=…&division=…&beat_uid=…&status=…` | GeoJSON alerts; poll with `since` = last `generated_utc`. `view=guard` for guard phones. |
| `GET /api/v1/alerts/{id}` | One alert with satellite points and reports (photo links) |
| `POST /api/v1/alerts/{id}/reports`, `POST /api/v1/alerts/{id}/review` | Field visit from eNetra's app; range officer accept / send back |
| `POST /api/v1/positions`, `POST /api/v1/shifts`, `POST /api/v1/chance_finds` | Phone positions (route, "reached"), shifts, fires found on patrol |
| `GET /api/v1/daily_list`, `GET /api/v1/big_watch` | Tonight's 2-day outlook squares; officials' big-fire watch list |
| `GET /api/v1/brief`, `GET /api/v1/beats/summary`, `GET /api/v1/scar_check` | Division brief, weekly per-beat table, burn-scar check |
| `GET /api/v1/health` | Dead-man check: feeds fresh, evening list arrived |
| Webhook (`FS_WEBHOOK_URL`, HMAC `FS_WEBHOOK_SECRET`) | `alert.updated`, `alert.reached`, `alert.reported`, `alert.reviewed`; retried in order, de-duplicate on `X-Event-Id` |

**Mapping to eNetra's current alert record** (from eNetra's production `listalerts` response for Guna):

| eNetra field | Engine field | Note |
|---|---|---|
| `lat`, `long` | `lat`, `lon` (also GeoJSON geometry) | eNetra sends strings, engine numbers |
| `division`, `range`, `beat` | `division`, `range`, `beat` (+ `beat_uid` = DID-RID-BID) | Join on `beat_uid` rather than names (names repeat across divisions) |
| `compartment` | `fsi.compartments[]` | Only when FSI sent the same fire |
| `sub_range`, `sub_division` | not in the engine | eNetra adds them from its own beat table via `beat_uid` |
| `startDate` / `createdAt` | `first_seen_utc` | |
| `status` | `status` (`new`, `visited`, `verified`, `revisit`) | |
| `alert_no` | `id` | eNetra can keep its own numbering and store the engine `id` |
| `confidence` | none for fire points; outlook squares carry a calibrated chance | |
| `officers` | not in the engine | eNetra keeps officer lists and sends SMS/push |
| `geo` / `kml_url` | point features; big fires carry all pixels | eNetra can draw its own polygon |

## 5. Running it

Laptop test:
```
cd field-system
pip install -r requirements.txt
python scripts/add_staff.py --name "Admin" --role admin     # asks for a PIN
python run.py                                               # http://localhost:8000
python scripts/run_tests.py                                 # test suite
```
Server: follow `field-system/deploy/README.md` (Ubuntu, 2-4 vCPU, **16 GB RAM**, 40 GB disk, **in India**; three runs of
`deploy/install.sh`, Docker compose, HTTPS via sslip.io or your own domain). eNetra already stores its files in
AWS Mumbai (ap-south-1), so the simplest home for the engine is a small EC2/Lightsail box in the same AWS account.
The evening run peaked at 6.2 GB RAM and took 7 minutes for 430,776 squares.

Secrets the server needs (typed into `field-system/deploy/.env` on the server, never into git):

| Variable | What | Without it |
|---|---|---|
| `EARTHDATA_TOKEN` | NASA Earthdata bearer token (urs.earthdata.nasa.gov > Generate Token), use a team account | HLS and MODIS inputs go stale after ~20 days; the evening list says so |
| `FS_SERVICE_KEYS` | Key(s) eNetra sends as `X-Api-Key` (installer generates one) | API refuses calls |
| `FS_WEBHOOK_URL`, `FS_WEBHOOK_SECRET` | eNetra's webhook endpoint and signing secret | eNetra polls instead |
| `FIRMS_MAP_KEY` (optional) | NASA FIRMS key, only for archive pulls | Live alerts still work (public files) |

## 6. Data inventory

**Tier 1: what the server needs, already in git (PR #3, via LFS).** `field-system/data/` 78 MB (beat layer 52 MB,
roads raster, industry mask, spread and runway models), `field-system/seed/` 209 MB (cloud input series and big-fire
history the first run starts from), `field-system/pc_models/` (87 division models, calibration, `meta.json`, static inputs).

**Tier 2: reading, on the shared Drive folder.**
- `PROJECT_FULL_REPORT.pdf` (59 pages, 5.8 MB): every result, what failed and why.
- `Van_Agni_compendium_2026-10-21.zip` (57 MB): report, maps, 46 tables (CSV + Excel), per-division factsheet, key data, all study READMEs.
- This file, `INTEGRATION.md`, `deploy/README.md`.

**Tier 3: research data, on request** (not needed to run the engine). Kept in the project's cloud folder (~9.5 GB) and on
Akkshay's PC (`E:\FIRE`).

| Set | Size | Where |
|---|---|---|
| Burn scars MP 2017-26 (153,817 fires + 2026 scars), alert-to-scar lookups | 2.6 GB | cloud `fire-alert-scars/`, 2026 scars in `research/large-fires/scars2026/` |
| Ratapani pilot: spread, FSI scouting, MP 500 m grid + static GIS, beats | 3.7 GB | cloud `ratapani/`; PC `E:\FIRE\ratapani` (13 GB, fuller) |
| Fuel maps and Prithvi | 1.8 GB | cloud `fuel-map/` |
| Research studies (ceiling/daily rule, large fires, big fires, spread review, ignition) | 1.0 GB | cloud `research/` |
| Cold files moved off the cloud folder (manifest with SHA-256) | 0.8 GB | PC `E:\FIRE\cloud_archive` |
| Raw training inputs and model runs | data 5.8 GB, models 8.3 GB, outputs 41 GB, ratapani_burn 12 GB | PC `E:\FIRE` |
| MP beat shapefile (source of `beats_mp.geojson`) | | PC `E:\MP_Merge\Mp_Beat_Merge.shp` |
| Forest loss monitor (separate work) | 70 GB | PC `E:\FIRE\forest_loss_monitor` |

The local SQLite database `field-system/var/field.db` is test data and is **not** shared.

## 7. The yearly calendar and open items

| When | Job | How |
|---|---|---|
| Now | Merge PR #3, pick the server, run `install.sh`, set the secrets above | deploy/README.md |
| Before Feb 2027 | Trial run of the evening list on the real server for a few weeks | `GET /api/v1/health` |
| Before Feb 2027 | Static season inputs: keep the 2025 AlphaEarth map until 2026 is published, then `pc_models/make_static_season.py` | pc_models/README.md |
| Before Feb 2027 | `scar_hist_2027.npz` for the big-fire list; calibration refit on the 2026 season | deploy/README.md "Left for later" |
| Alert start dates | Early-season divisions ~20 Feb, middle early March, late from late March | per-group dates in the runner |
| Fire season | 15 Feb - 15 Jun; control-burn tag (officials only) 15-28 Feb | `app/control_burn.py` |
| **Every June** | Refresh the big-fire watch list's per-division cuts from the season just ended (`watch/cuts_2025.json` → `cuts_2026.json`) | research/large-fires/README.md |
| Optional | Weekly burn-scar check on the server (`FS_SCAR_LIVE`, off; needs 877 MB of scar inputs moved) | deploy/README.md |

Rules that should not change without a test on a full past season: never hold back an alert; a burn scar shown as
`none_visible` is **never** a false alarm; guards never see the officials-only hints.

## 8. Headline numbers (2026 season, live rule)

The evening list flags about 22% of forest ground and catches **65%** of fires (52% of brand-new fires, 81% of beats
that burn); on 2023-24 the same rule caught 70% / 50% / 83%. The big-fire watch list's fixed cut caught 64% of
200 ha+ fires on about 3% of ground. Both lists are rankings with calibrated chances, not certainties. Details and caveats: full report sections on the daily rule and large fires.
