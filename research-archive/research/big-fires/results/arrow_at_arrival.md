### Arrow vs VIIRS dots at the time the arrow actually arrives (`b19d_arrow_at_arrival.py`, results/arrow_at_arrival.json, 20 Oct)

**Why.** In live use the Sentinel-2 scene (~10:30-10:45 IST) is only published about 5-6 h later (~16:00-17:00 IST). By then the afternoon VIIRS look (~13:30 IST) is already in. The fair test therefore gives the dots every VIIRS look up to scene + 6 h, and scores both against burning that happens *after* scene + 6 h.

**How.** The test uses the same 235 usable passes as 15f, with the same burnt patch, hot pixels, scars and VIIRS-look timing map. The rerun gives exactly the 15f angles on all 234 arrow and 142 dots passes. The comparisons are:
- **Arrow**: unchanged.
- **Dots before**: the 15f rule (earlier looks to the latest look before the scene).
- **Dots at arrival**: the same rule, with looks up to scene + 6 h.
- **Truth at arrival**: the part of the scar outside the burnt patch that the timing map has burning after scene + 6 h. The alerts only run to scene + 30 h, so this equals "new burning in the 24 h after arrival", and the two give identical numbers.

Each direction is compared with the line from the burnt-patch centroid to the truth centroid. CIs are 95% bootstrap over fires.

**Every one of the 235 passes has a VIIRS look between the scene and scene + 6 h** (median 2.2 h after the scene; by construction the scene is 0-3.5 h before a VIIRS day pass). With that look, the dots give a direction on all passes, not 142 of 235. Only 143 passes (129 fires) still have at least 2 ha of scar burning after scene + 6 h; on the other passes the fire was mostly done by the afternoon.

| direction estimate | truth: burning after scene + 6 h | passes | within 45 deg (95% CI) | median angle |
|---|---|---|---|---|
| burnt patch -> 30 m hot line (arrow) | yes | 143 | **58% (50-66)** | 36 deg |
| dots, looks before the scene | yes | 97 | 54% (43-64) | 40 deg |
| dots, looks up to scene + 6 h | yes | 143 | **56% (47-65)** | 39 deg |
| **paired: arrow minus dots-at-arrival** | yes | 143 | **+2 points (-6 to +11)** | |
| paired: arrow minus dots-before | yes | 97 | +7 points (-8 to +21) | |
| early fires (<=2 looks before scene): arrow vs dots-at-arrival | yes | 91 | 53% vs 55%, -2 (-13 to +9) | |
| later fires (>=3 looks): arrow vs dots-at-arrival | yes | 52 | 67% vs 58%, +10 (-4 to +23) | |

The 15f truths, which partly overlap the afternoon look, show the leak. On the scar remainder, dots-at-arrival reach 62% against the arrow's 65% (+2, CI -5 to +9). On the 0-24 h new burning they reach 73% against the arrow's 66% (-7, CI -15 to +1). The afternoon look is already part of that truth, so its gain there is not a forecast.

**Verdict.** Once the afternoon VIIRS look is in, the arrow no longer beats the dots. On burning after it would arrive, the arrow and dots are level: 58% vs 56%, with a CI of -6 to +11 points. The 19-point lead in 15f came mostly from giving the dots only the morning looks. There may be a small edge on longer-running fires (+10, not significant), and none on early fires. The arrow stays a useful same-evening confirmation, but it is not a better direction than the latest VIIRS dots.
