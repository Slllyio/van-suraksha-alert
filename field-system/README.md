# Fire alerts and field checks (prototype)

**Plan (Akkshay, 14 Oct):** this runs inside eNetra, the existing platform with its own app and dashboard. This code is the engine (alerts, beats, filters, proof checks). eNetra connects through the API in [INTEGRATION.md](INTEGRATION.md). The built-in pages (`/`, `/field`) stay as a demo and test harness.

A small web system that shows live NASA fire points (VIIRS and MODIS, the satellites FSI's alerts come from), gives each one to its forest beat, and records whether field staff went there, with photos and the FSI feedback fields. A range officer checks each visit and accepts it or sends it back.

Status: working prototype on all 8,973 MP beats, tested on this week's live points and a replay of the 2024 Ratapani season. Not yet in any repo.

## What it does

1. **Live alerts.** Every 15 minutes it reads NASA FIRMS' public near-real-time files for South Asia (VIIRS on Suomi-NPP, NOAA-20, NOAA-21, and MODIS). No key is needed. Points inside the region box are kept. Before NASA, it reads NRSC's Bhuvan forest-fire panel (`app/bhuvan.py`, `FS_BHUVAN=0` turns it off). Bhuvan carries the same S-NPP, NOAA-20 and Aqua pixels about an hour after the pass, 1-5 h before NASA's files (docs/viirs_speed/README.md).
2. **Forest filter, FSI style.** FSI keeps only points in forest. MP beats also cover farmland, so each in-beat point gets its tree + shrub share from ESA WorldCover 10 m (read straight from the public cloud files, only the blocks needed) within the pixel footprint. Below 10% it creates no task. That keeps 93.5% of Ratapani's Feb-May 2024 VIIRS points and drops this October's farm fires: MP tasks for 7-14 Oct fell from 128 to 21. Set `FS_FOREST_MIN`, or `FS_FOREST_FILTER=0` to switch it off.
   **Mines, industry, solar mask.** As FSI does, points within 500 m of OSM mines, quarries, industry, solar farms, power plants, kilns and landfills create no task (`scripts/build_industry_mask.py` -> `data/industry_mask.geojson`). This week it took MP tasks from 21 to 18. It removed none of Ratapani's 2024 fire points.
   **Persistent heat.** A point where fire has been seen on 8 or more separate days within 400 m over the past year is treated as a static heat source (a kiln or furnace that OSM misses), and creates no task. On 12 years of Ratapani VIIRS points (8,117) it flagged none. It needs history to work, so load a year of archive points when it is set up.
3. **Beat tagging, FSI style.** Each point goes to the beat it falls in. As in FSI's FAST 3, a point whose pixel overlaps a beat junction (190 m for VIIRS, 500 m for MODIS) goes to every beat it touches. Points outside all beats are shown on the map in grey (mostly farm fires) but create no field task. Low-confidence points create no task.
4. **One task per fire, not per pixel.** Points within 1.5 km and 48 h of an unvisited alert join it. The 2024 Ratapani season had 431 usable points, which became 164 field tasks.
5. **Large fires.** FSI's rule: 3 or more adjacent VIIRS pixels in one pass. These are flagged and tracked as one fire until 3 days after the last point, even after a visit.
6. **Field visit (phone page `/field`).** A beat guard sees open alerts in their beat, nearest and overdue first, with a Navigate button. The report has what was found (fire burning / burnt, fire out / no fire / fire outside forest / controlled burn), 1 to 6 photos, and FSI's feedback fields (land type, fire type, burnt area, cause), plus action taken and crew size. Without signal, the report waits on the phone and sends itself later.
7. **Photo proof.** For every photo it keeps the phone's GPS at the moment the photo was added and the GPS and time inside the photo (EXIF). It flags `far_from_fire` (over 1 km from every point, 1.5 km for MODIS), `photo_before_alert`, `photo_reused` (same file used before), `no_location`, `no_time`, and a mismatch between photo GPS and phone GPS. Each report is graded strong, weak or none.
8. **Reached, route, and fraud checks** (from the scouting notes: Odisha, Uttarakhand, SMART, PMAY-G). While the field page is open the phone sends its position about once a minute (queued without signal). The first time it comes within 200 m of an alert's fire point the alert is marked **reached**, with time and person. The route there is drawn on the control-room map. A report filed more than 500 m from the fire is flagged. Each phone gets a device ID, and a report from a phone another staff member used in the last 30 days is flagged. 7% of visits are picked at random for an in-person re-check by the range officer (`FS_RECHECK_SHARE`). The form also asks how staff first heard of the fire (satellite alert, watchtower, villager, own patrol) and when it was put out.
9. **Control room (`/`).** Map with beats, alerts coloured by state (not visited, visit again, awaiting check, checked) and overdue rings. It has numbers for the period: alerts, % visited, overdue, median hours to visit, % with strong proof, % finding no forest fire. A range officer opens an alert, sees photos and flags, and accepts or sends it back.
10. **Ground truth export.** `Download CSV` gives one row per alert with its latest report, including an FSI-style fire yes/no column. This is the field-checked fire register the research threads have been missing.

Who sees what: a guard sees their beat, a ranger their range, an admin everything. Sign-in is name plus PIN (stored hashed).

## Run it

```
pip install -r requirements.txt
python scripts/add_staff.py --name "Your name" --role admin          # asks for a PIN
python scripts/add_staff.py --name "Guard" --role guard --beat 009-008-007
python scripts/add_staff.py --name "Ranger" --role ranger --range Delawari
python run.py                                                         # http://<pc>:8000
```

Settings are environment variables (see `app/config.py`): `FS_DATA_DIR` (database and photos, default `./var`), `FS_BEATS`, `FS_BBOX`, `FS_POLL_MINUTES`, `FS_CLUSTER_KM`, `FS_VISIT_DUE_HOURS` (default 24, the latest a visit can be due; day alerts are due the same evening and night alerts at first light). `FIRMS_MAP_KEY` is optional and only for archive pulls.

- Replay a past season: `python scripts/import_archive.py ../ratapani/viirs_snpp_2013_2024.parquet --since 2024-01-01`
- Load the real MP beat layer: `python scripts/load_beats.py E:\MP_Merge\<beats>.shp --uid DID,RID,BID --beat Beat --range Range --division Division`
- End-to-end test (against a throwaway database): `python scripts/flow_test.py`

## Files

- `app/firms.py` feed, beat tagging, grouping, large fires. `app/evidence.py` photo checks. `app/server.py` API and pages. `app/static/` control room and phone page (Leaflet bundled, so it works without CDN access).
- `data/beats_mp.geojson`: all 8,973 MP beats from `E:\MP_Merge\Mp_Beat_Merge.shp` (converted with `scripts/load_beats.py`, beat_uid = DID-RID-BID, the same IDs as `ratapani/beats/`). Used by default. `data/beats.geojson` is the older grid-built Ratapani fallback.
- A ranger account's range is `Division:Range` (for example `Guna:Fatehgarh`), because some range names repeat across divisions.
- `docs/`: screenshots.

## Not done yet

- **FSI's own forest layer** (Recorded Forest Area + forest cover) would be closer to their filter than WorldCover. Ask MP FD or FSI for it.
- **Hosting.** Staff phones need to reach the server: a small cloud VM, or Akkshay's PC with a tunnel. HTTPS is needed for phone GPS to work in the browser.
- **Pushing alerts to staff** (SMS or WhatsApp). Today staff open the page.
- **Mask coverage** is only as good as OSM. 4 Singrauli tasks remain, which may be coal seams OSM doesn't map.
- **Positions only flow while the field page is open.** A background tracker needs an installed app (Android). Mock-GPS detection also needs an app; a web page cannot see it.
- **Burn scar for each alert** is the "burn scar per alert" thread's work. The alert ID and coordinates here are the join key.
- Grouping is order-dependent at the edges: two tasks can open for one fire when its first points land more than 1.5 km apart.

## FSI's own alerts (added Oct 14)

`app/fsi_portal.py` reads FSI's open Fire Point Search portal (no login) on every poll. Each FSI alert carries FSI's beat and compartment number.
- FIRMS points that FSI also sent get FSI's tags; the alert payload has an `fsi` block with beats and compartments.
- FSI alerts that FIRMS lacks are added as `FSI_PORTAL` points.
- FSI alerts our WorldCover filter dropped still become tasks (FSI's forest mask wins). Mines and persistent heat stay out.
- Check on 3,104 FSI alerts (Nov 2025 to Oct 2026, Ratapani area): we give 97% a beat; FSI's beat is among ours for 94%, our main beat equals FSI's for 83%, same range 93%.
- Live MP week Oct 7-14: 69 tasks; 58 also sent by FSI, 14 only by FSI, 11 only from SNPP/NOAA-20 passes FSI does not use. FSI's VIIRS alerts came from NOAA-21. Before that (Nov 2025 to 26 Apr 2026) FSI used S-NPP, with its own pixel positions (median 0.25 km from NASA's), so points are matched within 0.4 km.
- `burn_hint` marks Nov-Feb daytime low-heat fires as possible controlled burns. The visit form has the cause "Controlled burning / fire line".
- Turn off with `FS_FSI_PORTAL=0`.

## Fire may have moved

The satellite point lags the real fire edge by about 380 m, and fronts in Ratapani move about 30 m an hour, day and night (fuel-map/ratapani/timing/ and inversion/ READMEs). The guard's card for an alert up to 3 days old says how far the fire edge may be from the point by now (380 m plus 30 m per hour since the last detection, capped at 2 km).

## Burn scar per alert (added Oct 14)

`app/scars.py` joins each alert's points to the burn-scar thread's lookups (`/mnt/project-files/fire-alert-scars/`: FIRMS 2017-26, FSI 2025-26, and `live/` when `scripts/live.py` runs). The result is `burn_scar` in the API and a "Burn scar" line in the range officer's alert view, next to FSI's beat and compartment. "Not visible" is never treated as a false alert.

New alerts: once a day after the alert poll, `app/scar_live.py` runs `live.py` in the background (settings `FS_SCAR_LIVE`, `FS_SCAR_AOI` default all MP beats (`fire-alert-scars/mp/mp_beats_aoi.geojson`), `FS_SCAR_LIVE_DIR` default `fire-alert-scars/mp/live`; the older Ratapani-only `fire-alert-scars/live/` is still read, `FS_SCAR_EVERY_HOURS` 24). It needs geopandas, rasterio, planetary-computer and pystac-client, and takes about 10-15 s per new fire event (about 20-40 min a run across MP in peak season). A scar seen but not yet confirmed by a later clear image shows as provisional. Alerts whose scar changed get an `alert.updated` webhook; each run is logged in `ingest_log` as `SCAR_LIVE`.

On screen: the control-room map draws each scar outline under its alert (solid = confirmed, dashed = provisional, amber = faint; dashed grey ring = no scar visible, dashed blue ring = waiting for a clear image), with a legend; opening an alert zooms to its scar. Scars are for officials to monitor, so the guard app does not show them (Akkshay, 15 Oct). An earlier guard-card design had one scar line ("Burn scar 4.04 ha, reaches 0.3 km north-west of the point") and a small north-up sketch with a scale bar; waiting and not-visible say "Please still visit". Outlines are copied once into `scar_outlines.sqlite` in the data folder (about 20 s, in the background). Under `FS_DEMO_NOW`, scars from images taken after the demo clock show as waiting. Screenshots: `docs/scars/`.

## Demo replay of a past day

`scripts/demo_replay.py 2026-04-15` loads the real FSI and NASA alerts for the 3 days up to that date into a throwaway database and adds demo accounts (admin 1111, ranger 2222, guard 3333). Start the server with `FS_DEMO_NOW=2026-04-15T12:30:00Z`: the screens then treat that time as "now", show a demo banner, and do not pull live alerts. Screenshots of 15 April 2026: `docs/demo-2026-04-15/`.

## Patrol pilot (forecast-led cell checks)

This follows protocol v3 in `research/reframe/pilot/PROTOCOL.md` (season 15 Feb-15 Jun 2027). The code is in `app/pilot.py`, and the API is in INTEGRATION.md under "Patrol pilot".

**Guard app**
- Model-picked 500 m squares appear as "Check this square". These are the ignition stream; alert visits are the response stream.
- Reaching a square counts only as "arrived". A check counts once there are 2 or more photos inside it, at least 100 m apart.
- "No fire, no fresh burn" is the answer when nothing is found.
- Every fire report asks for:
  - burn age;
  - whether it crossed a beat boundary, and which beats it touched;
  - how it was fought, and when.
- "Start day / End day" logs crew size and hours. Person-hours = shift length x crew size, with one phone per crew. They are split by stream into travel, time on site (cell entry to exit), idle, and time with no phone positions.
- "Report a fire here" records a fire found with no task.

**Never sent to the field**
- Cells near a recent fire.
- The recent-fire ranker's list, which is stored as a shadow list only.

**Dashboard**
- Squares are drawn on the map.
- Each fire report says whether there was "no nearby recent VIIRS detection" or a link to a recent alert.
- "Pilot season report" shows:
  - confirmed fire starts per 100 patrol-list person-hours;
  - where first-day fires were found (patrol list, alert visits, no task);
  - person-hours by part of the day;
  - a quick-look rate ratio (beat bootstrap, not the locked analysis).
  - It links to the per-beat CSV for the locked analysis, the shakedown gate (25 Jan-7 Feb), and the blind fire review.
- Fire reports within 500 m and 2 days with no satellite event count as one fire, credited to the first completed inspection.
- `/review` is the blind post-season review of fires where field burn age and the satellite grouping disagree: 2 reviewers, a third on a split, and a reason for each verdict.

**Settings**
- `FS_BEAT_ARMS`, `FS_RATAPANI_GRID`, `FS_RATAPANI_CELL_BEAT`, `FS_MP_GRID`.
- `FS_CELL_MARGIN_KM` (0.1).
- `FS_INSPECT_SPREAD_M` (100).

**Test and screenshots**
- Test: `scripts/pilot_test.py`.
- Screenshots: `docs/pilot/` (7-9 are the v3 review page, season report and shakedown gate).

**Likely control burns (15-28 Feb).** Officials see a "Likely control burn" tag on matching alerts, in the dashboard and the API (`control_burn`). Guards never see it, and the alert is handled as usual. The rule comes from the FSI thread and is right about half the time, and about 1 in 10 late-Feb wildfires also gets the tag. The tag is provisional for the first 3 days. Code: `app/control_burn.py`.
