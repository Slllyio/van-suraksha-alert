# Dating every scar pixel from Sentinel-2 + Landsat: pilot, dead end (19 Oct 2026)

Question: can the 20 m scar pixels get their own burn day from optical looks, so that ground VIIRS missed gets a date? Such a date would feed the spread thread's map check.

Method (../scripts/pixel_dating.py): 150 random 2025 scars of at least 20 ha (15 Feb-15 Jun). Every clear S2 L2A and Landsat 8/9 look from 20 days before to 30 days after the first alert was used. Each pixel's NBR drop was measured against its own pre-fire median and against unburnt ground in the same chip. The burn window runs from the last clear look before the drop to the first clear look with a persistent drop of 0.10 or more. For the check, VIIRS points (S-NPP, NOAA-20, NOAA-21) within 300 m were taken as the pixel's VIIRS day. Two baselines: (a) VIIRS days shuffled among the pixels of the same fire, (b) every pixel given the fire's median VIIRS day. Files: events.csv, pixels.parquet.

| measure | result |
|---|---|
| scar pixels given a window | 89% |
| window length (median, IQR) | 4 days (3-5) |
| windows of 3 days or less | 38% of pixels |
| pixels with no VIIRS point within 300 m | 27% |
| of all pixels: unseen by VIIRS and dated to 3 days or less | 8.5% |
| VIIRS day inside the pixel window (+1 day) | 85% |
| same, VIIRS days shuffled within the fire | 81% |
| same, the fire's median VIIRS day for every pixel | 86% |
| multi-day fires (51): pixel / shuffled / fire median | 83% / 76% / 86% |
| within-fire order, window end vs VIIRS day (multi-day fires) | rank corr 0.21 median, positive in 84% of fires |

Verdict: **not worth building out.**
- A window is about 4 days wide, set by how often S2 and Landsat get a clear look. VIIRS looks every ~12 hours.
- The pixel windows hold some real within-fire order: 83% vs 76% when shuffled. But simply giving every pixel the fire's own VIIRS days (86%) does better. On the ground VIIRS missed, only about 1 pixel in 12 gets a window of 3 days or less.
- This agrees with fire-continuity: within-gap timing can only be judged from photos, and the blend map is already 84% right on those photos. A 4-day optical window cannot improve that. HLS uses the same S2 and Landsat looks, so it would not narrow the window either.
