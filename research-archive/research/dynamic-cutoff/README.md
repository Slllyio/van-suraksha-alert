# Burn cut-off by division and through the season (19 Oct 2026)
Akkshay (10:01Z Oct 19): decide the "burnt square" cut-off per division from its fire conditions, not one strict number, and let it change through the season. Squares are 500 m = 25 ha.

## A. Statewide: how big is a normal burn? (`scripts/a_division_month.py`, `results/a_*`)
62,953 burn scars, 75 divisions, 15 Feb-31 May 2022-25.
- Median scar: Sendhwa 14 ha, Khargone 14, Ratlam 15, Kanha 18 ... Khandwa 77, Panna TR 80, Damoh 83, Noradehi 111, Kuno 150, Rewa 155. An 11x spread.
- It is a division trait: division medians in even vs odd years agree (Spearman 0.81).
- Through the season, statewide medians: 35 ha (15 Feb-15 Mar), 45 ha (16 Mar-15 Apr), 32 ha (16 Apr-15 May), 17 ha (late May). The season shape differs by division (west: Dhar, Alirajpur, Jhabua biggest early; Panna, Harda, North Betul, Kuno biggest late) and is only moderately repeatable (0.51).
- Size variance explained: division 8%, phase 2%, division x phase 11%. Most of the variation is fire to fire.

## B. 10 regions: does a division-and-phase cut-off give a better map? (`scripts/b_model_test.py`, `results/b_*`)
Region held out; inputs controls + frozen Prithvi + phase + in-season dryness + burnt earlier this season. The local cut-off is the median burnt share of burnt squares in that region and phase in other seasons.

Local cut-offs (share of square; x25 = ha):

| Region | 15 Feb-15 Mar | 16 Mar-15 Apr | 16 Apr on |
|---|---|---|---|
| Khandwa | 35% (9 ha) | 52% (13) | 31% (8) |
| Dewas | 29% (7) | 46% (11) | 30% (7) |
| South Betul | 45% (11) | 38% (10) | 27% (7) |
| South Chhindwara | 37% (9) | 42% (11) | 30% (8) |
| South Balaghat | 24% (6) | 38% (9) | 34% (8) |
| Dindori | 19% (5) | 23% (6) | 21% (5) |
| Umaria | 29% (7) | 42% (11) | 28% (7) |
| Chhatarpur | 21% (5) | 46% (11) | 33% (8) |
| Panna TR | 18% (4) | 54% (13) | 42% (11) |
| Satpura TR | 24% (6) | 41% (10) | 25% (6) |

Map quality (flag top 20% of squares in each region-season-phase; share of burnt hectares inside):

| Model target | Burnt ha caught | Local big burns caught |
|---|---|---|
| any burn | 40.0% | 41.0% |
| fixed 30% | 42.4% | 43.8% |
| division+phase cut-off | 42.6% | 44.3% |
| share itself (no cut-off) | 41.8% | 42.7% |
| division+phase cut-off, no Prithvi | 39.5% | 40.4% |

- Division+phase cut-off vs fixed 30%: +0.2 pts (6/10 regions, CI -0.4 to +0.8). Same map; "any burn" as target is worse (-2.4).
- Prithvi gain (ha caught) by phase: +5.0 early, +3.6 peak, +1.3 late. By region: Satpura +15, Dindori +9, Panna +7, Dewas +6, Umaria +5; negative in Balaghat, Betul, Khandwa, Chhatarpur.

## C. In-season update (`scripts/c_dryness.py`, `results/c_dryness.json`)
Same model with vs without HLS dryness from the 10-day step before each phase: early -2.2, peak -0.9, late +1.9 pts. Late-season gain in Panna +10.8, Dewas +8.3, Khandwa +7.1, South Chhindwara +5.7; loss in Satpura -6.6, Umaria -5.4.

## What it means
1. Use the division-and-phase cut-off to define and report a "significant burn": Dindori ~5-6 ha all season, Panna 4 ha early but 11-13 ha later, most divisions ~7-9 ha early/late and ~10-13 ha at peak. It costs nothing in map quality.
2. The cut-off does not change which squares get flagged. The map changes through the season because the pre-season image signal fades (Prithvi +5 early to +1.3 late).
3. A mid-season update helps late fires in some divisions (Panna, Dewas, Khandwa, South Chhindwara) and hurts in others (Satpura, Umaria), so switch it on per division.

## D. Switching inputs per division and phase (`scripts/d_switch.py`, `results/d_switch.json`)
For each region and phase, pick full / no Prithvi / no dryness update using the other seasons only, then score the held-out season (burnt ha caught in top 20%, mean over region-phase-seasons).

| Choice | Burnt ha caught |
|---|---|
| no Prithvi | 39.5% |
| full model, same everywhere | 42.6% |
| no dryness update everywhere | 43.0% |
| switch per region + phase | 43.7% (+1.0 vs full, CI +0.2 to +1.8; 3/4 seasons, 7/10 regions) |
| best possible switch (hindsight) | 47.9% |

Verdict: switching is a small real gain (~+1 pt). With these inputs the burn map sits at ~43-44% of burnt hectares in 20% of squares.
