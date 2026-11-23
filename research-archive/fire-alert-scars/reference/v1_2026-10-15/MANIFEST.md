# Burn-scar reference v1 (frozen 15 Oct 2026)

A fixed copy of the per-alert burn-scar outlines for Ratapani, so other threads can score against one versioned truth.
The files are read-only. Later fixes will go in a new folder (v2_...), so these files never change.
When you use them, cite them as **"scar outlines v1 (2026-10-15)"**.

| File | What | Rows | sha256 (first 16) |
|---|---|---|---|
| firms_event_scars.geojson | One outline per NASA FIRMS fire event, 2017-2026, Ratapani | 5,669 (5,312 scar, 357 faint) | 29254be03b9cad64 |
| firms_alert_scar_lookup.csv | Every FIRMS alert -> its event and scar | 15,048 | ee1716a8c7ea37ab |
| fsi_event_scars.geojson | One outline per FSI-alert event, 2025-26 | 1,762 (1,666 scar, 96 faint) | 64ac0309c0b276e6 |
| fsi_alert_scar_lookup.csv | Every FSI alert -> its event and scar | 3,104 | 2ba8a8f06a9d6ae1 |

**Method version:** `alert_scar.py`, grow_to_check=True, as of 15 Oct 2026. Each outline is built in four steps:
1. A Sentinel-2/Landsat 20 m relative NBR drop between the last clear look before the fire and the first clear look after it.
2. A persistence check at a later look.
3. FireCCI-style growth.
4. Growth into connected ground that has also dropped by the later check look (`check_date`).

Field notes:
- `scar_ha` is the final area. `scar_ha_post` is the area from the first post-fire image alone.
- `grew_into_large_burn = True` marks 341 FIRMS and 62 FSI outlines that would have grown more than 3x, which usually means merging into a later fire. They keep their first-image outline.
- `status = scar_faint` is a weak scar. On sharp imagery only about 1 in 3 are real, so treat them as "possible".
- `pre_date` / `post_date` give the image pair. The fire happened somewhere between them, and that window can be 1 to 3 weeks wide.

The uncertainty check and the notes on what these outlines can and cannot be used for are in `USE_AND_LIMITS.md`.
