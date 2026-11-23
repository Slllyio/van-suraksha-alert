# What the department's own records say about cutting and burning, and what the orbit can add (20 Oct 2026)

Akkshay (20 Oct 07:36Z) picked up the line "the next real input would be which patches the department actually cut or burnt in a season". This note is what can be had now, without asking anyone.

## 1. Records that exist and are public

**MP State CAMPA Annual Plans of Operation (APO), 2020-21 to 2025-26**, on the National CAMPA site (`nationalcampa.nic.in/apo.php`, Madhya Pradesh rows; 2025-26 = `dashboard/APOPDF//6810738061e2b.pdf`, 472 pages, 22 MB; 2024-25 = `66b349ff5b618.pdf`, 403 pages). They are scanned images, Hindi, no text layer; copies are in this thread's scratch, not the shared folder (size). The 2025-26 plan carries, per territorial unit:

- **Fire-line management budget** ("अग्नि रेखाओं के प्रबंधन (जलाई-कटाई इत्यादि)", printed pages 306-308): 72 units, Rs 6 to 40 lakh each, total Rs 16.04 crore, for 6 m lines at 3.55 man-days/km and 12 m lines at 5.3 man-days/km. Transcribed to `code/newq/out/n8_campa_firelines_2025_26.csv` (my sum 15.99 crore against the printed 16.04; one cell may be misread).
- **Fire watchers and training budget** (printed pages 309-310): 73 units, Rs 5 to 20 lakh watchers each, total Rs 9.10 crore plus Rs 0.36 crore training. `n8_campa_watchers_2025_26.csv`. At the statewide rate (Rs 9.07 crore for 4,730 watchers) that is 42 to 104 watchers per division.
- The 2024-25 plan (National CAMPA agenda notes, 28th EC) puts the state totals at 85,000 km of fire line (Rs 14.51 crore) and 4,730 watchers; 2025-26 at 139,364 km (Rs 18.90 crore).

What they do **not** hold: km per division, where the lines are, which were actually cut or burnt, when, or any controlled-burn area. The MoEFCC FFPM sanction orders (in `fire_management_practice.md`) oblige geotagged before/after photos and DBT wage records for every km and every watcher, so the execution record exists inside the department; it is not published. Tender portals show no fire-line works for MP (the work is done by daily wage, not contract).

## 2. Where the money goes against where the fire is (`code/newq/out/n8_budget_vs_burning.csv`)

62 units match our scar divisions with 300+ burnt forest ha a year (2017-25 mean).

| | Spearman with burnt forest ha/yr | top-10 burning divisions' share |
|---|---|---|
| fire-line budget (Rs 15-30 lakh in most units) | 0.10 | 17% of budget, 40% of burning |
| watcher budget | 0.24 | 18% of budget, 40% of burning |

The allocation is nearly flat: Khandwa (44,800 ha burnt a year) gets Rs 25 lakh of lines and about 63 watchers, Mandsaur (392 ha) Rs 25 lakh and 83 watchers. Burnt ha per watcher runs from 5 (Mandsaur) to 711 (Khandwa). This is the one thing in the department's records that the scar record can act on directly: a re-allocation of the same Rs 25 crore by nine-season burning would move about a quarter of it into the ten divisions that burn most. The plan's per-division tables (`joint_plan.md`, `j1_by_division.csv`) already say where that would land.

## 3. What the orbit says the department actually burns (`code/newq/n7_dept_burns_patches.py`)

The early-burn flag from `managed_early_burns.md` (day-only, single-day, at most 2 points, FRP at most 5 MW, before 15 Feb) applied to the 3,867 repeat patches, 2017-25 (`out/n7_patch_seasons.csv`, 34,800 patch-seasons):

| | share of patch-seasons |
|---|---|
| a flagged control-like burn inside the patch before 15 Feb | 0.9% (296) |
| any early burning (a VIIRS cluster, or a scar over 5% of the patch) | 1.8% (634) |
| first-programme patches (465) with any early burning in 2023-25 | 10.5%; lines patches 16%; other patches 3% |

So the department (or villagers) already burn early inside about one in ten of the patches the plan names, mostly Ratapani (14 patches), Dewas (11) and Sehore (7): the plan is not proposing something foreign to those divisions. But what gets burnt early is small: the early scar covers a median 0% and a mean 5% of the patch's forest, which is strip burning, not block burning.

Effect, two-way fixed effects (patch, and division-season), weighted by forest ha (`out/n7_effect.csv`):

| treatment | patch-seasons | later burnt share, untreated | effect | relative |
|---|---|---|---|---|
| flagged control-like burn | 296 | 42% | -4.4 points (CI -6.3 to -2.0) | -10% |
| any early burning | 634 | 42% | -6.7 points (-9.0 to -4.3) | -16% |
| early scar over 30% of the patch | 38 | 42% | later share 14% | -66% |

The 38 patch-seasons where a real block got burnt early are the programme as it would actually run, and they burnt a third as much later. The strip burns do little, as expected from `control_burning.md` (a burn protects its own ground, nothing beyond it). This is the closest thing to a ground-truthed measurement of the programme that exists without the department's records.

## 4. What to ask for, if asked at all

One request, to the division or the CAMPA CEO: the FFPM quarterly progress returns (annexure VII) and the geotagged fire-line photos for one division and one season. With those, `n7` becomes an exact test instead of a flag-based one. Until then, section 3 is the measurement.

Files: `code/newq/n7_dept_burns_patches.py`, `out/n7_patch_seasons.csv`, `out/n7_effect.csv`, `out/n7_patches_dept.csv` (every patch: seasons with department-like burning, 2023-25 count); `out/n8_campa_firelines_2025_26.csv`, `out/n8_campa_watchers_2025_26.csv`, `out/n8_budget_vs_burning.csv`.
