# Every January-February burn in MP forest, 2014-26, sorted into department-like burning and the rest (20 Oct 2026)

Akkshay (20 Oct 09:11Z): "try to capture all the control burns done by forest dept in Jan n Feb each year". This is that capture. The department keeps no public record of where or when it burns (`department_records.md`), so the orbit is the record: every VIIRS detection and every burn scar in MP forest in January and February, each season, with a plain-rule sort into department-like and wildfire-like. Code `code/dept_burns/d1_capture.py`, `d2_summarise.py`.

## Files

| file | what |
|---|---|
| `code/dept_burns/out/dept_burns_jan_feb.geojson` | every event as a point: 22,500 VIIRS burn-day clusters 2014-26 and 4,193 scar fires 2017-25, with date, division, beat, class, size |
| `out/viirs_clusters_jan_feb.csv` | the clusters: points, satellites, day-only, single-day, max FRP, elongation, distance to road and to beat boundary, control-like flag, class |
| `out/scar_fires_jan_feb.csv` | the scars: ha, forest ha, length and width, share on a beat boundary, burn days, matched VIIRS points, night share, max FRP, class |
| `out/jan_feb_by_division_season.csv` | per division and season: clusters, points, before-15-Feb, control-like, department-like, on a line, scar fires and ha |
| `out/jan_feb_statewide.csv` | the same per season for all MP |
| `code/dept_burns/figs/maps_by_season.png`, `figs/trend.png` | one map per season; the trend |

## How a burn is sorted

- **VIIRS cluster** (all three satellites, 750 m same-day, 2014-26): *control-like* = day-only, single-day (nothing within 1 km two days before or three after), at most 2 points, max FRP at most 5 MW (the flag from `managed_early_burns.md`, 24% of pre-15 Feb points, 5.8% of wildfire-season points). *On a line* = within 100 m of a beat boundary or a road (29% of Jan-Feb clusters; 25% for random forest points, so a line is only a weak sign). *Department-like* = control-like, or before 15 Feb and on a beat boundary.
- **Burn scar** (60 m, 2017-25): *strip* = length/width at least 4 and width at most 150 m, or 60%+ of cells within 90 m of a beat boundary. Before 15 Feb: department-like unless hot (FRP over 10 MW) or night-burning and multi-day. 15-28 Feb: department-like only if a strip or control-like (day-only, single day, at most 2 points, FRP at most 5 MW).

Two coverage facts set what the numbers can mean. The scar method ran the whole season only in Ratapani, so **January scars (area) exist only for Ratapani**; everywhere else scars start on 15 Feb and January is VIIRS points only. And a 6-12 m fire-line strip is below both sensors: VIIRS sees a strip as one or two cool points, the 60 m scar sees it only where the burn spread wider (34 January strips in nine seasons in Ratapani, median 6.5 ha). What is captured is therefore the burning a strip or block produces, not the line itself.

## What the capture shows

Statewide per season (`jan_feb_statewide.csv`; before 2018 only S-NPP flew, so 2014-17 counts are about half of what three satellites would give):

| season | Jan-Feb clusters | before 15 Feb | control-like | scar fires 15-28 Feb | scar ha | of which department-like ha |
|---|---|---|---|---|---|---|
| 2016 | 1,926 | 846 | 580 | | | |
| 2017 | 1,024 | 380 | 392 | 448 | 46,990 | 12,342 |
| 2018 | 1,457 | 839 | 590 | 455 | 29,699 | 12,104 |
| 2019 | 1,597 | 1,104 | 689 | 407 | 19,339 | 7,985 |
| 2020 | 436 | 230 | 208 | 89 | 2,740 | 1,739 |
| 2021 | 3,935 | 2,706 | 1,212 | 704 | 68,624 | 9,245 |
| 2022 | 959 | 614 | 424 | 186 | 7,133 | 2,638 |
| 2023 | 3,453 | 1,891 | 1,183 | 1,018 | 55,835 | 12,293 |
| 2024 | 1,529 | 858 | 635 | 262 | 10,227 | 2,642 |
| 2025 | 3,040 | 1,758 | 1,076 | 624 | 25,328 | 5,735 |
| 2026 | 2,608 | 1,760 | 1,001 | | | |

- **The January-February burning of MP is 1,000-2,700 cool day-time burns a season before 15 Feb, and 1,000-1,200 control-like burns across the two months, in 70-80 divisions.** They look alike everywhere: 82% day-only, 76% single-day, median max FRP 3.8 MW. The control-like share falls week by week, 46% in the first week of January to 26% in the last week of February, as the people's fires start.
- **It is concentrated.** Ten divisions carry half of it: Dewas (138 pre-15 Feb clusters a season), Ratapani (100), Sehore (88), Singrauli (88), Khandwa (69), Raisen (66), Indore (48), Burhanpur (39), Satpura TR (34), Damoh (30). Singrauli's early burning is almost never control-like (2 of 88): it is hot and multi-point, which fits coal-belt and village burning rather than crews.
- **Area.** Where scars exist, 15-28 Feb department-like burning is 5,400 ha a season against 21,800 ha of wildfire-like burning in the same fortnight. In Ratapani, the one division with January scars, the January blocks ran 2,800-4,800 ha a season in 2017-19 and 2021, then 24-1,400 ha in 2020 and 2022-25 (`scar_fires_jan_feb.csv`, class "pre-15 Feb block"). The 2026 season (VIIRS only) is as busy as 2025.
- **The early-leaf-fall years stand out**: 2021, 2023 and 2025 have two to three times the clusters of the years around them, before 15 Feb above all. That is the department (and villagers) burning when the litter is ready, not a change of policy, and it matches the leaf-fall record in `mp_forest_types.md`.

## What this is good for

1. The geojson is the "who burnt what, when" layer the plan lacked: for any patch in `joint_plan/out/j1_patches.geojson`, the events inside it say whether the division already burns there, and in which weeks. `department_records.md` section 3 used a first cut of this (10% of first-programme patches had early burning in 2023-25).
2. The sort is a rule, not a model, so it can be checked against any division's own record of burns in one afternoon; the FFPM geotagged photos for one division would calibrate the control-like flag's precision, which from the week profile is about 70% before 15 Feb and falls after.
3. For the live system: a pre-15 Feb detection that is day-only, single-day, cool and on a beat boundary is department work and should be tagged, not alerted as a wildfire; the field thread's officials-only control-burn tag already follows this rule.

## Against the plan: what the department already burns, and the gap (20 Oct, `d3_plan_gap.py`)

Every captured event placed in its repeat patch (`out/plan_patches_dept.csv`, every tr3 patch; `out/plan_gap_by_division.csv`, the first programme per division).

| first-programme patches (465, 100k ha) | patches | forest ha |
|---|---|---|
| department burns it (department-like early burn in 2+ of 2023-26) | 17 | 29,500 |
| burnt early some seasons since 2017 | 75 | 24,800 |
| Jan-Feb fire on record, not department-like | 53 | 13,100 |
| never burnt early | 320 | 32,500 |

By area the department already does the programme on 30% of the first-programme ground, mostly the big Ratapani, Dewas and Sehore patches, and has touched another 25% in some season. The 45% never burnt early is the gap, and it sits in divisions where early burning is not the practice: South Balaghat (26 patches, 4,400 ha, none ever burnt early), Umaria (13, 3,600 ha), Barghat (3,450 ha), Narsinghpur, Hoshangabad, South Chhindwara, East Chhindwara, West Mandla, Satna, Dindori. Of all 3,867 repeat patches, 3,194 (83%) have never had an early burn on record. The gap list is the field-practical output: the divisions where the programme means starting a practice, not scaling one.

## Is January too early? (20 Oct, `d4_january_hold.py`)

Ratapani, the one division with January scar outlines, 2017-25. Ground classed by its first burn (Jan 1-31, Feb 1-14, Feb 15-28, Mar 1-15); every VIIRS point from 16 Mar to 15 Jun counted on ground burnt in that window at least two weeks earlier, against ground not burnt before March in the same 5 km square (the cb2 method). Ratio below 1 = the old burn still keeps fire off that ground (`out/january_hold.csv`).

| burnt in | burnt ha (9 seasons) | later points on it | later fire vs unburnt ground | CI |
|---|---|---|---|---|
| Jan 1-31 | 5,800 | 17 | 0.30 | 0.09-0.53 |
| Feb 1-14 | 13,200 | 73 | 0.48 | 0.38-0.63 |
| Feb 15-28 | 21,500 | 65 | 0.30 | 0.21-0.40 |
| Mar 1-15 | 49,500 | 85 | 0.15 | 0.11-0.19 |

A January block holds through April and May as well as a late-February one (0.30 against 0.30; the March figure is lower only because less season is left). January is not too early for the ground it covers; the cost of January is the one found before, that litter still falling after the burn is what the orbit sees as the 1-14 Feb burns protecting least (0.48), and that a January crew burns before the teak has shed, so it covers less ground per day. Few points (17 on January ground), so the CI is wide, but nothing here says wait for February.

## Checking the sort against Ratapani's January scars (20 Oct, `d5_calibrate.py`)

776 pre-15 Feb VIIRS clusters in Ratapani 2017-25 matched to the January scar fires (within the scar plus 750 m, 3 days). Of the 387 January scar fires, 335 are cool blocks (median 26 ha), 34 strips (median 6.5 ha) and 18 hot multi-day fires (median 136 ha): **95% of what burns in Ratapani before 15 Feb is a cool block or strip**, which backs the plain reading that pre-15 Feb burning is department work. The control-like flag is a weak filter inside that: it marks 41% of the blocks and 53% of the strips, and the clusters it leaves unflagged are just as often blocks (87% of those with a scar). So for January the right rule is "all of it", with the hot multi-day 5% set aside; the flag earns its keep only from 15 Feb, when the people's fires start and the two must be told apart. The tables in this note already count both ways (`pre15_clusters` and `control_like`).

## Last round: does the department burn the right ground, and does it spill over? (20 Oct, `code/dept_burns/d6_last_round.py`)

Four last questions the capture can answer on its own. Files `d6_targeting.csv`, `d6_spillover.csv`, `d6_habit.csv`, `d6_budget_vs_activity*.csv` in `code/dept_burns/out/`.

**Where the burning lands.** Only 10% of pre-15 Feb burn clusters (2017-26, 12,140 of them) fall inside a repeat-burn patch, against 16% of later wildfire points (15 Feb-15 Jun). Nine tenths of early department burning is on ground that does not burn repeatedly. Inside a division the patches the crews do burn are the better ones: they sit at the 62nd percentile of their division's repeat rate (never-burnt patches at the 50th), 40% of them are in the division's top quarter against 24% by chance, and they are mostly the large patches (74th percentile of forest area). So crews pick big, often-burnt blocks when they go into repeat ground, but most of their work is elsewhere.

**No spillover.** Two-way fixed effects on 34,800 patch-seasons with own burn and neighbour burn (another patch within 2 km burnt early that season) side by side:

| | patch-seasons | later burnt share | 95% range |
|---|---|---|---|
| own patch burnt early | 360 | −6.2 pts (−15%) | −11.7 to −2.4 |
| a neighbour burnt early | 585 | −1.7 pts (−4%) | −5.6 to +3.8 |

A burn protects the patch it is on and nothing next door. Programme benefit should be counted patch by patch, with no credit for neighbours.

**Habit.** A patch burnt early in one season is burnt early again next season 30-46% of the time (2020 and 2022 aside), against 15-20% for other patches. Still, 261 of the 387 patches ever burnt early were burnt in one season only; 61 in three or more. The department's repeat burning is a small core, not a rotation.

**Money against activity (CAMPA 2025-26, 65 divisions).** Watcher numbers track where early burning happens (Spearman 0.55 with pre-15 Feb clusters, 0.41 with burnt area). The fire-line budget does not (0.22, p 0.08; 0.28 with burnt area). Dewas does 198 burn clusters a year on 25 lakh; West Mandla, South Shahdol and Sidhi hold 28-30 lakh each and show 1-3 clusters a year. The line money is spread by unit, the work is not.

**What this closes.** The capture says where crews burn, that it works on the patch and nowhere else, that only a tenth of it lands on repeat ground, and that line money does not follow the work. The ask that remains is the department's own return for one division, to put a precision figure on the sort.
