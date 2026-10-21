# Fire alerts in eNetra: integration guide

For the eNetra team. eNetra keeps its own app, dashboard and users. This engine does the fire side and talks to eNetra over a small HTTP API and a webhook.

## Who does what

| This engine (fire alert engine) | eNetra |
|---|---|
| Pulls NASA FIRMS (VIIRS SNPP, NOAA-20, NOAA-21, MODIS) every 15 min, no key needed | Shows alerts on its dashboard and in its app |
| Pulls FSI's own alerts from FSI's open Fire Point Search portal and tags each alert with FSI's beat and compartment | Sends the alert to the beat's staff (push / SMS) |
| Keeps forest points only: ESA WorldCover tree + shrub share ≥ 10% in the pixel footprint, or FSI sent it (FSI's forest mask wins) | |
| Drops points within 500 m of mines, quarries, industry, solar, power plants, kilns (OSM) | Captures the field visit: photos, GPS, form |
| Tags each point to its beat; junction points go to every beat they touch (FSI FAST 3) | Sends the visit and phone positions to this engine |
| Groups points of one fire into one alert; flags FSI large fires (3+ adjacent VIIRS pixels) | Shows proof grade and flags to the range officer, who accepts or sends back |
| Grades the proof of each visit and marks "reached" at 200 m | Shows the weekly per-beat table |

## Auth

Every call carries `X-Api-Key: <key>`. Keys are set on the engine's server in the `FS_SERVICE_KEYS` environment variable (comma-separated). They are never stored in code or files.

eNetra users stay in eNetra. Each call passes the eNetra user ID as `staff_external_id`, and the engine creates a matching record on first use.

## 1. Get alerts

`GET /api/v1/alerts?since=2026-10-14T00:00:00Z&division=Guna&beat_uid=067-002-015&status=new`

This returns GeoJSON. One feature per alert. For `since`, pass the `generated_utc` of the previous answer: every change to an alert (new points, a report, a review or send-back, "reached") moves its `updated_utc`, so a poll misses none of them. `division` and `range_name` (`Division:Range` when the name repeats) are applied before `limit`. `view=guard` leaves out the officials-only hints (`cause_sample`, `control_burn`, `big_fire`, `direction`, `still_burning`, `runway`, `spread_24h`, `burn_scar`) for lists shown on a guard's phone; the answers to a guard's report and chance find use that view already.

```json
{"id": 17, "status": "new", "outcome": null, "lat": 25.00838, "lon": 77.14545,
 "beat_uid": "067-002-015", "beat": "Saretha", "range": "Bamori", "division": "Guna",
 "all_beat_uids": ["067-002-015"], "first_seen_utc": "2026-10-14T08:52:00Z",
 "last_seen_utc": "...", "due_utc": "...", "n_points": 1, "sensors": ["VIIRS_NOAA21"],
 "max_frp_mw": 2.1, "large_fire": false, "reached_utc": null, "first_report_utc": null,
 "fsi": {"division": "Guna", "range": "Bamori", "beats": ["Saretha"], "compartments": ["412"],
         "sent_by_fsi": true, "fsi_only": false},
 "burn_hint": null,
 "burn_scar": {"scar_found": "yes", "scar_ha": 5.88, "severity": "low", "dist_m": 185,
               "pre_date": "2025-11-03", "post_date": "2025-11-06", "event_id": "E20251104-000",
               "provisional": false, "live_status": null},
 "watch_nearby": {"radius_km": 1.0, "until_utc": "..."},
 "near_recent": []}
```

- `beat_uid` is `DID-RID-BID` from the MP beat layer (Mp_Beat_Merge.shp), zero-padded to 3 digits.
- `status` is one of: `new` (not visited), `visited` (awaiting the range officer), `verified`, `revisit` (sent back).
- `fsi` is FSI's own tagging of the same fire, or `null` when FSI has not sent it. `compartments` lets eNetra show the compartment number staff already use. `fsi_only` means FIRMS did not have the point (FSI gets some passes from NRSC that FIRMS lacks).
- FSI tags can arrive after the alert, so an alert may first come with `fsi: null` and be updated (`alert.updated` webhook, and its `updated_utc` moves) when FSI's portal catches up.
- FSI lists a junction pixel once per beat; `beats` and `compartments` carry every beat FSI sent it to.
- `burn_hint` is `possible_controlled_burn` (or `..._linear` when the pixels lie in a line) for Nov–Feb daytime fires with low heat (≤ 10 MW), the fire-line and early-burning season. It is a hint for sorting the queue. The visit still happens; staff confirm it with the cause "Controlled burning / fire line".
- `burn_scar` is the Sentinel-2/Landsat burn scar found for this alert (from the burn-scar work in `/mnt/project-files/fire-alert-scars/`), or `null` until it has been checked. `scar_found` is `yes`, `faint`, `none_visible` or `unknown`. **`none_visible` must never be shown as a false alert:** fires of ~0.15 ha, litter-only burns and burns under green canopy leave no scar a 20 m sensor can see. Show it to the range officer as support for the visit, not as a verdict. New alerts get their scar from a daily check (the burn-scar work's `live.py`, run by the engine after its poll): the first scar usually appears about 3 days after the fire (95% within 5 days). `provisional: true` means a scar was seen but no later clear image has confirmed it yet (usually confirmed within 5 days, 90% within 8); `live_status: "waiting"` means no clear image since the fire yet. Each change sends an `alert.updated` webhook.
- `due_utc` follows the field rule: a day alert is due the same evening (19:30 IST), a night alert at first light (09:00 IST), never sooner than 5 h after the pass (feeds arrive 1-6 h late) and never later than `FS_VISIT_DUE_HOURS`.
- `watch_nearby`: keep forest within 1 km of this fire on watch for 7 days. In Ratapani 93% of first burns in never-burned forest had a fire within 1 km in the week before.
- `near_recent` lists earlier alerts with a fire point within 1 km in the 7 days before this one that were not merged into it (already visited, or quiet for over 48 h): this fire most likely spread from them.
- `GET /api/v1/alerts/{id}` adds the satellite points (with forest share) and every report with photo links.

Health: `GET /api/v1/health` (same key) is the dead-man check for eNetra or an uptime monitor. `ok` is false and `problems` says why when: NASA FIRMS has had no good read in 3 h (an empty file, an HTML page or a file without the FIRMS columns counts as failed, not as "no fires"), Bhuvan or FSI (when on) has had none in 6 h, a poll has run over 30 min (a hung download) or none has finished in 3 poll intervals, points were kept unfiltered in the last 24 h because WorldCover could not be read (`forest_unknown_24h`), or a daily list is late. `poll` gives the poll thread's heartbeat and `recent_errors` the last errors from `ingest_log`.

## 2. Webhook (optional, instead of polling)

Set `FS_WEBHOOK_URL`, and `FS_WEBHOOK_SECRET` for signing. The engine then POSTs `{"event": ..., "data": <alert>}` for these events:

- `alert.updated`: a new alert, or new satellite points for one.
- `alert.reached`: a phone came within 200 m.
- `alert.reported`
- `alert.reviewed`

The `X-Signature` header is the hex HMAC-SHA256 of the body.

Events are stored before they are sent and delivered in order by one worker; while eNetra is down they wait and are retried with backoff (15 s doubling to 1 h), so none is lost. A retry after a lost answer sends the same event again: de-duplicate on `X-Event-Id` (also `id` in the body). `X-Timestamp` (unix seconds) and `X-Signature-Ts` (hex HMAC-SHA256 of `X-Timestamp + "." + body`) let eNetra reject replays: check `X-Signature-Ts` and refuse timestamps older than a few minutes. Webhooks carry the full (officials') view; filter it before showing it to guards. Changes made in the engine's own pages (`/field`, control room) are pushed too.

The service key is for server-to-server calls only: never put it in eNetra's browser or app code (the API sends no CORS headers on purpose). A browser client would need per-user tokens.

## 3. Phone positions (route + "reached")

`POST /api/v1/positions`

```json
{"staff_external_id": "enetra-u-17", "staff_name": "...", "beat_uids": ["067-002-015"],
 "positions": [{"lat": 25.0, "lon": 77.1, "acc_m": 8, "utc": "2026-10-14T15:00:00Z",
                "device_id": "android-abc", "mock_location": false}]}
```

Send about one position a minute while the guard is on duty. They can be batched, and a batch can be sent late after a no-signal stretch.

The first position within 200 m of a fire point (accuracy ≤ 100 m, not mocked) marks the alert reached. Odisha uses the same rule.

On Android, set `mock_location` from `Location.isMock()` (API 31+) or `isFromMockProvider()`. A web page cannot see this, which is one reason the eNetra native app is the better place for capture.

## 4. Field visit

`POST /api/v1/alerts/{id}/reports` (multipart)

- `staff_external_id`, `staff_name`
- `report`: JSON with these fields:
  - `outcome`: one of `active_fire`, `burnt_out`, `no_fire`, `outside_forest`, `controlled_burn`.
  - FSI feedback fields: `land_type`, `fire_type`, `area_ha`, `cause`.
  - `action`, `crew`, `notes`, `visited_utc`, `fire_out_utc`.
  - `first_known_by`: one of `satellite`, `watchtower`, `villager`, `patrol`, `other`.
  - `device_id`, `device_lat`, `device_lon`, `device_acc_m`.
- `photo_meta`: a JSON list with one entry per photo: `dev_lat`, `dev_lon`, `dev_utc` (the phone's GPS when the photo was taken) and `mock_location`.
- `photos`: 1 to 6 original JPEGs. Keep EXIF; don't recompress.

The response looks like this:

```json
{"report_id": 3, "evidence": "strong|weak|none",
 "flags": ["far_from_fire", "photo_before_alert", "photo_reused", "no_location", "no_time",
           "photo_gps_differs_from_phone", "mock_location", "reported_far_from_fire",
           "phone_used_by_other_staff", "not_auto_reached", "no_photo"],
 "distance_km": 0.05, "recheck": false, "alert": {...}}
```

Field-proven anti-fraud rules are built in. A GPS accuracy of exactly 0 m, typical of fake-GPS apps, is flagged and downgrades the proof. Accuracy worse than 50 m is flagged `gps_rough`.

A burn scar from the burn-scar-per-alert work must never mark a visit false on its own. Uttarakhand's ground-checked real fires averaged about 0.15 ha, far below what satellites map.

`recheck: true` means this visit was picked at random (7%) for an in-person check by the range officer. Show it to the range officer, not the guard.

## 5. Range officer check

`POST /api/v1/alerts/{id}/review` with `{"reviewer_external_id": "...", "decision": "accept" | "revisit", "note": "...", "report_id": 123}`

- Only an alert waiting for a check (`status: "visited"`) can be decided; otherwise 409 (reload).
- `report_id` is the newest report the reviewer looked at; when a newer one came in, 409. Send it.
- The reviewer cannot check their own report (403). Two reviewers deciding at once: the second gets 409.

Reports: send a `client_ref` (any unique string per report, e.g. a UUID made when the report is saved) in the report JSON. A resend with the same `client_ref` from the same person returns the stored answer with `"duplicate": true` and stores nothing, so retrying after a timeout is always safe. Bad input (not JSON, text in number fields, an unreadable time) gives 400 with a reason; a photo the server cannot decode gives 415; over 15 MB 413. `/api/v1/positions` needs `beat_uids` (or a beat on the staff record) and takes up to 1000 positions per call; positions with no `acc_m` or timed before the alert never mark it reached.

## 6. Weekly per-beat table

`GET /api/v1/beats/summary?days=7&division=Guna`

One row per beat:

- alerts, reached, reported, verified, overdue, large fires
- median hours to reach and to report
- counts of what staff found

## 7. Photos

`GET /api/v1/photos/{id}` (`?thumb=true` for 480 px)

## Tested

`scripts/api_v1_test.py` runs these steps against a test server: reject without key, list, positions to reached, report (strong), mocked-GPS report (downgraded to weak), accept, photo download, beat table. It does not check webhook delivery; `scripts/webhook_test.py` does (signed, ordered, redelivered after the receiver was down). `scripts/run_tests.py` runs every server test on its own fresh demo database.

## Optional feed: Sentinel-3 morning and night fires (not built yet)

EUMETSAT's Sentinel-3 SLSTR fire product (Data Store collection EO:EUM:DAT:0417) gives 1 km fire pixels from passes over MP at about 10:20-10:50 IST and about 22:00 IST, roughly 2 h after the pass. It would add a morning alert that the current feeds lack (FSI's MODIS alerts are all from the afternoon Aqua pass). It needs EUMETSAT Data Store keys, which will be set as `EUM_KEY` / `EUM_SECRET` in the environment settings. Once they exist, the engine can poll the feed like FIRMS and add its points as source `SLSTR`. The keys do not cover Meteosat (LSA SAF), which needs a separate account. Measured on 2025+ data: the 10:30 IST pass matches FIRMS 72-75% of the time but gives only about 20-40 hits near Ratapani per season (use FRP > 10 MW and n_cloud = 0); the 22:00 IST pass is real fire and arrives about 2 h after sensing. A ready puller exists at `ratapani/fsi/scouting/code/slstr/pull_slstr_frp.py`. Low priority.

## Open questions for eNetra

1. How does eNetra prefer to get alerts: polling `/api/v1/alerts`, or the webhook?
2. Does the eNetra app already send push notifications or SMS to beat staff, and keep a staff-to-beat list? If yes, the engine only supplies `all_beat_uids`.
3. Where should the engine run: next to eNetra on the same server, or separately behind HTTPS?
4. Does eNetra already have MP forest boundaries (RFA)? Those would be a better forest filter than WorldCover.
5. Does eNetra already have the MP FD compartment layer (reportedly on MP FD's ArcGIS server)? With it the engine can tag compartments for alerts FSI does not send (SNPP and NOAA-20 passes).
6. Should eNetra's fire registers follow the NTCA fire audit format (fire-line km cleaned, controlled-burn area against the TCP, watchers, towers)? The engine can count controlled burns confirmed in the field per beat for that.

## Patrol pilot: cell checks, chance finds, crew-day log (protocol v2, 15 Oct 2026)

These follow `research/reframe/pilot/PROTOCOL.md` (v2, section 0). The pilot season is 15 Feb-15 Jun 2027, and everything is locked by 1 Feb 2027.

Every item in `/api/v1/alerts` has `kind` and `stream`. Filter with `?kind=`.

| kind | what it is | stream |
|---|---|---|
| `predicted` | a check task for one 500 m cell | `ignition` (this is what differs between the arms) |
| `alert` | a satellite-alert visit, the same in every arm | `response` |
| `chance` | a fire staff found with no task | none |

**Cell check tasks: `POST /api/v1/tasks`** (send each evening)
```json
{"issue_date": "2027-03-02", "grid": "ratapani",
 "model_version": {"model_hash": "<sha256 of the model files>", "code_commit": "<git commit of the feature and scoring code>",
                   "config_hash": "<sha256 of thresholds, 1.5 km / 3-day rule, budget scaling>", "data_cutoff_utc": "2027-03-02T12:00:00Z"},
 "tasks": [{"cell_id": 3288, "score": 0.91}, {"cell_id": 3310}]}
```
- **Version record (required):** `model_version` must have model_hash, code_commit, config_hash and data_cutoff_utc. Otherwise the call is refused (400). It is stored on each task and returned as `task.model_version`.
- `grid` is `ratapani` (`ratapani/grid_500m.geojson`) or `mp` (`ratapani/mp_grid`). The cell polygon and the beat come from the grid.
- `arm` comes from the beat in `research/reframe/pilot/beat_arms.csv`.
- **Cells near a recent fire are never sent.** A cell with a satellite point within 1.5 km in the 3 days before issue is not created, in any arm. It comes back in `excluded_near_active`, because the response stream covers it.
- **Only ignition-stream tasks are accepted.** Any other `stream` is refused.
- The window is day t+1 06:00 to day t+2 19:30 IST.
- Re-sending the same list creates nothing new.
- Each new task fires a `task.created` webhook.
- **Shadow lists:** `"shadow": true, "list_name": "recent_fire_ranker"` stores a list (with the same version record) for scoring after the season. It creates no tasks and sends nothing.

**Arrival vs inspection**
- **Arrived** = a phone position inside the cell.
- **Inspection completed** = a report with at least 2 geotagged, timestamped photos inside the cell, at least 100 m apart (`FS_INSPECT_SPREAD_M`), plus an outcome.
- Each cell report gets `inspection`: `completed`, `arrived` or `not_shown`.
- Arrivals without a completed inspection are flagged (`arrived_not_inspected`). They are not credited as checks.

**Report fields** (all report endpoints)
- `outcome: nothing_found` = "No fire, no fresh burn". It is for cell checks only and is never a false alert.
- `burn_age`: `now` / `1_2_days` / `older`.
- `crosses_beat_boundary`: `yes` / `no` / `unknown`, plus `beats_touched` (free text).
- `suppression`: `none` / `fire_line` / `beating` / `water` / `counter_fire`, plus `suppression_utc`.
- `linked_alerts` (set by the engine): satellite alerts with a point within 1.5 km in the 3 days before the visit.
  - Empty = "no nearby recent VIIRS detection". That is not proof of a new ignition.
  - A fire is called **new** only when the field burn age (now or 1-2 days) agrees with no linked alert.
- `stream` (set by the engine): `ignition` for cell checks, `response` for alert visits.

**Chance finds: `POST /api/v1/chance_finds`**
- Takes the same multipart form as a report, with `device_lat` / `device_lon` required.
- It creates a `chance` item at that spot, with the arm of the beat it falls in.

**Crew-day log: `POST /api/v1/shifts`**
- Send `{"staff_external_id", "beat_uid", "action": "start" | "end", "crew_size", "utc", "lat", "lon"}`.
- **Staff-hours per stream:** within a logged day, the time up to each report goes to that report's stream. Travel therefore counts for the task reached next.
  - Time after the last report goes to the last report's stream.
  - A day with no task report is `unassigned`.

**Season report: `GET /api/v1/pilot/report?start=2027-02-15&end=2027-06-15`**
- **Primary, per arm:** verified fires with no nearby recent VIIRS detection, found by ignition-stream checks (completed inspections only), per 100 ignition-stream staff-hours.
  - Reported as `rate_ratio_vs_fixed`, with a 95% bootstrap over beats within each arm.
  - "Verified" = the range officer accepted the report and its photo proof is strong.
- **Secondary:**
  - forecast vs calendar ratio (reported, not claimed);
  - ignition-stream inspected, arrived only, not reported, nothing found, fires found, fires that are also new by burn age;
  - response stream: alerts visited within 2 days, pending, missed, missed with a burn scar, fires found, staff-hours;
  - chance finds;
  - a spillover list (fires crossing beats, suppression with its time) for the sensitivity analysis;
  - the stored shadow lists.
- The same tables are on the dashboard under "Pilot season report".

### Protocol v3 additions (15 Oct 2026, PROTOCOL.md sections 0.2, 0.3 and 0.6)

**Person-hours**
- Person-hours = shift length x crew size. One phone logs the crew. If each person logs their own day, each enters crew size 1, so nobody is counted twice. The guard app now asks for crew size at "Start day" and refuses a blank.
- Each shift is split into `travel`, `on_site`, `idle` and `no_positions`, per stream:
  - `on_site` runs from cell entry to cell exit (alert visits: from arriving within FS_ARRIVE_KM to leaving). Both times are stored on the report as `site_entry_utc` and `site_exit_utc`. They are recomputed when late positions arrive from a phone's offline queue.
  - Off site, moving at 1 km/h or more between two fixes is `travel`; slower is `idle`.
  - Fixes more than 30 min apart leave the time as `no_positions`, so the parts always add up to the person-hours.
  - Stream rules are unchanged: time on site goes to the task's stream, travel and waiting to the next task's stream, the trip back to the last task's stream, and a shift with no task is `unassigned`.

**Shakedown gate: `GET /api/v1/pilot/shakedown?start=2027-01-25&end=2027-02-07`** (also `/api/pilot/shakedown` and a dashboard button)
- Per arm, it reports three shares and whether each passes:
  - shifts with start, end and crew size (ended by the user, not auto-closed): need 95% or more;
  - on-duty time covered by phone positions with gaps under 30 min: need 90% or more;
  - unassigned person-hours: need 5% or less.
- It also lists incomplete shift logs, and overlapping crews in one beat where people may be counted twice.

**Unique fires**
- Every fire report gets a `fire_id` (provisional).
  - A fire on or next to a satellite event takes that event's id (`S` + the earliest alert id).
  - Otherwise, reports within 500 m and 2 days of each other are one fire (`F` + the first report's id).
- Each fire is credited once:
  - to the first completed inspection that found it (ignition stream);
  - otherwise to the first alert visit or chance find.
  - A fire seen only on arrival, with no completed inspection, is counted as `found_not_credited`.
- The class follows the table in section 0.2: `confirmed_start`, `continuation`, `older_burn` or `unclassifiable`.

**Post-season grouping: `POST /api/v1/pilot/grouping`**
```json
[{"fire_id": "F412", "grouping": "no_satellite_event", "est_ignition_utc": "2027-03-04T05:10:00Z"},
 {"fire_id": "S9031", "grouping": "separate_fire", "fire_first_utc": "2027-03-04T08:00:00Z", "chips": [{"label": "before", "url": "https://..."}]},
 {"fire_id": "F433", "merge_into": "F412"}]
```
- `grouping` is `no_satellite_event`, `same_fire_as_alert` or `separate_fire`.
- `est_ignition_utc` is the FSI method's ignition time. It gives time to discovery.
- `merge_into` joins two provisional fires.
- `chips` are before/after image URLs shown to reviewers.

**Blind review (`/review`; API `GET /api/review/fires`, `POST /api/review/fires/{fire_id}/verdict`)**
- The queue holds rows 2 and 3 of the table, where field burn age and the grouping disagree. Admins can add any fire with a reason.
- Each case shows the photos, photo and phone times, burn age, nearby satellite points with their burn scar, and any chips.
- It hides the arm, beat, task source and other reviewers' verdicts.
- Two reviewers decide; a third settles a split. Every verdict needs a reason, and the reasons are stored as `final_reason`.

**Season report (v3)**
- Per arm, `fires` gives confirmed starts found by (a) `ignition`, (b) `response`, (c) `chance` and (d) `total`. It also gives continuations, older burns, unclassifiable fires, fires waiting for review, `found_not_credited`, and the median `time_to_discovery_h` per stream (when `est_ignition_utc` was imported).
- `person_hours` breaks each stream down by part, and `unassigned_share` is reported.
- **Primary:** confirmed starts from completed ignition-stream inspections that the range officer accepted, per 100 ignition-stream person-hours. Rejected reports (sent back to revisit) never count.
  - Sensitivities: unassigned hours shared out, all person-hours, unclassifiable fires counted as starts, and no acceptance required (`per_100_no_acceptance_required`, which counts reports still unreviewed at season close).
  - `fires.confirmed_starts_accepted` holds the accepted counts; `fires.confirmed_starts` counts with no acceptance required.
  - `rate_ratio_vs_fixed` is labelled "beat bootstrap, not the locked analysis".
- **Per-beat table: `GET /api/v1/pilot/beats.csv?start=&end=`** (also `/api/pilot/beats.csv`)
  - One row per pilot beat: `beat_uid, block, arm`, accepted starts by stream (`starts_<stream>`), starts with no acceptance required (`starts_<stream>_no_acceptance`), unclassifiable fires, fires waiting for review, ignition tasks and inspections.
  - It also gives `ph_<stream>_<part>` person-hours for streams ignition / response / unassigned and parts travel / on_site / idle / no_positions, plus totals.
  - The block-randomisation analysis runs from this file.
- `block` from `beat_arms.csv` is also a column of `/api/export/incidents.csv`, together with `fire_id`, `site_entry_utc` and `site_exit_utc`.


### Protocol 0.9 additions (16 Oct 2026, exploratory deterrence: recorded, not tested)
- Two optional fields on every report endpoint, asked on cell inspections in the guard app:
  - `people_met`: a whole number from 0 to 500;
  - `enforcement`: `none`, `warning` or `fir_por`.
- The season report has an `effort` block per arm:
  - `person_hours_per_km2_per_week`: all person-hours ÷ the arm's forest km² ÷ the weeks in the date range. Beat forest area comes from `beat_arms.csv`: `forest_km2` if that column exists, otherwise `cells` × 0.25 km².
  - Completed inspections, the median minutes on site (from `site_entry_utc` / `site_exit_utc`), people met, warnings, and FIR/POR counts.
- Both fields are also in `/api/export/incidents.csv`.

### Likely control burns, 15-28 Feb (16 Oct 2026, Akkshay chose "tag only")
- Alerts in `/api/v1/alerts` carry a `control_burn` field. It is null unless the rule matches, and then holds `{likely_control_burn, provisional, recheck_after_utc, note}`.
- The rule is the FSI thread's (`ratapani/fsi/scouting/code/early_burns/control_burn_rule.py`, about half are control burns in a held-out test (30-70% by season), and about 1 in 10 late-Feb wildfires also gets the tag). It tags an alert that is daytime only, has at most 2 points, has a highest FRP of 5 MW or less, has no night point within 1.5 km that fire-day, and has no other point within 1 km from 2 days before to 3 days after.
- Until those 3 days are over, the tag is provisional.
- FSI-only alerts are not judged, because FSI points carry no FRP.
- **Show it to officials only.** It changes nothing for guards: the order, the due time and the alert itself all stay the same.

### Cause check on late-Feb alerts, from the 2027 season (17 Oct 2026, Akkshay said yes)
- This is the only way to learn how often the tag is right. Crews record the cause on every tagged alert, and on an untagged comparison sample of about the same size.
- Alerts carry `cause_required` (true/false). Show it to the guard. When it is true and the outcome is `active_fire` or `burnt_out`, the report must include `cause`; otherwise the API answers 400. "Unknown" is accepted. A `controlled_burn` outcome fills the cause in itself.
- `cause_sample` is for officials only: `{group: tagged | random | none, p}`. `p` is the chance an untagged alert was drawn, for weighting. **Never show the group to guards**, so they don't know which alerts the rule suspects.
- How it works:
  - It covers 15-28 Feb IST alerts from 2027 on (env `FS_CAUSE_FROM_YEAR`).
  - The group is decided once and stored on the alert (`incidents.cause_group`, `cause_p`, `cause_required`; also in the CSV export).
  - Untagged alerts are drawn by a hash of the alert, with p = tagged so far / untagged so far this season.
- Test: `scripts/cause_check_test.py`.

### Big-fire points at alert (on, 18 Oct 2026: Akkshay chose "rank only, no %" and asked that guards be told)
- **For guards:** alerts carry `big_fire_flag` (true/false) and `big_fire_text`. When the flag is true, show the text on the alert: "May become a big fire. Go with extra crew if you can, and tell your range officer when you reach it."
  - The flag is set at 12 points or more (env `FS_BIG_FIRE_GUARD_POINTS`).
  - In the 2025-26 replay that was 3-6 new fires a day statewide. About 1 in 4-5 of them passed 200 ha, against 2-4% of all new fires.
  - The flag does not change the alert's order or due time.
- **For officials only:** `big_fire` holds:
  - `{new_fire: false, note}` for an alert that continues a fire seen in the last 30 h;
  - otherwise `{new_fire: true, points, items: [[label, points]], division, first_look_utc, guard_flag, farmland_checked, note}`.
- **No % is sent.** Use the points to order the day's new fires.
- The points are scored once, on the first VIIRS look of a new fire, from the research points table (`app/big_fire.py`).
- `FS_BIG_FIRE=0` turns all of this off. Replay results are in `docs/big_fire_replay/README.md`.

### Search radius per alert (18 Oct 2026)
- Alerts carry `search_m`, the distance to search around the point, on all sides. Show it to the guard.
- It is half the largest pixel of the latest pass plus 100 m, from FIRMS `scan`/`track` (big-fires README section 15d). That is about 300 m near the middle of a VIIRS pass and about 500 m at the swath edge.
- It replaces a fixed 300 m. The built-in field app also adds about 30 m for each hour since the last pass, for spread.

### Direction hint from a 30 m scene (18 Oct 2026, Akkshay said yes to the Big fires hand-over)
- **Officials only:** alerts carry `direction`, null unless a Sentinel-2 (or Landsat) scene from the last 3 days caught the fire burning. Otherwise `{heading, bearing_deg, sensor, scene, scene_utc, burnt_ha, text, note}`, e.g. "Heading N (from the 30 m Sentinel-2 scene of 23 Apr 10:56 IST)".
- Arrow = centre of the burnt patch to centre of the 30 m hot line (big-fires README 15e-15f, `app/direction.py`). Show it as a hint only; it never changes the alert, its order or the search area. Guards do not get it: they keep searching on all sides.
- Checked in the app on 78 past MP fires (`scripts/direction_check.py`, rows `docs/direction_check_rows.csv`): within 45 deg of where the scar grew next 68% of the time (58-78), against 25% by chance; the research got 62% on the same fires.
- **Re-tested at real arrival time (20 Oct, research/big-fires/results/arrow_at_arrival.md):** the scene is published about 16:00-17:00 IST, after the 13:30 IST VIIRS pass is in. Against burning after it arrives, the arrow is right 58% of the time and the VIIRS dots including that afternoon look are right 56% (difference +2 points, CI -6 to +11; 143 passes). So the arrow adds about nothing live; the 65% vs 47% above gave the dots only the morning looks.
- How often and when: about 12% of fires get one (two thirds of 50+ dot fires); the scene is taken about 10:30 IST and is ready a few hours later, so the hint arrives as an afternoon/evening update, not on the first alert. Landsat reaches Planetary Computer about 40 days late, so live hints are Sentinel-2.
- The server checks alerts seen by VIIRS in the last 3 days every 6 h on its own thread (Planetary Computer, no login). `FS_DIRECTION=0` turns it off.

### Still-burning chance for a fire VIIRS stopped seeing (18 Oct 2026, fire-continuity hand-over)
- **Officials only:** `still_burning` is null while the last VIIRS dot is under 6 h old; then `{hours_dark, chance, last_viirs_utc, text, note}`: 6-12 h 62%, 12-24 h 33%, 24-48 h 16%, 48 h+ 9% (`app/still_burning.py`). From 1,505 30 m scenes of Ratapani fires; a pass with no fire does not mean the fire is out. It never closes or holds back an alert.

### Which side of a new fire likely burns farther (18 Oct 2026, Akkshay's ask; research/runway-statewide/README.md)
- **Officials only:** `runway` is null unless a new fire's first VIIRS look has been scored. Otherwise it is `{open, stop, text, note}`, e.g. "Likely to burn farther toward the NW (forest, uphill); least toward the E (forest edge 180 m)".
- **Accuracy:** in a statewide test (4,104 fronts, held out by tiger reserve) the named side burned farther than the least likely side 67% of the time, against 50% by chance and 58% for "most forest". Show it as a hint only.
- **Inputs:** terrain (Copernicus DEM 30 m), ESA WorldCover, Overture roads (`data/runway/mp_roads_40m.tif`) and the front's own dots. It is scored on the server's background thread (`app/runway.py`). `FS_RUNWAY=0` turns it off.
- It can disagree with the 30 m `direction` arrow. The arrow is observed later from a scene of the actual fire; this hint is a forecast made at the first look.


## Officials' daily brief (18 Oct 2026)
`GET /api/v1/brief?division=<division>&day=<YYYY-MM-DD IST>` returns one division's brief at 16:00 IST: counts, the last
7 days vs the 2014-25 normal, new fires ordered by big-fire points (with runway, arrow and still-burning hints), fires lost
from view, alerts not visited past due, and a per-range table. Without `division` it returns every division with open
fires, busiest first. Officials only; it does not change what guards see. Details: docs/brief/README.md.

## Weekly scar check (18 Oct 2026)
`GET /api/v1/scar_check?division=<division>&day=<YYYY-MM-DD IST>` returns the week that ended 7 days before `day`.
For each range it gives: alerts, how many left a burn scar, the scar share, hectares burnt (overlapping outlines
merged) and the largest scar. It also lists visits that said "no fire" where a clear scar was found. Officials only.
"No scar visible" is never a false alert. Details: docs/scar_check/README.md.

## Same-day 30 m arrow from Copernicus Data Space (18 Oct 2026)
When the Sentinel Hub Process API on CDSE answers (an "OAuth 2.0 client credentials" environment secret for
sh.dataspace.copernicus.eu, token URL https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token;
or `CDSE_CLIENT_ID`/`CDSE_CLIENT_SECRET` env vars on a server without such a proxy), the arrow also looks at
Sentinel-2 scenes from Copernicus Data Space. CDSE lists them about 5 h after the pass; Planetary Computer can take more
than a day. Same-day arrows are re-checked every 2 h, not 6. Without it nothing changes (checked once an hour). After adding it,
run `python scripts/cdse_check.py` once; it checks that CDSE and Planetary Computer pixels agree on the same scenes.

## Faster points from NRSC's Bhuvan panel (19 Oct 2026, Akkshay chose "Add Bhuvan")

The engine reads NRSC's Bhuvan forest-fire panel at every poll, before NASA. The panel lists S-NPP and NOAA-20 VIIRS (375 m) and Aqua MODIS passes about an hour after the pass: VIIRS 40-62 min and Aqua 18 min on 18-19 Oct 2026. NASA's files take 1.7-2.8 h at night and 4.5-6 h by day.
- **Same pixels:** Bhuvan points match FIRMS to within a median of 15-65 m.
- **First, then filled in:** a Bhuvan point opens the alert first, with `source` `BHUVAN`. When FIRMS sends the same pixel, the point takes FIRMS' FRP, confidence, position and scan time, and no second point is added. A neighbouring pixel or another satellite is still its own point.
- **What eNetra sees:** an alert can appear with `frp` 0 for about 1-5 h, until FIRMS fills it in.
- **Order at every poll (Akkshay, 19 Oct 2026): Bhuvan, then FSI's portal, then NASA.** FSI's alert for a pixel Bhuvan already sent only adds FSI's beat and compartment to it; an FSI alert Bhuvan lacks opens its own point; NASA comes last and fills both kinds of row (check: `scripts/source_order_test.py`).
- **What Bhuvan lacks:** NOAA-21, Terra and points outside NRSC's forest mask still come only from NASA.
- **Past days:** on 6 days of the 2026 dry run, Bhuvan's archive (NOAA-20 only) would have made 43% of alerts known about 4 h sooner. The median time from first satellite look to a known alert fell from 5.0 h to 2.2 h.
- **Reliability:** the panel is a public web page, not an API, and about 1 request in 4 fails, so calls retry. If Bhuvan is down, alerts simply come from NASA as before.
- **Code and tests:** `app/bhuvan.py`; test `scripts/bhuvan_test.py`; `FS_BHUVAN=0` turns it off.

## Officials' 2-day check list: statewide pool + 50% floor + 35% quiet reserve (19 Oct 2026; 35% from 21 Oct, Akkshay "ok go ahead")

This is the final daily rule from `research/ceiling/DAILY_RULE_SPEC.md`, built in `app/daily_list.py`.

**What the pipeline sends.** Each day it posts that day's division-model scores for every mp_grid square to `POST /api/v1/daily_scores`:
- `issue_date`, `model_version`;
- `cell` (the mp_grid ids);
- `pct` (calibrated chance, using the previous season's calibration only);
- `score` (the raw score).

Optional fields:
- `counts` {division: n}, the danger-scaled count per division. Without it the engine computes the count itself: 10% of the division's squares, times today's mean score divided by the season's mean daily score up to yesterday. The share is clipped to 1-40%, and is a plain 10% in the season's first week. The result is multiplied by k (`FS_DAILY_K`, 0.5844), which keeps the ground flagged the same as the tested rule's.
- `base_share` {division: share}, last season's overshoot shrink.

Sending the same day again replaces that day's list.

**The rule.** The step order follows the PC's tested rule (van-suraksha-alert PR #1, `mp/README.md`, "Live combined rule"; results in `mp/results/officer/live_*`):
1. **Total.** The day's total is the sum of the division counts, so the workload is the same as the per-division rule.
2. **Floor.** Each division keeps ceil(half) of its count. Of those, 35% go to its quiet squares and 65% to the others, each by score. Spare slots move between the two when one side runs out.
3. **Pool.** The rest of the total goes statewide by calibrated %: 35% to quiet squares and 65% to others, again with spare slots moving.

A quiet square has no VIIRS point within 10 squares (5 km, measured as a box, as in the PC's rule) in the 7 days before the 16:00 IST issue time. The engine works this out from its own points, so the pipeline doesn't need to send it. Ties go to the raw score.

**Settings.** `FS_DAILY_RULE=division` makes each division fill exactly its own count instead. `FS_QUIET_SHARE` (0.35) and `FS_DAILY_K` (0.5844) are the quiet share and the count multiplier; change them together (25% goes with k 0.6032).

**What eNetra gets.**
- `GET /api/v1/daily_list?division=&day=` returns the division's squares with %, beat and range. Each square has a `reason`: "division", "quiet square" or "statewide".
- The daily brief gains a "Check in the next 2 days" section with counts by reason and by range.
- Guards' beat alerts do not change.

**Big-fire watch list (separate layer, officials only).** Akkshay, 20 Oct 2026: "keep the daily list, and add the big-fire model as a separate short watch list of the top 1-2% of squares."
- `POST /api/v1/big_watch_scores` takes issue_date, cell, division, rank_in_division, top1 and top2 from `research/large-fires/watch/big_watch.py`. `scripts/cloud_daily.py` sends it each evening.
- `GET /api/v1/big_watch?division=&day=` returns the division's squares above its fixed season cut, best first (since 21 Oct 2026; the count changes with the day, about 5,600 statewide on a peak day). Each square has a rank, a tier (1 = above the stricter cut, 2 = the rest), its beat and its range. There is no %, as for the big-fire points (18 Oct).
- The same nightly body also carries `size_cell` + `size_score` for every square: the chance that a fire starting there passes 200 ha. The app keeps the last 3 nights.
- **Officials' order of new fires** (`FS_NEWFIRE_ORDER`, default `combined`): it uses the big-fire points of the first VIIRS look together with the highest size score of the first-look squares (3 x 3) from the night before. It falls back to points when no size score arrived that night. On the app's replay, fitted on 2025 and tested on 2026, it scores 0.87 against 0.80 for points and 0.84 for size alone, and puts 52% of 200 ha+ fires in each day's top 10% of new fires, against 42% and 39%. `big_fire.order_basis` says which was used. The order value is never shown. Guards' 12+ points flag is unchanged.
- It never changes the 2-day list or guards' alerts. With the fixed cuts from 2025 (`research/large-fires/watch/cuts_2025.json`, refreshed each June from the season just ended), 2026 caught 64% of 200 ha+ fires against 46% for the daily top 1-2%, on 3.3% of the ground against 3.5% (Akkshay chose this on 21 Oct). It is a list for watchers and readiness, not for sending a crew to every square.

**Checked.** `scripts/daily_list_test.py` ran on 22 Apr 2026 with stand-in scores (real scores stay on the PC):
- 37,368 flags, equal to the day's total;
- every division got at least half its count;
- 35% of the pooled flags went to quiet squares (25% when checked on 19 Oct);
- the `division` fallback gives each division exactly its count;
- the run takes about 15 s for all 373,681 squares.

The catch rates (71/68% of fires, 46/48% of brand-new fires, 83/82% of beats) are the PC's results; this test does not measure them.

**Checked against the PC (19 Oct 2026, `pc_check/`).** The PC sent 5 days of 2026 (12 and 17 Mar, 5 and 22 Apr, 10 May): its scores, its division per square, its counts and the squares its own rule flagged.
- **Same squares:** the app, working out quiet squares from its own points, picked 99.8-99.9% of the PC's squares on every day. The same total was flagged each day, and no division fell below half its count.
- **Quiet squares:** the app's quiet squares were identical to the PC's.
- **The few differences:** all are squares with the same calibrated %, where the app breaks the tie by raw score.
- **The pipeline should send `division` and `counts`:**
  - About 8% of the PC's flags fall on squares outside the beat map.
  - Boundary squares are scored once by each division holding them.
  - The PC's counts carry a scale factor (k = 0.603) and last season's shrink, so the share flagged swings from 2.5% to 20.6% of squares a day. The app's own fallback count does not reproduce that.
- **Results:** `pc_check/app_vs_pc.csv`.

## 24 h spread map (19 Oct 2026)

`GET /api/v1/alerts/{id}` carries `spread_24h`: a GeoJSON Feature (WGS84) of the ground likely burnt 24 h after the fire's latest
VIIRS look, or null when that look is over 24 h old. Properties: `from_look_utc`, `valid_until_utc`, `area_ha`, `extra_ha`,
`radius_m`, `rule_extra_ha`, `method`, `model` (`ratapani` near Ratapani, else `mp`: trained on Ratapani + 2,600 MP fires, docs/spread24/MP_RETRAIN.md), `zero_frp_dots`, `note`. Officials only: do not show it to guards. Replay on 818 unseen
fires: overlap with the scar 0.460 vs 0.447 for the old rule (docs/spread24/README.md). Recomputed on every request (under 1 s).
