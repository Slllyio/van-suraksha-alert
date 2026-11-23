# Burn-scar reference v2 (frozen 16 Oct 2026)

v2 is v1 (`../v1_2026-10-15/`) with one fix. The fresh spread review (research/spread-review/README.md) found that big fires were cut off at the edge of the 3 km image chip, so those outlines have been redrawn. Please cite it as **"scar outlines v2 (2026-10-16)"**. Don't edit these files; later fixes go in v3.

| File | What | sha256 (first 16) |
|---|---|---|
| firms_event_scars.geojson | 5,669 FIRMS event outlines, Ratapani 2017-26 | 5d57f042c65c0e68 |
| firms_alert_scar_lookup.csv | 15,048 FIRMS alerts -> event + scar (`scar_ha_v1` kept, `v2_action`) | f5cced61fc3e03a6 |
| fsi_event_scars.geojson | 1,762 FSI-alert event outlines, 2025-26 | 93d5ea00fea6e46e |
| fsi_alert_scar_lookup.csv | 3,104 FSI alerts -> event + scar | 88c363fb5c180afb |
| v2_changes.csv | one row per redrawn event: v1 ha, v2 ha, chip size, action | dd32155a9ca9e2f5 |

## What changed
**How bad the edge problem was.** 2,171 of 5,669 FIRMS outlines (38%) reached within 40 m of the 3 km chip edge, and those outlines hold 75% of all scar area. For FSI it was 374 of 1,762 (21%).

**How the redraw works.**
- Each edge outline was redrawn with the same method on a 6 km chip. If it still touched the edge, it was redrawn on a 12 km chip.
- Only 214 outlines still touch the edge at 12 km. They carry `still_at_edge = True`.

**Merged neighbouring fires.** A bigger chip can take in a neighbouring fire that burned in the same image gap.
- **FIRMS redraws** are split by fire first, with `split_scars.one`. Each pixel goes to the nearest fire burning in the gap, and the event keeps the ground nearest its own chained alerts and fire pixels.
- If the split result is smaller than v1, the v1 outline is kept. This happened for 521 events, because v1 itself held some neighbouring ground.
- **FSI points** have no seed chain, so a FSI redraw is used only if it grew 3x or less. Otherwise v1 is kept: 54 events, flagged `grew_into_large_burn_v2`.

**Result by action:**

| | events | v1 total ha | v2 total ha | median v2/v1 |
|---|---|---|---|---|
| FIRMS redrawn and split | 1,639 | 318,779 | 715,129 | 1.52 (IQR 1.15-2.48; 90th pct 4.3) |
| FIRMS kept v1 (split smaller) | 521 | 85,672 | same | 1 |
| FSI redrawn (3x or less) | 320 | 51,621 | 74,396 | 1.21 |
| FSI kept v1 (grew more than 3x) | 54 | 10,974 | same | 1 |

**Totals.** All FIRMS outlines go from 541,856 to 938,207 ha (+73%), while the median outline barely moves (60.6 to 62.0 ha). The change sits in the big fires. FSI goes from 106,383 to 129,158 ha (+21%). The totals double-count ground shared by events of the same fire.

**Is the added ground really burned?** 175 redrawn FIRMS fires have an Esri Wayback sub-metre image within 40 days (`check/check_added.py`).
- In 91% of them (92% when the image is 15 days old or less), the ground v2 adds is darker than a 150 m ring outside the new outline.
- Ground next to a scar that was *not* added was darker only 42% of the time in the 15 Oct grow test.
- Median brightness: v1 54.5, added 55.7, ring 62.5. The added ground looks like the v1 burn.

**Code.** `../../scripts/alert_scar.py` now does this redraw by default (`auto_expand`, with a 3x guard instead of the split), so the live run and the all-MP run draw full outlines from now on. The tiger-reserve and all-MP sample scars from 15 Oct were drawn before this change.
