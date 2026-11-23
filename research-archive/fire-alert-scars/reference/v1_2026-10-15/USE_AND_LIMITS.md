# Scar outlines v1: how uncertain they are, and what to use them for

## How uncertain (blind check on sub-metre imagery)

Esri Wayback sub-metre images taken 15 days or less after the fire were available for 202 Ratapani fires. The same outlines were also moved 3 km into unburned forest as decoys. Scripts: `check/zones.py`, `check/zones_summary.py`. Per-fire numbers: `check/zones_per_fire.csv`.

**Method.** Points could not be read one by one by eye. At the scale needed to see a whole fire, burned litter under canopy is not visible point by point, so that attempt was dropped. Instead, each fire's image is split into zones, and each zone's brightness is placed between two references from the same image:
- "Burned" is the outline core, more than 40 m inside the edge.
- "Unburned" is a ring 400-700 m out.

Running the same calculation on the decoys gives a noise floor of a 15-18% "burned share", and that floor is subtracted from every zone.

**Readable fires.** Half the real fires (50%) have a core clearly darker than the far ring, against 10% of decoys. The other half can't be judged on these images either way:
- Images of 2017-19 fires: 76% readable.
- Images of 2020-25 fires: 21-31% readable.

So the error bands below come from the 102 readable fires only.

| Per fire, as a share of the outline's own area | median | middle half (IQR) | 90th pct |
|---|---|---|---|
| **False area**: ground inside the outline's 40 m edge that is not burned | 9% | 6-13% | 23% |
| **Missed area**: burned ground within 250 m outside the outline | 22% | 0-59% | 146% |

**By size:**
- Missed area is a median 19% for large outlines, 11% for medium and 88% for small (under about 20 ha), so small fires are mostly under-drawn.
- False edge area is 9-13% at every size.
- In 36% of readable fires essentially nothing burned was missed.

**Two more limits:**
- **Whole-outline false positives.** From the earlier blind decoy check (README "Improvements tested 15 Oct"), "yes" scars are visibly real 81% of the time when imaged within 3 days, 76% at 4-15 days and 58% at 16-40 days. Faint scars are real only about 1 in 3.
- **Not measured.** The core itself is assumed burned. Burned ground more than 250 m outside the outline was not checked.

## What the outlines are good for
- **Fire size**, as a lower-leaning estimate. For medium and large fires the outline is about right: roughly 10-20% too small, plus up to 9% false edge. Small fires are under-drawn.
- **Shape and footprint scoring** (spread and footprint models), with these error bands quoted. A model scored against v1 cannot be judged better than about ±10-20% of area for medium and large fires.
- **"Did this alert burn ground, and roughly where"**, for monitoring by officials.
- **Which cells burned in a season.** These are the preferred truth over the research burn-label rasters, which miss 85% of the extra ground (spread README 4k).

## What not to use them for
- **The day a cell burned.** The outline sits between `pre_date` and `post_date`, which can be 1-3 weeks apart. For timing, use VIIRS dating (out/af/dated_first_burns.csv).
- **Exact edges at 20 m.** Errors run 40 m and more at the edge, and burned ground is often missed within 250 m.
- **Small fires (under about 20 ha) as size truth.** They are typically about half their real extent.
- **Counting `none_visible` alerts as false alerts.** They are often small or under-canopy burns.
- **The 341 FIRMS and 62 FSI outlines flagged `grew_into_large_burn`.** They kept their smaller first-image outline, so treat them as under-drawn.

**When you publish a result scored on these outlines,** state: "truth = scar outlines v1 (2026-10-15), error bands per USE_AND_LIMITS.md".
