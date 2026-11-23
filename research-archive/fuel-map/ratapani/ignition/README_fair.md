# ignition_fits_fair.csv (forecast-fair start points), 2026-10-16

Back-simulation using only what is known at the first detecting pass: first-pass footprints (375 m cells), quiet passes before it, no scar outline, no later passes, no photos. 788 of 809 Ratapani fires (21 had no usable scar). Keyed by `event` (events_viirs id). Script: ../work/scripts/ignition/backsim_v2.py with FAIR=1.

What it shows (plain): with first-pass information alone the start is NOT pinned down.
- Start time: anything from 0 to ~12 h before the first alert fits equally (median window lead_lo 0 h to lead_hi 12 h; `lead_h` = 9 h is just the middle of the grid, not an estimate).
- Start place: ~640 m median spread of equally good points around the first footprint.
- Speed (`speed_k`): unidentified; 83% of fires fit every speed tested (k 1-11). Do not use it.
- 97% of fires reach cost 0, i.e. many solutions explain the first pass perfectly.

Use: as a prior box (place +/- ~650 m, time 0-12 h before first alert), not as a point. The leaky version (ignition_fits.csv) used later passes and outlines and must not be used as a forecast input.
Truth for outlines elsewhere = scar outlines v1 (2026-10-15).
