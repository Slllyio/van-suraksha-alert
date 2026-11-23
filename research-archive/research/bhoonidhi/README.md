# Bhoonidhi (NRSC/ISRO) imagery for MP fires (20 Oct 2026)

Akkshay (06:14Z): "i have the bhoonidhi login so i think their high resolution imageries can help us".

## Bottom line
The free Bhoonidhi optical sensor (AWiFS, 56 m) would put a scene on many more burning fires than Sentinel-2 alone. But that scene keeps only about a quarter of Sentinel-2's value, because AWiFS has no 2.2 µm band. The sharp sensors (LISS-III 23 m, LISS-IV 5.8 m, Cartosat) are paid and rarely over a fire. Not worth building on. Login not needed for any of this.

## What Bhoonidhi has over MP, fire season 15 Feb-15 Jun (catalog/, guest search of the portal)
| Sensor | Pixel | Cost | Days/season with an MP scene | Fires with a scene while burning |
|---|---|---|---|---|
| Sentinel-2 (for comparison, cloud < 80%) | 10-20 m | free | - | 18% |
| AWiFS, RS-2 + RS-2A (2017-24) | 56 m | free, ordered | ~150 | 31% (S2 + AWiFS 40%) |
| AWiFS, RS-2A only (today: RS-2 ended Jun 2025) | 56 m | free, ordered | ~65 | 13% (S2 + AWiFS 27.5%) |
| LISS-III (2024-25) | 23 m | PAID | 72-112 | 1.4% |
| LISS-IV (2024-25) | 5.8 m | PAID | 59-101 | 0.7% |
| EOS-04 radar (2022-25) | 18 m | free, ordered | 45-57 | 2.7% (radar does not see fire) |
Fires/passes exactly as big-fires 15h (137,605 fires 2017-25). AWiFS counted with no cloud screen (catalog has none); Mar-Apr Sentinel-2 cloud >= 80% is 2.5-14%, so AWiFS shares are a little high. AWiFS passes at the same ~10:30 IST as Sentinel-2, so it adds days, not a new time of day. Big fires already get one: 4+ day fires S2 69% -> 80% with RS-2A.

## Does an AWiFS scene help? (scripts/awifs_sim.py, results/awifs_sim.json)
Same test as spread section 16 (24 h map: scene burnt patch + hot line vs dots with the same area), on 359 Sentinel-2 fire scenes, with the scene degraded to AWiFS (3x3 mean to 60 m; red, NIR, 1.6 µm SWIR only).
| Scene | Gain over same area (95% CI) | Hot line found | Burnt patch (median ha) |
|---|---|---|---|
| Sentinel-2 as is | +0.029 (0.017-0.042) | 100% | 157 |
| Sentinel-2 at 60 m | +0.027 (0.016-0.038) | 90% | 155 |
| Sentinel-2 20 m but 1.6 µm only | +0.014 (0.010-0.019) | 71% | 4 |
| AWiFS-like, dNBR(1.6) >= 0.10 | +0.006 (0.003-0.009) | 31% | 3 |
| AWiFS-like, dNBR(1.6) >= 0.05 | +0.007 (0.001-0.012) | 31% | 31 |
| AWiFS-like, NDVI drop >= 0.10 | +0.008 (0.001-0.014) | 31% | 38 |
Pixel size is not the problem; the missing 2.2 µm band is. Caveat: these scenes were chosen because Sentinel-2's 2.2 µm band showed >= 3 hot pixels, which favours Sentinel-2.

Net: today's RS-2A adds a scene to ~10% more fires at ~1/4 of the value = worth about +2-3 points of Sentinel-2-equivalent coverage. Below the noise of anything downstream.

## Access facts
- Portal guest search (POST /bhoonidhi/ProductSearch, scripts/qp.py) works from the cloud, no login. Rate-limited; run one process at a time.
- STAC API (bhoonidhi-api.nrsc.gov.in) resets connections from the cloud. Download needs login; only products marked Online=Y download by API, older ones ("OpenData_OnOrder") go through Browse & Order.

## EOS-04 radar for fire scars (20 Oct ~10:30Z, after Akkshay shared his team's EOS-04 code bundle)
The bundle (E:\FIRE\"Document from Akkshay Rathore", a zip) is a working EOS-04 L2B pipeline from the eNetra disturbance work: API token,
order list, download of Online scenes, clip to a 10 m grid, and a "new pass vs last 3 passes" HV/HH drop rule (Guna 2026). The zip also holds
a .env with the Bhoonidhi login; our cloud copy was deleted and nothing from it is stored here.
Test before downloading anything: same C-band on Sentinel-1 RTC (Planetary Computer), 390 MP forest scars 2022-25 (20-2000 ha), post scene
1-30 d after the fire, pre scene same orbit 1-40 d before; change inside the scar minus a 300-1500 m ring; decoy = same shape 3 km east.
Script scripts/s1_scar_test.py, results/s1_scar.json.
| | Scars | Decoys |
|---|---|---|
| VH change vs ring (median dB) | -0.13 | 0.00 |
| VV change vs ring (median dB) | -0.10 | -0.01 |
| Scars with a clear VH drop (pixel AUC >= 0.7) | 3.1% | 0.3% |
| Scar vs decoy separation (AUC) | 0.68 (VH) | |
Brighter-burn scars (RdNBR 0.2-0.3) drop more (-0.34 dB), still far below the ~1 dB a person or a rule can see. Litter fires under standing
teak leave the canopy, which is what C-band sees. Sentinel-2 finds ~90% of the same fires. Verdict: EOS-04 (and C-band in general) does not
see MP fire scars; the dry season is cloud-free, so radar's one advantage does not apply. Not worth ordering or downloading for fires.

## Faster Sentinel-2 (Copernicus instead of Planetary Computer): tested, no gain (20 Oct ~10:30Z, coordinator relay)
Delay after the pass (scripts/lat.py, results/cdse_latency.csv, CDSE OData PublicationDate - sensing, MP scenes):
| Product | 2026 (3,660 scenes) p10 / median / p90 | 2025 (898) median |
|---|---|---|
| L1C | 4.0 / 5.0 / 5.5 h | 5.3 h |
| L2A | 4.4 / 6.0 / 6.5 h | 6.4 h |
Scenes are sensed ~05:15 UTC (10:45 IST), so CDSE has them ~16:00-17:00 IST. Planetary Computer had all 8 of the last 8 days' MP scenes
on 20 Oct 09:45Z (so <= ~28 h), but none of 18 Oct's 13 h after (app/cdse.py note). The 13:30 IST VIIRS pass reaches the app ~14:30 IST,
always before any Sentinel-2 product.
Value of the scene by when it arrives (scripts/delay_test.py, results/delay.json; 359 Sentinel-2 mid-fire scenes, statewide; the map is
made at scene + lag with every VIIRS look up to then; truth = burned by forecast + 24 h; same rules as spread s16):
| Scene used at | Scene gain over same area (95% CI) | Better / worse fires |
|---|---|---|
| scene time (impossible live) | +0.031 (0.018 to 0.043) | 220 / 125 |
| +3 h (after the 13:30 VIIRS look) | +0.004 (-0.007 to 0.015) | 170 / 159 |
| +6 h (Copernicus) | +0.004 (-0.006 to 0.014) | 169 / 164 |
| +12 h | +0.004 (-0.006 to 0.014) | 168 / 165 |
| +24 h (Planetary Computer) | +0.007 (-0.004 to 0.016) | 168 / 161 |
The scene's own information (burnt patch, hot line) is worth +0.03 only before the afternoon VIIRS look; once that look is in, it adds
nothing measurable, whether the scene comes 6 h or 24 h after the pass. Copernicus vs Planetary Computer does not matter for the map.
(Using the scene's total area still beats the dots-only rule by +0.02-0.03 at every lag, but that is the area, which the learned 24 h area
already supplies.) Verdict: no faster-imagery lever for the spread map; the "~0.53 on scene days" in spread s18 is not reachable live.
