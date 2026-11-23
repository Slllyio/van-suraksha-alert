# 2026 burn scars, all MP (built 20-21 Oct 2026 by the large-fires thread)
Same method as fire-alert-scars/mp 2017-25 history: FIRMS 2026 MODIS, S-NPP, NOAA-20 (no NOAA-21), 15 Feb-15 Jun, inside MP beats, events = same day within 1 km, forest >= 10% tree+shrub within 375 m (`../scripts/l12_scars2026_prep.py`), then `fire-alert-scars/mp/scripts/mp_run.py`.
- `set_2026.csv`: 19,019 forest events (event_id, seed point, Division/Range/Beat).
- `scars_2026.csv`: one row per event, status (scar 16,468; scar_faint 893; no_scar_seen 1,648; error 9; waiting 1), areas, dates.
- `scars_2026_geom/`: outlines as WKT, one gzip per batch: `pd.concat(pd.read_csv(f) for f in sorted(glob('scars_2026_geom/*.csv.gz'))).drop_duplicates('event_id', keep='last')`.
- `alert_event_2026.csv`: every alert with its event_id.
Chained into 12,117 fires (368 of 200 forest ha+) by `../scripts/l13_fires2026.py`.
