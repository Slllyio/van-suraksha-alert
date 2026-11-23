# Control burns before and just after 15 Feb across MP: what they look like from orbit, how far they leak into the fire season, whether they reduce later fire, and a pipeline rule (scouting round 15, topic "burn", 16 Oct 2026)

**Starting fact (from Akkshay, 16 Oct 18:23Z):** "before 15 feb there are many control burnings in all over mp forest". This note treats that as known. It does not try to prove that planned burns exist. It measures what they look like in VIIRS, how many continue after 15 Feb, and whether they change later fire.

**Not repeated here** (already in other notes): NAPFF 2018 §6.3-6.4, MP FFPM/CAMPA fire-line km and budgets, the NTCA audit protocol, Price et al. 2012 (Arnhem leverage, slope about −1), Price 2015, Franke 2024 (Cerrado), Laris 2002/2005 (Mali): see `fire_management_practice.md`. The Ratapani-only winter night-share and boundary tests are in `diurnal_and_controlled_burns.md`. The Kuno/Satpura/Kanha early-share jump is in `mp_forest_types.md` item 6.

**Tags.** DATA = computed here from our files. FULL / PARTIAL / ABSTRACT ONLY = reading status of a source. **[inference]** = my reasoning.

**Code:** `code/early_burns/` (scripts `b0`-`b14`, plus `control_burn_rule.py`). **Tables:** `code/early_burns/out/`. **Re-usable table:** `out/clusters_oct_to_15mar.parquet` (54,050 burn-day clusters, Oct to 15 Mar, with all features and the flag).

---

## Headline findings

1. **Early fires across MP look different only in intensity and duration, not in shape.** Compared with 16 Mar-May fires, 1 Jan-14 Feb burn-day clusters are more often day-only (82% vs 61%), more often single-day (76% vs 55%), weaker (median max FRP 3.8 vs 5.2 MW) and smaller (mean 2.0 vs 2.5 points). At 375 m they are **not** more linear (median elongation 2.35 vs 2.28), **not** nearer roads (16% vs 14% of points within 375 m of an Overture road; random forest points: 26%) and **not** nearer beat edges (17% vs 18% within 100 m; random: 25%). VIIRS cannot see a 6-12 m fire-line strip as a line. (DATA)
2. **A simple flag catches about a quarter of pre-15 Feb points.** Flag = day-only, no detection within 1 km on the 2 days before or 3 days after, at most 2 points, max FRP ≤ 5 MW. It tags 24% of Jan-14 Feb points MP-wide (median division 28%, IQR 22-35%) and 36% of Oct-Dec points, against 5.8% of 16 Mar-May points (the background rate for wildfires). (DATA)
3. **Control-like burning spills about two weeks past 15 Feb, then stops.** Flagged share by week: 15-21 Feb **21.5%**, 22-28 Feb **15.9%**, 1-7 Mar 8.3%, 8-14 Mar 7.5%, then back to the 5.8% background from 22 Mar. The estimated precision of the flag is 73% and 64% in the two late-Feb weeks, but only 31% in 1-7 Mar. (DATA)
4. **Contamination of the 15 Feb-15 Jun target is small overall but concentrated.** It is about 0.4% of season points by the flag-excess method, and at most about 3% by an upper-bound method. Most of it falls in the first two weeks, where "Jan-like" fires may be 56-87% of all points. **The sal belt and the reserves are hit hardest:** the flagged excess in 15 Feb-15 Mar is 22 points of share in Kanha, 20 in Anuppur, 18 in Bandhavgarh, 16 in South Balaghat, 15 in West Mandla, North Panna and Panna TR, and 14 in Satpura and Vidisha. **[inference]** Sal sheds late (about 7 Feb, `mp_forest_types.md`), so burning there runs later. (DATA)
5. **Kuno's early fires are block burns, not strips.** They average 3 points per cluster with FRP about 6 MW, and the flag catches only 10% of their points. The top 3 days hold a median 60% of a season's early points. A reserve-specific "block burn" class is needed there. Satpura's early fires are small and flag-like (50% of clusters flagged). (DATA)
6. **In the same 500 m cell, a pre-15 Feb burn goes with about one-third lower odds of burning later that season.** Two-way fixed effects (cell, and division × season) on 1.85 million cell-seasons: −4.1 points against a 12.5% base (−33%, SE 0.24 pt). Flagged small burns −26%; larger early fires −38%. The effect holds both in 15 Feb-15 Mar (−47%) and in 16 Mar-May (−27%). (DATA)
7. **The effect stays local.** At beat level, seasons with more early-burned cells have slightly *more* later-burned cells, not fewer: elasticity +0.09 (CI 0.08-0.11), with beat and division-season effects removed. MP-wide, the implied avoided later burns are about 700 of 232,000 later cell-seasons (0.3%). **[inference]** Early burning removes fuel in the cell it touches, but busy-burning beats stay busy. (DATA)
8. **Reserve-level test (cautious): Satpura is the one clean case.** After its early-burn jump (2023-26), Satpura's Mar-May share of MP S-NPP points fell 64%, the largest drop of 76 divisions. Its Mar-May scar total per season fell from 18,786 ha to 5,465 ha (−71%). But Pench fell almost as much (−84% scar ha) with no early-burn jump, and median scar size fell in most reserves after 2023. Kuno fell 28%. Across divisions, the change in early share does not predict the change in Mar-May share (Spearman −0.10, p = 0.37). (DATA)
9. **2023 was an early-fire year everywhere.** The MP-wide pre-15 Feb share was 11.2% in 2023 against 1.5-5.6% in other years; the median division went from 0-1.5% to 5%. That fits the 3-week-earlier leaf fall in 2023 (`mp_forest_types.md`). Kuno (69%) and Satpura (40%) stood far above that in 2023, and Kuno 2025-26 (27%, 59%) and Satpura 2024/2026 (42%, 41%) stood far above it in other years too. (DATA)
10. **There is no clean work-week signal.** Jan-14 Feb clusters are slightly fewer on Mon-Wed (index 0.90-0.94) and more frequent on Thu-Sat (1.04-1.10). There is no Sunday dip, and Mar-May is flat (0.95-1.02). Weekday is not a usable flag condition. (DATA)

---

## Part A. Our data (DATA, computed 16 Oct 2026)

### A1. Inputs
- **Jan-Jun points:** `code/mp_types/out/viirs_vtm.parquet` (S-NPP 2014-26, NOAA-20 2018-26, NOAA-21 2023-26, inside MP beats, type 0 only).
- **Oct-Dec points (new):** FIRMS country archive yearly India files (S-NPP 2013-25, NOAA-20 2018-25), downloaded without a key, clipped to the MP bbox and then to beats. That gives 9,066 points, assigned to the following season (`b0_fetch_novdec.sh`, `b3_features.py`).
- **Roads (new):** Overture Maps 2026-09-23 transportation segments for the MP bbox, read by HTTP range requests on row groups, with no key or install (`b2_overture_roads.py`). That gives 3.21 million road segments. "Road" means all classes except residential and footway-type; "track" means track, path, unknown or unclassified. Overpass and Geofabrik both reset from this container.
- **Beat edges:** boundaries of all 8,973 polygons in `ratapani/beats/mp_beats.geojson`.
- **Random controls:** 300 random points per division inside beats (`b4_random.py`).
- **Burn-day cluster:** points on the same fire-day within 750 m, any satellite. Night points from 00:00 to 05:59 IST count toward the previous day. This gives 266,857 clusters (`b6_clusters.py`).

### A2. Early share by reserve and year (S-NPP, share of a season's Jan-Jun points before 15 Feb; `out/early_share_snpp.csv`)

| | 2014-22 range | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| All MP | 1.5-5.6% | **11.2%** | 3.7% | 3.4% | 6.0% |
| Median division | 0-1.4% | 5.0% | 0.4% | 1.0% | 1.5% |
| Kuno | 0-22% | **69%** | 9% | **27%** | **59%** |
| Satpura | 0-14% | **40%** | **42%** | 11% | **41%** |
| Kanha | 5-37% | 31% | 10% | 3% | 10% |
| Noradehi (VDTR) | 1-42% | 26% | 2% | 4% | 4% |
| Panna TR | 0-46% | 20% | 3% | 2% | 8% |
| Ratapani (Obedullahganj) | 1-14% | 15% | 4% | 3% | 7% |
| Bandhavgarh, Sanjay-Dubri | 0-7% | ≤1% | ≤1% | ≤1% | 0% |

Point counts are small in some cells of this table (Kuno 23-95 early S-NPP points a season; `out/early_n_snpp.csv`).

### A3. What early clusters look like vs the main season (`out/windows_snpp.csv`, `b8_explore.py`)

| Burn-day clusters | Oct-Dec | 1 Jan-14 Feb | 15 Feb-15 Mar | 16 Mar-May | Jun | Random |
|---|---|---|---|---|---|---|
| clusters | 6,459 | 13,336 | 34,255 | 208,565 | 4,242 | – |
| day only (no night within 1.5 km) | 74% | **82%** | 64% | 61% | 73% | – |
| single-day (nothing within 1 km, −2 to +3 days) | 73% | **76%** | 58% | 55% | 78% | – |
| max FRP ≤ 5 MW | 78% | **66%** | 59% | 49% | 46% | – |
| median max FRP (MW) | 3.0 | 3.8 | 4.1 | 5.2 | 5.5 | – |
| ≥3 points | 9% | 20% | 28% | 27% | 15% | – |
| linear (≥3 points and elongation ≥3) | 3% | 7% | 10% | 9% | 6% | – |
| S-NPP points ≤375 m from road | 31% | 16% | 11% | 14% | 19% | 26% |
| S-NPP points ≤100 m from beat edge | 25% | 17% | 17% | 18% | 20% | 25% |

- Fire points of every month lie *farther* from roads than random forest points. Fires are in the remote forest; random points include the farmland and villages inside beats. Oct-Dec points look like random points (31% near road, 4% near residential streets against 2% in Jan), so many Oct-Dec points are field-edge burns.
- **Site recurrence is low.** Only 9.7% of Jan-14 Feb clusters sit in a 500 m cell that also had an early cluster in ≥2 *other* seasons. **[inference]** Either the department burns different line sections each year, or VIIRS detects only a few strips, at random. In both cases, "same place every year" is not a usable VIIRS signal at 500 m.
- **Temporal clustering:** in division-seasons with ≥20 early points, the 3 busiest days hold a median 44% of early points (Kuno 60%, Panna TR 66%, Noradehi 58%, Satpura 48%, Kanha 41%, Ratapani 36%).
- A leak-free classifier trained on Jan-14 Feb vs 16 Mar-May with date-free features (day-only, single-day, n, satellites, FRP, road, track and edge proximity, linearity, early-site recurrence; train on even seasons and test on odd, and vice versa) reaches **AUC 0.80**. A first version reached 0.99 only because the site-recurrence feature leaked the cluster's own season; this was fixed. Most of the signal is FRP, day-only and single-day.

### A4. The flag by division (`out/division_flag_shares.csv`)

- Among 37 divisions with ≥100 Jan-14 Feb points, the flag tags a median **28%** of early points (IQR 22-35%).
- Lowest: Singrauli 0.8% (industrial heat, already masked elsewhere), Kuno 10% (block burns), Noradehi 15%, Burhanpur 18%, Damoh 19%.
- Highest: East Chhindwara 44%, West Chhindwara 43%, Narsinghpur 42%, Dhar 41%, Guna 39%.

| Reserve division | Jan-14 Feb pts (all sats) | flagged | 15 Feb-15 Mar pts | flagged | 16 Mar-May flagged (background) |
|---|---|---|---|---|---|
| Ratapani (Obedullahganj) | 2,245 | 24% | 6,072 | 9.0% | 3.8% |
| Kuno | 780 | 10% | 661 | 2.7% | 2.5% |
| Noradehi | 684 | 15% | 1,056 | 6.0% | 2.4% |
| Satpura | 606 | 35% | 303 | 16.5% | 2.2% |
| Kanha | 505 | 22% | 277 | **32.5%** | 10.5% |
| Panna TR | 346 | 32% | 524 | 17.4% | 2.6% |
| Bandhavgarh | 46 | 46% | 265 | 27.9% | 9.7% |
| Pench | 36 | 31% | 158 | 25.9% | 9.5% |
| Sanjay-Dubri | 36 | 33% | 210 | 14.3% | 5.3% |

### A5. How many control-like burns continue after 15 Feb (`out/weekly_after_15feb.csv`)

| Week | points | flagged | excess over 5.8% background | est. flag precision | upper-bound "Jan-like" share of all points |
|---|---|---|---|---|---|
| 15-21 Feb | 6,852 | 21.5% | 15.7 pt | **0.73** | 0.87 |
| 22-28 Feb | 11,746 | 15.9% | 10.1 pt | **0.64** | 0.56 |
| 1-7 Mar | 24,250 | 8.3% | 2.6 pt | 0.31 | 0.14 |
| 8-14 Mar | 37,082 | 7.5% | 1.7 pt | 0.23 | 0.09 |
| 15-21 Mar | 40,809 | 9.5% | 3.8 pt | 0.40 | 0.21 |
| 22 Mar onward | 96k-131k a week | 4.6-6.0% | ≈0 | ≈0 | 0 |

- **Excess method.** Flagged share minus the 16 Mar-May background, divided by the flagged share, gives the precision column.
- **Upper-bound method.** It assumes all Jan-14 Feb points are control burns: (flagged − background) / (Jan flagged − background). A histogram-mixture fit of the classifier score agrees: 0.88, 0.59 and 0.41 for weeks 0-2.
- **Both are upper bounds on the control share** because of weather. The same method calls 33% of **June** points "Jan-like", and June fires are not control burns but weak end-of-season fires. Small, cool, short fires look alike whatever lit them.
- **The 15-21 Mar bump** (9.5%) may be Holi-week burning or a wet spell. Not resolved.
- **MP totals.** The 15 Feb-15 Jun season has 633,406 points. Flag-excess control points in 15 Feb-15 Mar number about 3,900 (0.6% of the season). The upper bound for 15 Feb-14 Mar is about 19,300 (3.0%).

### A6. Does a control-burned cell burn less later that season? (`b11_later_odds.py`, `b12_twfe.py`, `out/later_odds_twfe.csv`)

**Unit:** cell-season, on a 0.005° grid (about 500 m), for the 142,523 cells that ever had a VIIRS point, 2014-26. **Treatment:** any cluster from Oct to 14 Feb. **Outcome:** any cluster from 15 Feb to 30 Jun.

| Sample | Treatment | Coefficient (pt) | SE | Base rate | Relative |
|---|---|---|---|---|---|
| All MP | any early burn | −4.13 | 0.24 | 12.5% | **−33%** |
| All MP | flagged (small) early burn | −3.22 | 0.32 | 12.5% | −26% |
| All MP | other early fire | −4.79 | 0.34 | 12.5% | −38% |
| Tiger-reserve divisions + Ratapani | any early burn | −2.76 | 0.46 | 11.4% | −24% |
| Other divisions | any early burn | −4.46 | 0.28 | 12.7% | −35% |
| All MP, outcome 15 Feb-15 Mar only | any early burn | −0.83 | 0.15 | 1.8% | −47% |
| All MP, outcome 16 Mar-May only | any early burn | −2.89 | 0.20 | 10.7% | −27% |

- **Method:** linear probability model with cell and division × season fixed effects, standard errors clustered by cell.
- **Raw within-cell difference ≈ 0.** The negative effect appears only once season weather is removed. Early-burn seasons are high-fire seasons in the same division.
- **The naive cross-section is also negative** (9.9% vs 12.6%), but cells that get early burns differ from other cells.
- **Beat level:** elasticity of later-burned cells on early-burned cells is **+0.09** (CI 0.08-0.11) after beat and division-season demeaning.
- **[inference]** The protective effect is fuel removal inside the burned 25 ha. It does not reduce a beat's total. It is about half of Arnhem's one-for-one leverage, and in line with Price 2015's forest end (leverage about 0.25 at 5% burnt per year). Caveats: one pixel is about 14 ha, so the outcome cell may include unburned ground; same-season fires are not independent; and this is observational.

### A7. Reserves with more early burning: fewer or smaller Mar-May fires? (`b7_division_did.py`, `b14_tr_scars.py`)

Mar-May share of MP S-NPP points, 2014-22 vs 2023-26:

| Division | Change in early share | Change in Mar-May share |
|---|---|---|
| Kuno | +22 pt | −28% |
| Satpura | +19 pt | **−64%** (rank 1 of 76) |
| Indore | +14 pt | −3% |
| Singrauli | +9 pt | 0% |
| Rewa | +8 pt | −21% |
| Kanha | ≈0 | −49% |
| Pench | ≈0 | −51% |
| Noradehi | ≈0 | −47% |
| Panna TR | ≈0 | +91% |

- **All 76 divisions:** Spearman between the change in early share and the change in Mar-May share is −0.10 (p = 0.37).
- **Tiger-reserve scars** (v1 outlines, 15 Feb-15 Jun 2017-25, Mar-May events; pre = 2017-22, post = 2023-25):

| Reserve | events/season pre → post | median scar ha | total scar ha/season |
|---|---|---|---|
| Satpura | 182 → 67 | 85 → 41 | 18,786 → 5,465 (−71%) |
| Pench | 65 → 30 | 28 → 14 | 3,908 → 630 (−84%) |
| Kanha | 191 → 142 | 23 → 15 | 8,094 → 3,115 (−62%) |
| Bandhavgarh | 347 → 294 | 37 → 22 | 24,019 → 13,326 (−45%) |
| Noradehi | 222 → 105 | 131 → 108 | 29,162 → 11,497 (−61%) |
| Sanjay-Dubri | 234 → 307 | 49 → 27 | 18,371 → 14,106 (−23%) |
| Panna TR | 132 → 179 | 73 → 75 | 12,044 → 19,304 (+60%) |
| Madhav | 28 → 42 | 130 → 116 | 3,320 → 5,079 (+53%) |

- **[inference]** Satpura is consistent with early burning working, but Pench and Kanha fell as much without a Satpura-style early jump. A reserve-scale test with 3 post years cannot separate early burning from the general post-2023 drop. v1 outlines are also capped by the chip edge (43% of Satpura pre events touch it), so the large fires behind the pre-period totals are under-measured. Kuno is not in the reserve scar set. **Verdict:** no reserve-level evidence beyond the local cell effect in A6.

---

## Part B. Literature and documents (short, as asked)

### B1. Kanha Tiger Conservation Plan, core 2022-23 to 2031-32, and buffer TCP. **NOT READ** (URLs found; host blocked)
https://mpforest.gov.in/img/files/Kanha_TCP_Text_Part-I.pdf and https://mpforest.gov.in/img/files/Kanha_TCP_Buffer.pdf. Both returned 503 or a connection reset to curl and WebFetch. A third MPFD file that search turned up, `https://www.mpforest.gov.in/img/files/Book_164-168.pdf` (likely manual pages), was also unreachable.
**Concrete action for us (threads 1, 5):** download these from an Indian connection. The TCP fire chapter should give the burning calendar, fire-line km and controlled-burn area, which would turn our 15-28 Feb tail (A5) into a known schedule. Ask for the Satpura, Kuno, Pench and Panna TCPs too.

### B2. Laris, Jacobs, Koné, Dembélé & Camara, "Determinants of fire intensity and severity in a mesic savanna of Africa" (conference slides of the Fire Ecology 2020 study, 10.1186/s42408-020-00085-x). https://csulb.edu/sites/default/files/2024/documents/Determinants%20of%20Fire%20Intensity%20and%20Severity%20in%20a%20Mesic%20Savanna%20of%20Africa%20%28PDF%29.pdf **PARTIAL** (slides read in full; the paper itself redirected to a login)
- Design: about 100 experimental fires in early, middle and late dry season in Mali (900-1,100 mm). The slides show 40 head fires and 43 back fires.
- Byram intensity 24.7-1,395 kW/m: head fires mean 336, back fires mean 124. Fuel 0.46 ± 0.16 kg/m², fuel moisture 7 ± 14%, wind 1.18 ± 0.59 m/s.
- **Season correlates with intensity only for back fires** (r = 0.48). Head-fire intensity is not explained by season, weather or grass type (adjusted R² 0.115, not significant). Back-fire models: season and grass share, adjusted R² 0.28-0.29.

**Concrete action for us (thread 4, thread 1) [inference]:** do not assume early burns are intrinsically gentle. Our early FRP is lower (median 3.8 vs 5.2 MW, A3), but that is partly fuel moisture. For the spread and stopping model, an early-season burned patch is a fuel break, not a low-intensity "type".

### B3. Search-level items. **ABSTRACT ONLY**
- No news, plan or paper reachable from here describes **Kuno** controlled or grassland burning, or a Satpura burning schedule. Several searches gave only poaching and cheetah stories.
- A news editorial on a "Khosla panel" report (indiaenvironmentportal.org.in) cites "2,301 km of fire lines, only 1,004 km were cleared and control burning was carried out only over 2,952 hectares". The state and year are not given in the snippet, so this is unverified.
- A guidance snippet (scribd) says controlled burning of leaf litter and dry grass is done "every year during early February" in dry deciduous forest. That matches our 15-28 Feb tail. Source not verified.
- Consensus search was unavailable (monthly quota used up).

---

## Part C. Pipeline rule (thread 1 target, thread 2 labels, thread 5 alerts)

`code/early_burns/control_burn_rule.py`, function `control_burn_flag(points, live=False)`:

1. **Oct to 14 Feb → `pre_season_control`.** Never a positive for the 15 Feb-15 Jun target. Keep it as an input: `early_burnt_cell_this_season`, with −33% later odds (A6).
2. **15-28 Feb and core flag → `likely_control`.** Core flag = no night point within 1.5 km that fire-day, no point within 1 km on days −2 to +3, ≤2 points in the 750 m cluster, max FRP ≤ 5 MW. Drop these from training positives and from scoring, or train them as a separate class.
3. **Everything else → `fire`.** Do not extend the rule into March: precision falls to 31% in 1-7 Mar and 23% in 8-14 Mar.
4. **Live mode:** the "days +1 to +3" test is unknown at alert time. Use day-only, ≤2 points and FRP ≤ 5 MW to give a 15-28 Feb alert low priority, not to suppress it.
5. **Reserve option:** in Kuno (and any division whose early clusters average ≥3 points), also tag day-only Jan-14 Feb clusters of any size as `pre_season_control`. The rule already does this through step 1. The question only matters if the target window is ever moved before 15 Feb.

**Cost of the rule (all MP, 15 Feb-15 Jun 2014-26, 633,406 points):**

| Option | Points removed | Est. control removed | Est. wildfire lost | Control left in target |
|---|---|---|---|---|
| Keep everything | 0 | 0 | 0 | ~3,900 by excess (0.6%); ≤19,300 upper bound (3.0%) |
| Drop flagged 15-28 Feb (recommended) | 3,339 (0.53%) | ~2,260 | ~1,080 | ~1,600 by excess (0.25%) |
| Drop flagged 15 Feb-7 Mar | 5,357 (0.85%) | ~2,880 | ~2,470 | ~1,000 |
| Start the target at 1 Mar | 18,598 (2.9%) | ≤12,500 (upper bound) | ≥6,000 | ≈0 in Feb |

- Ratapani (Obedullahganj) by the rule: 0.5-2.4% of 15 Feb-15 Jun points a season are `likely_control` (overall 0.9%). Kanha: 0.75%, but 11% in 2020. Satpura: 0.55%, 3.8% in 2026.
- **[inference] What it does to scores.**
  - Thread 1 per-division model: removing about 0.5% of positives hardly moves recall. But the removed points are the ones weather cannot predict, early in the test window, and concentrated in the sal belt and reserves (A4). Expect a gain of under 1 point of recall overall, and possibly a few points in Kanha, Bandhavgarh, Pench and Panna, where 15-30% of 15 Feb-15 Mar points are flagged against a 3-10% background.
  - Ratapani 2-day score: if the scored season includes 1 Jan-14 Feb, about 7.8% of Ratapani points (S-NPP) are pre-15 Feb control-like fires that the weather model cannot see coming. Score both ways.

---

## Ranked actions

| # | Action | Thread | Gain [inference] | Effort |
|---|---|---|---|---|
| 1 | Apply `control_burn_flag` in label building: pre-15 Feb → out of target; flagged 15-28 Feb → drop or separate class. Report recall with and without | 1, 2 | Small overall (~0.5% of positives), a few recall points in sal-belt reserves; more honest scoring | 0.5 day (code exists) |
| 2 | Add `early_burnt_cell_this_season` (and `days_since_early_burn`) to the 2-day model and the burn-probability maps. Measured −33% later odds in the same cell (−47% within 15 Feb-15 Mar) | 1, 4 | Small-medium for "where", in early-season weeks | 0.5 day |
| 3 | Give live alerts a `likely_control` low-priority tag on 15-28 Feb (day-only, ≤2 points, FRP ≤5) in the officials' weekly report | 5 | Fewer wasted checks in late Feb, mainly in the sal belt | 2 h |
| 4 | Get the Kanha core and buffer TCPs and the MP fire manual from an Indian connection. Extract the burning calendar and controlled-burn area; check against the A5 weekly tail | 1, 5 | Turns an inferred schedule into a known one | Low for us |
| 5 | Kuno-type block burns: a separate class for day-only multi-pixel Jan clusters in Kuno, Noradehi and Madhav. Check them on Sentinel-2 (expect compact blocks, not strips) | 2 | Removes a 2023+ regime break the 2019-21 training years cannot see | 0.5-1 day |
| 6 | Sentinel-2 10 m check of 50 flagged 15-28 Feb clusters (strip vs patch, along roads or lines) to measure the flag's true precision. Use the v2 scar code on Ratapani first | 2 | Replaces the 64-73% estimated precision with a measured one | 1 day |
| 7 | Redo the reserve test (A7) with v2-style full outlines for Satpura, Pench and Kanha, and add Kuno to the reserve scar run | 2, analysis | Settles whether Satpura's −71% is early burning or the general post-2023 drop | 1 day + scar run time |
| 8 | Check whether the 15-21 Mar flagged bump is Holi (`weekday_festival_check.md` method, all MP) | 1 | Small | 2 h |

## Reading status
- **DATA:** all of Part A.
- **PARTIAL (1):** Laris et al. slides (B2).
- **ABSTRACT ONLY / search-level (3):** Khosla-panel editorial, scribd guidance snippet, and Kuno/Satpura news searches (nothing relevant found).
- **NOT READ (blocked):** Kanha TCP core and buffer, MPFD Book_164-168, NTCA Stripes 2016.
