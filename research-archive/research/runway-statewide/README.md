# Which side of a new fire burns farther: statewide test (18 Oct 2026)

Akkshay asked for the continuity thread's "runway" hint "after proper scientific research". That thread found 63-66% on 146
Ratapani big fires. This redoes it on all 9 MP tiger reserves with the same rules, then builds it into the field app
(`field-system/app/runway.py`, officials' card).

## Data
- **Fires:** 4,051 tiger-reserve burn scars 2017-25 with 4,104 scored fronts (`fire-alert-scars/mp/out/scars_tiger_reserves.csv`; status scar, 10 ha+, not cut by the chip edge). No Ratapani fires are in this set, so it is fully separate from the continuity work.
- **Fronts:** the same as c10. A fire's looks are split by gaps over 2 h. The first look's dots are linked within 750 m, then later groups more than 750 m from earlier dots.
- **Truth:** 36 rays every 10° from the dot centre, measuring how far each ray runs inside the scar (stop = 60 m unburned in a row). Censored rays (cut by another front) are not scored; that is 0.9% of rays.
- **Inputs:** sampled from the dot centre along the full 0-2 km ray, so the scar is never an input (the c15 leak fix).
  - ESA WorldCover 10 m: tree, grass, crop, forest edge.
  - Copernicus DEM 30 m: local height, grade, slope, valley floor.
  - Overture 2026-09 roads (3.3 M segments).
  - Earlier seasons' scars.
  - The front's own dots: FRP-weighted offset ("hot side"), long axis, bearing from earlier dots.
- **Scripts:** `scripts/r1_events.py`, `r2_rays.py`, `r3_score.py` (rules and held-out models), `r4_checks.py` (dot-offset checks), `r5_final.py` (app model).

## Results
Scoring is as in c14/c15: the rule's best sector against its worst sector, and the rule is right if the best one really burned farther. Chance is 50%. The 95% range comes from a bootstrap over fires.

| rule (9 sectors of 40°) | right | best sector past 500 m vs worst |
|---|---|---|
| most tree cover (c14/c15 rule) | 58% (56-59) | 15% vs 11% |
| farthest to first road / forest edge / crop | 60% (59-62) | 17% vs 9% |
| uphill side | 57% | 17% vs 11% |
| hot side of the dots | 56% | 19% vs 16% |
| **model, ground + dots, other reserves held out** | **68% (67-69)** | **20% vs 8%** |
| model, ground + dots, other seasons held out | 68% (66-69) | 21% vs 8% |
| model, first-look fronts only (other reserves) | 68% (66-70) | |

- **Card version** (8 compass sides, past burns left out because the app has no statewide burn history), other reserves held out: **67% (66-69)**. The named side burned past 500 m 20% of the time against 9% for the least likely side. It names the single farthest side 21% of the time against 12.5% by chance.
- **By reserve** (held out): Bandhavgarh 70%, Kanha 69%, Sanjay-Dubri 70%, Madhav 68%, Veerangana Durgavati 67%, Panna 66%, Pench 61%, Satpura 63%.
- **What drives it** (model gain):
  - local height within 300 m: 20%;
  - slope direction within 300 m: 11%;
  - the hot side of the dots: 10%;
  - then distance to the first road, forest edge, valley floor and crop: 6% each.
  - Land cover share adds little: terrain + dots alone gives 65%. Roads add 1.5 pts and past burns 1 pt.

## Is it real?
- **Null tests:**
  - scoring each front with another front's map gives 50% (49-51);
  - rotating a front's own map gives 46%.
- **Not the VIIRS dot being off-centre** (median dot-to-scar-centre 197 m, against median reaches of 200-450 m):
  - fronts whose dots sit within 150 m of the scar centre score 69%;
  - 150-300 m: 68%;
  - 300-600 m: 67%.
  - The named side points at the scar centre only 35% of the time (chance 25%), so the model is not just finding where the scar sits.
- **By fire size:**
  - 10-50 ha: 68%;
  - 50-100 ha: 68%;
  - 100-200 ha: 66%;
  - 200 ha+: 63% (only 47 fronts).

**Verdict:** a real, moderate signal, a little better than in Ratapani (63-66%). The named side burns past 500 m about twice as often as the least likely side. It stays a hint for officials, not a dispatch rule: 1 in 3 times the named side is wrong.

## In the app
- `field-system/app/runway.py` runs once at a new fire's first VIIRS look, with the same new-fire rule as the big-fire points. It takes about 4 s a fire (public cloud reads plus `data/runway/mp_roads_40m.tif`, 13 MB).
- The trees are evaluated in numpy and give exactly the LightGBM numbers.
- On 120 statewide fronts the app's live inputs gave the same named side as the research table 98% of the time (`scripts/runway_check.py`).
- **Card example:** "Likely to burn farther toward the NW (forest, uphill); least toward the E (forest edge 180 m)."
- **Officials only.** It never changes the alert, its order or the search area.
