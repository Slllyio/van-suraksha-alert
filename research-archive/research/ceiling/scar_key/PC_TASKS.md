# Two PC jobs after the quiet-share run (from thread "Is the project at its limit", 18 Oct)

Predictions stay on the PC. Only results tables leave it (PR #1, as usual).
Inputs for job B are on vanagni branch `claude/project-thread-v0whah`, folder `data/scar_key/`. Copy them to `E:\FIRE\mp\scar_key\`.

## Job A: statewide crew budget (no new model)

Use the current +GIS model's saved predictions (calibrated %), held-out 2022-24 and forward 2025-26.
Each day, keep the statewide number of flags equal to the sum of that day's danger-scaled per-division counts, so the total workload is unchanged. Then compare:

1. **Current rule:** each division gets its own count.
2. **Statewide pool:** the day's total goes to the highest calibrated % squares anywhere in MP.
3. **Statewide with a floor:** each division keeps at least 50% of its own count, and the rest is pooled statewide.

Score strict, each fire once, at matched total ground. Report:
- all fires, brand-new fires, beat episodes and ground;
- fires caught per 100 flags;
- how many divisions lose more than half their flags under rules 2 and 3, and which ones.

## Job B: the model on a burn-scar answer key

Files: `scar_key.parquet` (event_id, ld = IST date, row, col on the mp_grid, is_alert, under_scar, status) and `scar_events.parquet`.
- 73,050 forest fire events, 15 Feb-31 May 2022-2025, from the scar thread.
- 86% have a clear scar.
- The squares are the alert's own square plus every square at least 10% under the scar outline. The median event covers 4 squares.

An event is caught if one of its squares is flagged, or next to a flag, on day ld-1 or ld-2. An event belongs to the division that holds its alert square. Brand-new means no VIIRS point within 5 km on days ld-7 to ld-1, for every alert square.

Score the current model's held-out predictions (2022-24) and forward predictions (2025 only; there are no scars for 2026 yet) on four keys, each for all fires and for brand-new fires:
- `alert_all`: alert squares, every event;
- `alert_scar`: alert squares, scar-confirmed events only;
- `scarsq_scar`: all squares under the scar, scar-confirmed events;
- `alert_noscar`: alert squares, events with no scar seen.

Compare with the simple-rule numbers in the shared folder, `research/ceiling/scar_key/scar_rules_summary*.json`. The cloud thread will add them to the README.
