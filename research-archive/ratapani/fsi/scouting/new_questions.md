# New questions the scar record can still answer (20 Oct 2026, Akkshay "u tell me what can be new questions")

Prevention from orbit is exhausted (control_burning.md sections 9-14). These are the questions left that nine seasons of burn outlines, VIIRS heat and the GIS layers can answer, ranked by what they would change. Code `code/newq/`.

| # | question | what it would change | status |
|---|---|---|---|
| 1 | Does a February fire damage the forest less than a late-March one? (burn severity from the scars) | whether the 108k ha "converted to cool burns" in the plan is worth anything | **done, section 1: no difference visible from orbit** |
| 2 | Which divisions are getting better or worse over nine seasons, against the state? | where management is working, where to look first | **done, section 2: 1 improving (Satpura TR), 8 worsening, mostly the Bundelkhand dry belt** |
| 3 | Why did some repeat patches cool (Noradehi, South Betul, Barwah, Indore) while others held? Land-cover or greenness change on cooled patches vs held ones | whether cooling is protection or land-use change; which patches to drop | done: no land change; cooled patches are the reachable ones (section 3) |
| 4 | Which side of each patch is downwind in late February (ERA5 10 m wind, 2017-25), for the block-burn order | the burn order per patch in the plan | done: wind side is random for escapes (53% vs 50%); large escapes go uphill and toward often-burnt forest (61%), section 4 |
| 5 | Ignition calendar beyond Holi: weekday, market day, tendu and mahua fortnights, by division | when watchers should be on the ground | done: null, no division has a weekday effect (0 of 68), section 5 |
| 6 | Wet-season recovery after fires of different dates (HLS peak greenness the following monsoon) | the ecology question, as far as orbit can see it | done: no trace of the fire in next-monsoon peak greenness, whatever its date (MODIS, 2025), section 6 |

## 1. Burn severity by fire date: no difference (`n1_severity.py`, `out/n1_severity.csv`)

127,015 forest fires 2017-25 with a scar and an RdNBR (relativised burn ratio, median over the scar, from the all-MP scar run). The median RdNBR is 0.127 for fires started 15-28 Feb, 0.128 for 1-15 Mar, 0.125 for 16-31 Mar, 0.123 for 1-15 Apr, 0.131 for 16-30 Apr; within division-year the differences are 0.00-0.01; 99.2% of all fires are "low" severity, 0.04% "high". The same by forest type (sal, teak, dry mixed, degraded) and by fire size (under 10 ha to 200 ha+). In 45 of 70 divisions the February median is below the late-March median, by a hair.

- These are litter fires under a canopy that is not burnt; the optical scar sees the blackened ground, not a hotter fire. The 30% lower fire power and the smaller size of February fires (control_burning.md section 3) do not show up as a milder scar.
- **For the plan:** from orbit a February burn and an April wildfire leave the same mark. The case for "cool burns" rests on the heat and size record, not on visible damage; whether a hotter litter fire hurts regeneration more is not something the scars can say. Question 6 (greenness the next monsoon) is the only satellite angle left and is unlikely to see more than this.

## 2. Who is getting better, who worse (`n2_trend.py`, `out/n2_trend.csv`, `figs_r30/r30_fig9_trend.png`)

Per division, burnt forest share per season 2017-25 relative to all MP that season (which removes the weather year), trend over the nine seasons, p by permutation of the season labels (999); a division counts only if the VIIRS point series 2014-26 (S-NPP, same construction) moves the same way. About 4 of 82 divisions would pass p < 0.05 by chance; 9 do.

| division | burnt share 2017-19 | 2023-25 | change per year, scars | p | change per year, VIIRS | verdict |
|---|---|---|---|---|---|---|
| Satpura TR | 9.9% | 2.9% | -13% | 0.010 | -12% | improving |
| Damoh | 7.2% | 10.4% | +14% | 0.004 | +9% | worsening |
| South Panna | 5.9% | 8.7% | +15% | 0.006 | +17% | worsening |
| North Sagar | 6.9% | 7.2% | +8% | 0.019 | +14% | worsening |
| Vidisha | 7.8% | 6.5% | +5% | 0.044 | +7% | worsening |
| FDC Khandwa | 4.3% | 5.4% | +12% | 0.043 | +10% | worsening |
| South Seoni | 14.2% | 12.4% | +5% | 0.000 | +2% (p 0.68) | weak |
| Jhabua (7k ha) | 2.7% | 4.2% | +15% | 0.003 | +4% (p 0.57) | weak |
| Datiya (11k ha) | 0.4% | 1.2% | +35% | 0.022 | +10% (p 0.14) | weak |

- **Satpura Tiger Reserve is the one clear improver**: burning fell by an eighth a year relative to the state, from 10% of its forest a season to 3%. It is also the reserve whose share of fires before 15 February jumped from 4% to 23% after 2022 (mp_forest_types.md, finding 6): the reserve started burning early and its season burning fell. That is the only place in MP where the record shows a management change and a result together, and it is the natural pilot for the plan.
- **The worsening cluster is the Bundelkhand dry belt** (Damoh, South Panna, North Sagar, Vidisha): burning rising 5-15% a year against the state, from 6-8% of forest a season to 7-10%. Not a weather artefact (the state-season term removes it) and seen in both the scars and the heat points.
- North Betul's fall after 2020 (section 9.2 of control_burning.md) is a step, not a trend, and does not pass this test.

## 3. Why did some repeat patches cool? (done, 20 Oct)

Code `code/newq/n3_cooled.py`; outputs `code/newq/out/n3_patches.csv` (one row per tr3 patch with class, greenness change, access layers, division trend) and `n3_tests.csv`.

Classes among the 3,867 tr3 patches: cooled = burnt 60%+ of seasons 2017-21 and under 25% in 2022-25 (995 patches); held = 50%+ in 2022-25 (651); the rest in between (2,221). Each patch was put on the 500 m grid, and its Jan NDVI and NBR (HLS dryness file, first three 10-day steps) averaged for 2017-19 and 2023-25, with the GIS layers from static_gis_v1.

| What was compared | Cooled | Held | Verdict |
|---|---|---|---|
| Jan NDVI change 2017-19 to 2023-25 | +0.041 | +0.041 | same (all MP forest +0.049): no canopy loss, no extra regrowth |
| Jan NBR change | +0.030 | +0.034 | same |
| Division's own nine-season trend | -2.6 %/yr | +1.1 %/yr | cooled patches sit in cooling divisions, but division explains only 13.5% of patch-to-patch change |
| Distance to road / to village (km) | 1.19 / 1.95 | 1.38 / 2.20 | cooled patches are nearer people |
| Road km within 5 km, farm share within 5 km | 0.093, 16% | 0.074, 14% | same direction |
| Early (Jan-Feb) share of fires on the patch, 2017-21 vs 2022-25 | 5% to 6% | 4% to 5% | cooling is not conversion to Feb burning |

Within divisions (patch minus its division mean), the change in burnt share correlates with road density at rho -0.11, distance to road +0.11, slope +0.10, distance to village +0.08 (all p < 0.001, n 3,833). Small but consistent: the repeat patches that cooled are the ones people and crews can reach; the ones that held are remote and steep.

What this means. The satellite record shows no land change on the cooled ground, so the cooling is behaviour (suppression reaching the patch, or fewer people lighting it), not fuel. It cannot say which from here. For the programme it says one thing clearly: the ground still burning year after year is the hard-to-reach ground, so the first-programme patches (already selected on 2022-25 repeat burning) are the right ones, and the access layers (d_road, slope) are a fair way to rank them for the watcher layer rather than for lines, since lines need the same access.

## 4. Which side of a patch is downwind, and does it matter? (done, 20 Oct)

Code `code/newq/n4_fetch_wind.py` (ERA5 10 m wind from Google's public ARCO-ERA5 store, the same key-free reader the live-alerts thread uses for soil moisture; 06/09/12 UTC = 11:30-17:30 IST, 15 Feb-15 Mar, 2017-25, 0.25 deg), `n4_downwind.py`, `n4b_fuel_side.py`. Outputs `code/newq/out/n4_patches.csv` (every tr3 patch: late-Feb and early-March downwind side, constancy, speed, years agreeing), `n4_divisions.csv`, `n4_escapes.csv` (1,439 escapes), `n4_test.csv`, `n4b_ground_side.csv`; map `figs_r30/r30_fig10_wind.png`.

**The wind itself.** Late-February afternoon wind over MP forest is a north-westerly that blows toward the SE (57 of 75 divisions with patches) or E (11), at 1.7-2.5 m/s. It is steady in the east and north-east (Singrauli, Sanjay Dubri, the Shahdols, Anuppur: constancy 0.73-0.79, the same octant in 6-7 of 9 years) and unsteady in the south-west belt (Ratapani 0.08, Sehore 0.13, Dewas 0.15, Barwah 0.20, Indore 0.25: the dominant octant holds in only 1-3 years of 9). Of the 465 first-programme patches, 301 have the SE as the downwind side, 93 E, 47 NE.

**Does it say where a fire leaves the patch?** Test on every scar fire 2017-25 that started inside a tr3 patch between 15 Feb and 14 Mar and burnt 10+ ha outside it (1,439 fires, 75 divisions): bearing from the ignition cells to the outside burnt ground, against the wind.

| Side predicted by | fires | within 45 deg | within 90 deg | 200+ ha escapes within 90 deg |
|---|---|---|---|---|
| random | | 25% | 50% | 50% |
| afternoon wind of the fire's first two days | 1,439 | 29% | 53% (CI 51-55) | 47% |
| late-Feb wind climatology of the cell | 1,439 | 26% | 50% | 48% |
| most forest within 3 km outside the patch | 1,439 | 26% | 52% | 54% |
| most often-burnt forest within 3 km outside | 1,439 | 25% | 52% | 60% |
| uphill side (500 m elevation, 2 km) | 1,400 | 29% | 52% | 61% |

Wind adds almost nothing (53% against 50%), on calm and windy days alike, and nothing at all for the 200+ ha runs. The climatology is random. This repeats what the big-fires study found on a different fire set (ERA5 daily wind 50% within 90 deg). The only side that carries a signal is for the large escapes: 60-61% of the 211 fires that ran 200+ ha outside went uphill or toward the most often-burnt neighbouring forest, which is the same "momentum plus slight uphill, toward often-burnt ground" the big-fires study measured.

**What this means for the plan.** A burn order by downwind side is not supported: on the ground a February fire in MP teak is a litter fire that creeps on all sides, and where it breaks out is set by slope and the fuel next door, not by the 2 m/s afternoon breeze. For the 182 high-escape patches the boundary that must be real is the uphill one and the one facing the neighbouring repeat-burn ground, and `n4_patches.csv` keeps the wind side only as a secondary note. `n4c_patch_sides.py` adds `uphill_side` and `repeat_fuel_side` (octants) to every patch in `n4_patches.csv` and to the plan files `joint_plan/out/j1_patches.csv/.geojson`, next to `feb_downwind_side`; in the first programme the two agree on only 22% of patches, so both boundaries are named. The wind data itself is a useful by-product: a key-free ERA5 wind reader now exists for the live system (`n4_fetch_wind.py`), which the big-fire and spread work had asked for.

## 5. Ignition calendar by division (done, 20 Oct): null

The statewide check (`mp_calendar_effects.md`, 16 Oct) already found no weekday effect and Holi eve 1.38x. The one thing it could not see is a market (haat) day, because haat days differ from place to place and would cancel statewide. `code/newq/n5_weekday_division.py` tests each division on its own: scar-fire start dates 2017-25 (93,116 fires), observed starts per weekday against a centred 15-day running mean of the division's own daily series, the largest weekday's ratio against 2,000 shuffles of weekday labels within each week, Holm across the 68 divisions with 300+ fires. Outputs `out/n5_weekday.csv`, `out/n5_weekday_division.csv`.

| | result |
|---|---|
| All MP, weekday ratios | 0.95 (Sat) to 1.05 (Tue); permutation p 0.74 |
| Divisions with a weekday at p < 0.05 | 0 of 68 (3.4 expected by chance) |
| Largest per-division peak | Ratlam Sunday 1.32x on 323 fires, p 0.17 |
| Peak day across divisions | Tue 18, Sun 14, Mon 14, Thu 8, Wed 6, Fri 5, Sat 3: no pattern |

No division lights fires by the day of the week, so there is no market-day signal to put watchers on. Tendu and mahua collection dates are not in any data we hold (the statewide note said the same), so the ignition calendar stays what it was: the season clock by region (fire-timing study), Holi eve, and nothing weekly.

## 6. The monsoon after the fire (done, 20 Oct): no trace by the next peak greenness

Only one season can be tested from what we hold: the MODIS 8-day series that the live system reads (500 m) covers Sep-Oct 2024 and Sep-Oct 2025, so the 2025 fires have a before and an after. `code/newq/n6_monsoon_recovery.py`: per 500 m forest cell (at least half forest), peak NDVI and NDMI of the Sep-Oct composites, 2025 minus 2024, for cells at least half burnt in 2025 (scar rasters, by burn date) against the unburnt forest cells of the same division. Output `code/newq/out/n6_recovery.csv`.

| cells (2025) | n | peak NDVI 2024 | change to 2025, within division | holding the 2024 level |
|---|---|---|---|---|
| unburnt forest | 262,568 | 0.778 | +0.001 | reference |
| burnt 15-28 Feb or earlier | 548 | 0.815 | -0.005 (CI -0.009 to +0.001) | +0.008 |
| burnt 1-15 Mar | 4,427 | 0.818 | -0.007 (-0.011 to -0.004) | +0.006 |
| burnt 16-31 Mar | 8,768 | 0.820 | -0.009 (-0.011 to -0.006) | +0.006 |
| burnt Apr+ | 7,127 | 0.817 | -0.007 (-0.010 to -0.004) | +0.008 |

Burnt ground is the greener forest to begin with (peak NDVI 0.82 against 0.78), and greener cells come down a little the next year wherever they are (regression to the mean, slope -0.37). Taking that out, the burnt cells are 0.006-0.008 higher than unburnt, with no order by fire date, and NDMI shows the same nothing. On a peak NDVI of 0.82 these are differences of under 1%, inside what the sensor and the composite can tell apart. By the next monsoon the fire has left no mark on peak greenness at 500 m, whatever its date. This is one season and one sensor; a finer answer needs HLS 30 m over the monsoon, which the cloud reader can give but at about an hour per ten-day step for two divisions, and section 1 already says the orbit sees no difference between fire dates at the time of the burn.

## What the six add up to (20 Oct)

Four nulls and two findings. Nulls: fire date leaves no mark on burn severity (1), the wind does not say where a fire leaves a patch (4), no division lights fires by the weekday (5), and the next monsoon's peak greenness carries no trace of the fire (6). Findings: Satpura TR is the one division whose burning has fallen for nine seasons while its early-burn share rose, and is the natural pilot (2); the repeat patches that cooled are the ones people and crews can reach, with no land change behind it, so the ground still burning every year is the remote, steep ground, and the plan's first-programme patches are the right ones (3). The plan files now carry, per patch, the uphill side and the neighbouring repeat-fuel side, which is where the 200+ ha escapes go, in place of a wind rule.

Side product: a key-free ERA5 10 m wind reader (`code/newq/n4_fetch_wind.py`) that the live system can use the way it already reads ERA5 soil moisture.

On the satellite side of prevention, nothing with a real expected yield is left on this list. What would change the picture is ground truth the orbit cannot give: which patches were actually line-cut or burnt by the department in a season, so the held-out saving could be measured rather than inferred from scars alone.
