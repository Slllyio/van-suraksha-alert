# Can 70 m thermal (ECOSTRESS) fix the spread forecast? (17 Oct, Akkshay: "use 70 m thermal then")

Data already fetched by the big-fires thread (research/big-fires/README.md sections 14-14c). The 70 m clips sat in another session's
scratch and are gone. Only each visible pass's hot-pixel centre survives, in ecostress_pass_stats.csv. Script: scripts/eco_front_test.py.

## How much 70 m data there is (2018-2026, Ratapani)
- 520 ECOSTRESS passes fell on burning fires. The strip missed the fire in 242, and 16 were cloudy, leaving 262 usable.
- The fire shows (>= 10 K above background) in **30-31 passes, all by day, 11 on big fires**. That is about 1 usable pass in 7, and none at night.
- No fire has two visible passes, so 70 m can't measure speed.

## Test: place the next 24 h of burning from the 70 m hot front vs from VIIRS dots
- The test runs at the ECOSTRESS time on 25 usable passes.
- Truth is the blend arrival map, which is built from VIIRS only.
- Every rule adds the same (true) new area.

| Rule | Overlap of the added ground with the real new burning (median) |
|---|---|
| Nearest to VIIRS dots seen so far (current) | 0.09 |
| Dots + the 70 m hot centre as an extra dot | **0.16** (better in 10 passes, worse in 3; 95% range +0.02 to +0.12) |
| Nearest to the 70 m hot centre only | 0.24 |

**The control that matters.** In the 18 passes that have a VIIRS look within 1 h of the ECOSTRESS pass, the same-time VIIRS dots do as well as the 70 m centre: 0.153 vs 0.157, with each better in 3 passes. So the gain comes from **one more look at a new time**, not from the sharper 70 m pixel. Where no VIIRS look is near, the ECOSTRESS pass is simply the only fresh look. In 2 passes ECOSTRESS saw the fire before any VIIRS dot.

With the usual 24 ha budget, every rule is near zero (0.01-0.04), because these fires add a median ~120 ha in the next day.

## Verdict
- 70 m thermal helps only as an **extra look in time**.
- It is too rare (day only, ~1 in 7 passes shows fire, 31 passes in 8 years) to change the forecast.
- What would help is more looks in time. Geostationary is not the answer: it was tested in fuel-from-heat (Meteosat IODC 15 min saw ~2% of Ratapani fires; INSAT has the same ~4 km limit). The realistic sources are VNP14IMG raw fire masks (needs EARTHDATA_TOKEN), the MODIS Terra/Aqua passes in alerts_mp, and crew logs from 2027.
- Caveat: only the hot-pixel centre was tested. Re-fetching the full 70 m clips needs EARTHDATA_TOKEN set as an environment secret. With the hot line itself the placement might be a little better, but it would not change how rare the data is.

## Update 11:30Z: full 70 m fire line (clips re-fetched with Akkshay's token, used in-session only)
- 72 clips were re-fetched and 1,145 hot pixels taken from them (>10 K). The test used every hot pixel instead of the centre.
- Dots + the 70 m line scores 0.17 vs 0.09 for dots alone (better in 10 passes, worse in 9).
- **The same-time control on 18 passes:** the 70 m line scores 0.14 and the VIIRS dots from within 1 h score 0.15. VIIRS is better in 8 passes and the line in 4.
- **The answer is unchanged:** the sharper pixel adds nothing. The only gain is having a look at a new time. Files: eco_front_test_line.csv/json.

# Seeding growth from block edges instead of centres (big-fires 14c idea; edge_seed_test.py; 818 unseen fires, 2,246 forecasts)

| Rule (same added area as the 0.477 rule) | 24 h overlap (median) | vs centres (95% range, by fire) | Fires better / worse |
|---|---|---|---|
| Nearest to dot centres (the 0.477 rule) | **0.477** | | |
| Dots pushed 190 m away from the fire's centre | 0.444 | -0.030 to -0.026 | 35 / 672 |
| Latest dots pushed 190 m away from the earlier dots | 0.452 | -0.022 to -0.019 | 64 / 634 |
| Nearest to the outer edge of the block cluster | 0.456 | -0.014 to -0.012 | 58 / 513 |

- **Verdict:** edge seeding loses. Do not adopt it.
- **Caveat:** the "real" timing here is the blend map, which is built from VIIRS dot positions, so it leans toward centres. The independent test is the 340 mid-fire photos. There, "closest to any dot" already beat every learned or shifted rule (spread-review HONEST_TESTS.md).
