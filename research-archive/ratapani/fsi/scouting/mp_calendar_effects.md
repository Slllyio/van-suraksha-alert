# Calendar effects on fire starts across all of MP: festivals, elections, weekdays, exams (scouting round 15, topic "cal", 16 Oct 2026)

This note follows up `weekday_festival_check.md`. That check used Ratapani alone and found no weekday effect and a weak Holi-eve rise (1.47x). Here the same test runs on all-MP S-NPP data, which has about 30 times more fire starts. It also covers more calendar events, a placebo test and a correction for multiple testing.

It does not repeat the mahua, tendu and Holi background in `human_fire_drivers.md` (§1.1-1.8) or `mahua_tendu_mapping.md`.

Source marks: **FULL** means I read the whole text; **PARTIAL** means I read part of it; **ABSTRACT ONLY** means I saw only an abstract, a search snippet or press coverage. Anything marked [inference] is my own reasoning.

## Headline

1. **No calendar effect passes the bar** (>1.3x, CI excluding 1, after Holm correction across 22 tests). Every Holm-adjusted p-value is 1.0. **None of these events justifies a change to the daily patrol budget on its own.**
2. **Weekday: a firm null.** Every weekday is within 0.96-1.04x, and every CI lies inside 0.91-1.10. Sunday is 0.99x (0.92-1.05). This is now well powered: 16,000 starts per weekday. **Drop weekday as a feature and as a staffing rule.**
3. **The Holi window is the only consistent signal, and it is modest and noisy.**
   - Holi eve: 1.38x (0.95-2.06).
   - Holi day: 1.29x (1.02-1.61).
   - Eve and day pooled: 1.34x (1.01-1.81), uncorrected.
   - On the night satellite pass (~01:30 IST, just after the Holika Dahan bonfires), Holi eve is 1.88x (0.96-3.58; placebo p = 0.026). In tribal-majority districts it is 2.23x.
   - Ten of 13 years had a Holi-eve ratio above 1. But the pooled figure is pulled up by 2016 (3.24x, 597 starts), and the geometric mean of the per-year ratios is only 1.03.
4. **Holi is stronger in tribal districts (ST share ≥30%).**
   - Holi day: 1.48x in tribal districts against 1.13x elsewhere; the ratio of the two is 1.31 (1.03-1.58).
   - Holi +1..+2: 1.25x against 1.07x; ratio 1.17 (1.07-1.33).
   - This is not corrected for multiple testing, but it matches the field reports ("tribal residents burn forests after Holi", Udaipur, in `human_fire_drivers.md` §1.8).
   - Ratapani's districts are low-ST: Raisen 15%, Sehore 11%. That fits the weak Holi signal we saw there [inference].
5. **Polling day in a division's own Lok Sabha seat: 1.30x** (1.00-1.65 by seat-year bootstrap; placebo p = 0.10).
   - Driven by one date: 19 Apr 2024 (Sidhi, Shahdol, Jabalpur, Mandla, Balaghat, Chhindwara) had 59 starts against 16.5 expected.
   - The other 10 polling dates are mixed: 5 above 1 and 5 below.
   - **Not robust.** The mechanism is plausible: forest staff go on poll duty. In Uttarakhand in 2024, more than 90% of field staff got poll orders. So this is a staffing-policy point, not a forecasting feature.
6. **No effect** for Mahashivratri (0.76x, n.s.), Gudi Padwa (1.03x), Ram Navami (0.98x), Akshaya Tritiya (0.91x on the day, 1.06x for the following week), Eid (0.88x), the end of class-12 board exams (1.08x for the next 3 days) or the IPL final (null check: 0.89x on the day, 1.03x the day after).
7. **The test can only detect large effects.** For a single day summed over 13 years, the null 95% range is 0.65-1.41x (sd of log ratio 0.20). Weather noise that is common across MP dominates single-day events. After correction, a real one-day effect would need to be about 1.7x or more to be detected [inference].
8. **The season is not tied to the lunar calendar.** Across 13 years, the median start date does not follow the Holi date (slope −0.25 days per day, r = −0.24, p = 0.43). Holi moved between 2 and 29 March, and the median start date stayed between 88 and 121 days into the year. A `days_since_holi` feature is therefore not worth more than a Holi-window flag [inference].
9. **Tendu collection start and mahua peak could not be tested.**
   - No per-year tendu start dates are published that I could reach. The MFP Federation site is unreachable, and news searches give only targets, bags and bonus payments.
   - Mahua peak has no dated record either.
   - A fixed-date window is removed by the 15-day running mean, which is the seasonal curve itself. These effects can only be tested with dated per-unit collection records.

## 1. Data and method (DATA, computed 16 Oct 2026)

- **Points:** all-MP VIIRS S-NPP (FIRMS SP archive) inside MP forest beats, from `mp_types/out/viirs_vtm.parquet`, 2014-2026. Type 2 (static) points are dropped.
- **New starts:**
  - A point counts as new if no S-NPP point lies within 1.5 km in the previous 3 days.
  - New points on the same day within 1.5 km of each other (single linkage) are merged into one start, timed by its earliest point.
  - Result: 120,591 starts, with 113,416 in the window 15 Feb-15 Jun. Starts per year range from 2,786 (2015) to 13,931 (2025).
  - 26% of starts are first seen on the night pass.
- **Day definition:**
  - Main analysis uses the **burning day**: IST time minus 6 h. The ~01:30 IST night pass is credited to the previous evening, which places Holika Dahan night on Holi eve.
  - The IST calendar date is a sensitivity run.
- **Expected count:**
  - The mean of the 14 neighbouring days (d−7..d+7, excluding d) in the same stratum and year.
  - Strata are division groups by dominant forest type (teak, sal, dry_mixed, degraded, north_dry, moist_mixed+bamboo), from `division_types_final.csv`.
  - Polling-day tests use the Lok Sabha seat as the stratum.
- **Rate ratio:** RR = sum of observed / sum of expected over event days.
- **Uncertainty:**
  - (a) Bootstrap over years (4,000 draws). For polling days, I resampled seat-years instead (80 units), because 3 elections are too few to resample.
  - (b) **Placebo**: all event dates in a year shifted by a common random offset (4-45 days either side), 4,000 draws. This keeps the MP-wide weather noise and is the more honest test.
  - p_use = max(bootstrap p, placebo p), Holm-corrected over the 22 tests.
- **Tribal split:** each division is mapped to its main district. Tribal means Census 2011 ST share ≥30%. This covers 45% of starts.
- **Sensitivity runs:** IST calendar day; and forest-only, which drops starts on VTM agriculture, water, settlement and scrub (16% of starts). Neither changes any conclusion.

### 1.1 Main table (burning day, all starts in beats)

| Effect | Obs | Exp | RR | 95% CI (years) | Placebo p | Holm p | Robust? |
|---|---|---|---|---|---|---|---|
| Holi eve (Holika Dahan) | 1,841 | 1,329 | **1.38** | 0.95-2.06 | 0.08 | 1.0 | no |
| Holi day | 1,789 | 1,388 | **1.29** | 1.02-1.61 | 0.14 | 1.0 | no |
| Holi +1..+2 | 3,544 | 3,069 | 1.15 | 0.82-1.44 | 0.34 | 1.0 | no |
| Holi +3..+4 | 3,582 | 3,523 | 1.02 | 0.74-1.26 | 0.93 | 1.0 | no |
| Mahashivratri | 348 | 458 | 0.76 | 0.60-1.00 | 0.24 | 1.0 | no |
| Gudi Padwa / Chaitra Pratipada | 2,124 | 2,056 | 1.03 | 0.79-1.24 | 0.87 | 1.0 | no |
| Ram Navami | 2,005 | 2,038 | 0.98 | 0.73-1.30 | 0.95 | 1.0 | no |
| Akshaya Tritiya | 840 | 919 | 0.91 | 0.75-1.10 | 0.62 | 1.0 | no |
| Akshaya Tritiya +1..+7 | 5,209 | 4,919 | 1.06 | 0.81-1.23 | 0.55 | 1.0 | no |
| Eid (Fitr 2019-26, Adha 2025-26) | 736 | 835 | 0.88 | 0.40-1.29 | 0.57 | 1.0 | no |
| Class-12 board exams end, +1..+3 | 4,318 | 4,010 | 1.08 | 0.84-1.31 | 0.56 | 1.0 | no |
| IPL final day (null check) | 214 | 240 | 0.89 | 0.67-1.09 | 0.69 | 1.0 | no |
| IPL final +1 (null check) | 239 | 231 | 1.03 | 0.64-1.56 | 0.85 | 1.0 | no |
| Polling day, own Lok Sabha seat | 232 | 178 | **1.30** | 1.00-1.65 (seat-years) | 0.10 | 1.0 | no |
| Polling day, other seats, same date | 391 | 427 | 0.92 | 0.81-1.02 | - | 1.0 | no |
| Mon / Tue / Wed / Thu | ~16.2k each | | 0.99 / 1.02 / 1.04 / 1.00 | all within 0.93-1.10 | - | 1.0 | no |
| Fri / Sat / **Sun** | ~16.0k each | | 0.99 / 0.96 / **0.99** | 0.93-1.05 / 0.91-1.00 / 0.92-1.05 | - | 1.0 | no |

**Sensitivity runs:**
- **IST calendar day:** Holi eve 1.20x, Holi day 1.41x (1.07-1.96, placebo p = 0.06), Holi +1..+2 1.21x, polling 1.30x, exam end +1..+3 1.16x. Weekdays 0.98-1.04x.
- **Forest-only:** Holi eve 1.37x, Holi day 1.28x, polling 1.34x (1.01-1.71). Everything else is unchanged.
- **Why Holi shifts between eve and day:** the excess moves from eve to day when night detections are credited to the calendar date. That means the excess sits mainly in the night pass straddling Holika Dahan night.

### 1.2 Holi by year (all MP, burning day)

| Year | Holi | Eve RR | Day RR | +1 | +2 | Eve starts |
|---|---|---|---|---|---|---|
| 2014 | 17 Mar | 0.38 | 1.03 | 0.61 | 0.61 | 4 |
| 2015 | 6 Mar | 1.50 | 0.88 | 2.26 | 0.00 | 6 |
| 2016 | 24 Mar | **3.24** | 2.10 | 0.89 | 0.49 | 597 |
| 2017 | 13 Mar | 1.09 | 1.23 | 1.76 | 1.81 | 90 |
| 2018 | 2 Mar | 1.25 | 1.95 | 1.80 | 0.65 | 77 |
| 2019 | 21 Mar | 0.74 | 1.32 | 0.84 | 0.81 | 51 |
| 2020 | 10 Mar | 1.49 | 0.47 | 0.55 | 0.98 | 10 |
| 2021 | 29 Mar | 1.08 | 1.15 | 1.61 | 1.69 | 411 |
| 2022 | 18 Mar | 1.15 | 1.03 | 0.82 | 0.58 | 147 |
| 2023 | 8 Mar | 0.11 | 0.44 | 0.54 | 1.52 | 8 |
| 2024 | 25 Mar | 1.38 | 0.80 | 0.57 | 1.08 | 142 |
| 2025 | 14 Mar | 1.18 | 1.46 | 1.20 | 1.36 | 207 |
| 2026 | 4 Mar | 1.73 | 1.04 | 1.38 | 1.08 | 91 |

- The eve is above 1 in 10 of 13 years, and the day in 9 of 13.
- Late Holis (2016, 2021, 2024) fall when the season is already active, and most of the excess comes from them.
- Early Holis (2 to 8 March: 2018, 2023, 2026) have few starts. In those years a Holi flag hardly matters.

### 1.3 Holi eve by satellite pass (`holi_night_split.csv`)

| Subset | Day | Obs | Exp | RR | 95% CI | Placebo p | Years >1 |
|---|---|---|---|---|---|---|---|
| Night pass, all MP | Eve | 663 | 352 | **1.88** | 0.96-3.58 | 0.026 | 10/13 |
| Night pass, all MP | Holi day | 525 | 377 | 1.39 | 0.98-2.10 | 0.18 | 7/13 |
| Day pass, all MP | Eve | 1,178 | 977 | 1.21 | 0.89-1.53 | 0.28 | 8/13 |
| Day pass, all MP | Holi day | 1,264 | 1,011 | 1.25 | 1.02-1.45 | 0.19 | 8/13 |
| Night pass, tribal districts | Eve | 365 | 164 | **2.23** | 0.98-4.72 | 0.017 | 9/13 |
| Night pass, other districts | Eve | 298 | 188 | 1.58 | 0.91-2.71 | 0.06 | 8/13 |

**What the Holi-eve starts look like:**
- 36% are first seen at night, against 27% across the season.
- Their median FRP is 3.4 MW, against 4.2 MW for the season.
- 14% sit on non-forest VTM classes, against 16% for the season.

[inference] So these are small night fires inside beat polygons, not more farm fires. They could be Holika bonfires in forest-enclave villages, or evening litter burning. A 1.5 km merge cannot tell a bonfire from a litter fire. The post-hoc night split is one of many cuts, so treat it as a hypothesis.

### 1.4 Tribal vs other districts (`tribal_bday_all.csv`)

| Effect | RR tribal | RR other | Ratio (95% CI) |
|---|---|---|---|
| Holi eve | 1.53 | 1.26 | 1.22 (0.88-1.51) |
| **Holi day** | 1.48 | 1.13 | **1.31 (1.03-1.58)** |
| **Holi +1..+2** | 1.25 | 1.07 | **1.17 (1.07-1.33)** |
| Holi +3..+4 | 0.98 | 1.05 | 0.94 (0.81-1.10) |
| Mahashivratri | 0.69 | 0.81 | 0.85 (0.57-1.24) |
| Gudi Padwa | 0.99 | 1.07 | 0.92 (0.78-1.06) |
| Ram Navami | 0.98 | 0.99 | 0.99 (0.86-1.10) |
| Akshaya Tritiya | 0.86 | 0.96 | 0.89 (0.77-1.05) |
| Akshaya Tritiya +1..+7 | 1.06 | 1.06 | 1.00 (0.92-1.08) |
| IPL final (null) | 1.01 | 0.77 | 1.31 (0.85-1.88) |
| Sunday | 0.99 | 0.99 | - |

- The IST calendar-day run gives the same picture: Holi day ratio 1.39 (1.10-1.59), Holi +1..+2 ratio 1.20 (1.11-1.34).
- These are not corrected for the ~10 split tests. The IPL null check also gives a ratio of 1.31 (CI spanning 1), which shows how wide single-day ratios are.
- The Holi +1..+2 result is the most stable split.

### 1.5 Polling days by date

| Election | Dates and own-seat obs/exp | Election RR |
|---|---|---|
| 2014 | 10 Apr 59/47.7; 17 Apr 7/11.4; 24 Apr 30/13.7 | 1.32 |
| 2019 | 29 Apr 31/22.8; 6 May 25/16.3; 12 May 1/9.4; 19 May 7/4.7 | 1.20 |
| 2024 | **19 Apr 59/16.5**; 26 Apr 2/14.1; 7 May 10/17.6; 13 May 1/3.9 | 1.38 |

- 5 of 11 dates are above 1. The excess comes from the eastern tribal belt's phase-1 dates (2014 and 2024) and from 24 Apr 2014 (western MP).
- [inference] This fits a staff-diversion story more than a "people burn on holiday" story. Divisions not voting that day sit at 0.92x.

### 1.6 Is the season tied to Holi? (`season_median_vs_holi.csv`, `holi_anchor.csv`)

- **Median start date vs Holi date:** slope −0.25, r = −0.24, p = 0.43 (n = 13). The earliest medians came in early-Holi years such as 2018 and 2026, but 2015 (an early Holi) had the latest median of all, 121 days into the year.
- **Poisson model** with year fixed effects, a day-of-year spline and weeks-since-Holi bins: not identifiable. Every bin's CI spans about 0.1-5x, because with 13 years the Holi shift is confounded with the seasonal curve.
- **Conclusion:** at the MP scale, weather sets the season. Holi adds at most a 1-3 day bump.

## 2. Calendar dates used (all years 2014-2026; file `code/calendar/out/calendar_dates_2014_2026.csv`)

| Event | Dates | Source |
|---|---|---|
| Holi (colour day; Holika Dahan the evening before) | 2014-03-17, 2015-03-06, 2016-03-24, 2017-03-13, 2018-03-02, 2019-03-21, 2020-03-10, 2021-03-29, 2022-03-18, 2023-03-08, 2024-03-25, 2025-03-14, 2026-03-04 | python-holidays `calendars/hindu.py` HOLI_DATES (FULL, data table); matches `human_fire_drivers.md` §1.6 |
| Mahashivratri | 02-27, 02-17, 03-07, 02-24, 02-13 (2018, outside the window), 03-04, 02-21, 03-11, 03-01, 02-18, 03-08, 02-26, 02-15 | same table |
| Gudi Padwa | 03-31, 03-21, 04-08, 03-28, 03-18, 04-06, 03-25, 04-13, 04-02, 03-22, 04-09, 03-30, 03-19 | same |
| Ram Navami | 04-08, 03-28, 04-15, 04-04, 03-25, 04-13, 04-02, 04-21, 04-10, 03-30, 04-17, 04-06, 03-26 | same |
| Akshaya Tritiya | 05-02, 04-21, 05-09, 04-28, 04-18, 05-07, 04-26, 05-14, 05-03, 04-22, 05-10, 04-30, 04-19 | Drik Panchang New Delhi listings via search snippets (2014-16, 2018-19, 2020, 2023-25); Business Today for 2026 (19 Apr; the tithi spans 19-20 Apr); 2017/2021/2022 from the Parshuram Jayanti table, so ±1 day |
| Eid al-Fitr (India) | 2019-06-05, 2020-05-25, 2021-05-14, 2022-05-03, 2023-04-22, 2024-04-11, 2025-03-31, 2026-03-21 (2014-18 fall outside the window) | Umm al-Qura table + 1 day (Indian moon sighting) [inference: ±1 day] |
| Eid al-Adha in window | 2025-06-07, 2026-05-27 | python-holidays India override (2026) |
| Lok Sabha polling, MP | 2014: 10, 17, 24 Apr. 2019: 29 Apr, 6, 12, 19 May. 2024: 19, 26 Apr, 7, 13 May (Betul moved to 7 May) | Wikipedia "2014 Indian general election in MP"; ECI schedules via news (Deccan Herald, Business Today, Drishti) (PARTIAL) |
| IPL final | 2014-06-01, 2015-05-24, 2016-05-29, 2017-05-21, 2018-05-27, 2019-05-12, 2022-05-29, 2023-05-29 (reserve day), 2024-05-26, 2025-06-03, 2026-05-31; 2020 and 2021 finals fell outside the window | Wikipedia season pages, match-60 / final date fields (FULL, data) |
| MPBSE class-12 last theory paper | 2017-03-31, 2018-04-03, 2019-04-02, 2022-03-12, 2023-04-01 (from memory, unverified), 2024-03-05, 2025-03-25, 2026-03-07 (revised timetable); 2020 disrupted and 2021 cancelled, so not used; 2014-16 not found | examresults.net timetables (2017, 2019 FULL); news snippets (2018, 2022, 2024-26) |
| Tendu collection start | **not found per year** | MFP Federation site unreachable; news gives targets and bonuses only |

**Lok Sabha seat per district:** each district is assigned the seat covering most of it (`calendar_dates.py` DIST_SEAT). Split districts (Sehore, Katni, Seoni, Chhatarpur, Khargone) carry some misclassification.

**Census 2011 ST share for all 50 districts:** Wikipedia "Tribals in Madhya Pradesh", district table compiled from the Census 2011 PCA (FULL, data). The division-to-district map is in `division_district_st.csv`.

## 3. Literature (calendar effects on fire)

| Source | Status | What it gives | Concrete action for us |
|---|---|---|---|
| Pereira et al. 2019, *Sci Rep* 9:11424, "Anthromes displaying evidence of weekly cycles in active fire data cover 70% of the global land surface" (doi 10.1038/s41598-019-47678-4) | **FULL** | MODIS 2002-2012, 42.4 M fires. Sunday is the global minimum: the Sunday mean is below 11,000 per day against more than 12,000 for Tue-Thu. Croplands hold 40.2% of fires and show the strongest cycle. The cycle is "weaker in the Seminatural anthrome and not so much as a Sunday" minimum. Earlier work found no weekly cycles in rangelands, forests and wildlands, where fire management is weaker. | Thread 1/5: this agrees with our null. Forest-litter burning in MP has no weekly rhythm (weekdays within 0.96-1.04x). No weekday feature, and no weekday staffing. |
| Earl, Simmonds & Tapper 2015, *GRL* 42, "Weekly cycles of global fires: associations with religion, wealth and culture" (doi 10.1002/2015GL066383) | ABSTRACT ONLY (Wiley PDF returned 403; press coverage) | Globally, Sunday has about 8% fewer fires than Tuesday (MODIS 2001-2013). The cycle in India and China is "not so consistent". | Our all-MP Sunday of 0.99x (0.92-1.05) is consistent. No action. |
| Earl & Simmonds 2018, *JGR-Atmos* 123, "Spatial and temporal variability and trends in 2001-2016 global fire activity" (doi 10.1002/2017JD027749) | ABSTRACT ONLY | Includes weekly-cycle tests as an index of human influence. | None. |
| Balch et al. 2017, *PNAS* 114:2946, "Human-started wildfires expand the fire niche across the United States" (PMC5358354) | **FULL** (Europe PMC XML) | 1992-2012 US records. 4 July is "by far" the most common day for human-started fires: 7,762 fires over 21 years, more than twice any other summer day. | Benchmark: a fireworks-type holiday gives about 2x. Holika Dahan night at 1.9x on the night pass is the same kind of signal, but only on the night pass and with wide CIs. Thread 5: worth one night-alert reminder, not a budget change. |
| Wang et al. 2022, *Fire* 5:215, "Effectiveness in mitigating forest fire ignition sources… China" (doi 10.3390/fire5060215), plus the 2023 correction | ABSTRACT ONLY (MDPI returned 403) | The correction notice says graves sit at forest edges, and ritual burning is "routinely carried out during the Qingming Festival and the Winter Solstice". Chinese ministry: >90% of fires are human-caused, with a Qingming rise. | Analogue for ritual-fire days. The China case targets the place (grave sites). Our analogue would be Holika sites in enclave villages, which we cannot map from satellites. |
| Newslaundry, 6 May 2024, Uttarakhand forest staff on poll duty | **FULL** | ">90 percent of forest staff in every district were issued poll orders". Nainital put forward 1,895 forest names and deployed 676, about 500 of them for 5 days. The state asked for field staff to be exempted (letters of 3 Feb and 5 Apr 2024). The Supreme Court then said forest staff and vehicles must not be requisitioned. | Threads 5/patrol: our polling-day 1.30x (not robust) fits this mechanism. For the pilot, ask MP FD whether beat staff were on poll duty on 19 Apr 2024 in the Jabalpur-Mandla-Balaghat belt. In future polls, keep fire staff exempt rather than raising the forecast. |

No published study tests Holi, Indian festivals, elections or exam dates against satellite fire counts in India. I checked web search and Crossref; Consensus had hit its monthly limit. **This all-MP test appears to be the first.**

## 4. What this means for each thread

- **Thread 1 (2-day prediction; all-MP per-division model).**
  - Do not add weekday, Sunday, Ram Navami, Gudi Padwa, Akshaya Tritiya, Shivratri, Eid, exam or IPL flags.
  - Optional: one `holi_window` flag (eve, day, +1, +2), interacted with district ST share. Expected gain is tiny: Holi eve and day together add about 70 extra starts per year across all MP beats (3,630 observed against 2,717 expected over 13 years), out of about 8,700 starts per season. Test it only inside the per-division LightGBM with leave-one-year-out.
  - `days_since_holi` is not supported (§1.6).
- **Thread 4 (spread / burn-probability maps).** No calendar input is needed.
- **Thread 5 (live alerts, patrol pilot, calendar vs forecast budgets).**
  - **Calendar budgets should be season-shaped, not day-of-week or festival shaped.**
  - The only defensible calendar adjustment is a night-watch reminder on Holika Dahan night in tribal districts (night-pass 2.2x, not robust).
  - Poll-duty days are a staffing risk, not a fire-rate signal to forecast.
- **Ratapani.** Raisen (15% ST) and Sehore (11% ST) are "other" districts. Expect the Holi bump there to be ≤1.3x, which matches the 1.47x eve and 0.83-0.90x day we saw in the sanctuary [inference].

## 5. Ranked actions

| Rank | Action | Thread | Expected gain | Effort |
|---|---|---|---|---|
| 1 | **Close the weekday question.** Remove any weekday or Sunday feature or staffing rule; cite this note (0.96-1.04x, n ≈ 16k per day) | 1, 5 | Removes a dead feature; simpler budgets | 0 |
| 2 | Keep the patrol-pilot calendar budget purely seasonal. Add only a **Holika Dahan night** reminder for tribal districts (≥30% ST) | 5 | Small; at most a few extra night starts per division per year | 1 h |
| 3 | Test `holi_window × ST share` inside the per-division all-MP LightGBM (leave-one-year-out; score with the fair 2-day rule) | 1 | ≤0.1-0.3 pt recall [inference] | 2 h |
| 4 | Ask MP FD (through Akkshay) whether field staff were on poll duty on 19 Apr 2024 in Jabalpur, Mandla and Balaghat, and push for a fire-staff exemption in the next polls | 5 | Policy, not model | Email |
| 5 | Request per-unit tendu collection start dates and bags, 2017-2026, from the district unions (Raisen, Sehore, Obaidullaganj) or the MFP Federation. Only dated records make the tendu test possible | 1, 5 | Unknown; the only untested calendar driver with a known mechanism | Slow turnaround |
| 6 | If a festival flag is kept, re-run `s2_rates.py` on NOAA-20/21 first-day starts (2018+ / 2023+) as an independent replication of Holi eve/day before trusting it | 1 | Validation | 30 min |

## Files

Code is in `fsi/scouting/code/calendar/`; outputs are in its `out/` subfolder.

**Scripts:**
- `s1_events.py`: builds the first-day starts.
- `calendar_dates.py`: all date tables, the division-district-seat map and the ST shares.
- `s2_rates.py`: main RR table and tribal split. Run as `python3 s2_rates.py bday|cday all|forest`.
- `s3_detail.py`: per-year Holi, null spread, polling by date, Holi anchoring.
- `s4_holi_night.py`: night/day pass split.

**Outputs:**
- `starts.parquet`: 120,591 S-NPP first-day starts with burning day and calendar day, 2.6 MB.
- `rr_*.csv`, `tribal_*.csv`, `holi_by_year.csv`, `holi_night_split.csv`, `season_median_vs_holi.csv`, `holi_anchor.csv`.
- `calendar_dates_2014_2026.csv`, `division_district_st.csv`, `log_*.txt`.

**Caveats:**
- S-NPP has one day pass and one night pass. Fires lit and put out between passes are missed, so these are rates of *detected* starts.
- 2014-2015 have few starts (3,692 and 2,786).
- The 1.5 km / 3-day rule will call some re-ignitions of old fires "new".
