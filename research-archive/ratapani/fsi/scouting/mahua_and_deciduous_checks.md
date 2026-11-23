# Two field ideas from Akkshay, checked on our own data (FSI thread, 16 Oct 2026)

Akkshay (16 Oct 14:45Z):
1. Fires in Feb-Mar come from mahua collection, so ignition points should sit where mahua trees are dense.
2. Once a fire reaches a deciduous patch, the shed dry leaves keep it going.

There is no field data, so both checks use satellite proxies only. Code is in `code/akkshay_checks/` and outputs in `data/akkshay_checks/`.

## 1. Mahua and Feb-Mar ignitions

**Data.**
- 4,077 first-day ignition points (`data/ignition_points.csv`, 2017-26) in 3,241 forest cells of 500 m.
- Mahua proxy: the share of "hot-season flusher" pixels per cell, meaning trees that green up in April-May while the forest dries (`data/mahua/flush_cells.csv`, `mahua_tendu_mapping.md`). It is NOT a mahua map: it also catches kusum, achar and other flushers. No real mahua tree map exists.

**Result: change in ignition rate per 1 standard deviation more flusher share.** The controlled column holds hamlet distance, February greenness and forest share fixed. CIs are 95%, from a cell bootstrap.

| Period | Ignitions | Raw | Controlled |
|---|---|---|---|
| 1 Jan - 14 Feb | 566 | 1.25 (1.15-1.33) | 1.12 (1.04-1.22) |
| 15 Feb - 31 Mar | 2,337 | 1.06 (1.01-1.11) | 1.05 (1.01-1.10) |
| April | 880 | 0.97 (0.90-1.05) | 1.00 (0.93-1.08) |
| May - June | 290 | 0.97 (0.86-1.09) | 0.91 (0.80-1.02) |

- The top-fifth flusher cells get 1.27x the Feb-Mar ignitions of the bottom fifth. In April the ratio is 1.02.
- Early-season ignitions sit deeper inside the forest. The median distance to the nearest hamlet is 2.2 km for January to mid-February and 1.8 km for Feb-Mar, against 1.7 km in April. Only 13-18% of early ignitions are within 1 km of a hamlet, against 25-27% from April to June. This fits collectors walking to their own scattered trees, which a PARI report puts every 100-200 m inside the forest (`human_fire_drivers.md` 1.6).

**Reading.**
- The direction supports the idea: flusher-rich cells get more ignitions in the early season and not later.
- The effect is small: about +5% per standard deviation in Feb-Mar.
- This proxy cannot prove or disprove "all Feb-Mar fires are mahua". It mixes species, and mahua's own signal (leafless with flowers in March, new copper leaves in April) is diluted.
- [inference] A sharper test needs a real mahua tree map: PlanetScope or sub-metre imagery in March, or the department's own mahua counts by compartment.

## 2. Do fires keep burning into deciduous patches?

**Test.**
- Truth: 15 Feb - 15 Jun scar outlines v1 (`fire-alert-scars/event_scars.geojson`).
- Cover classes from `fuel-map/ratapani/cover_phenology_10m.tif`: 1 deciduous tree, 2 green-in-dry-season tree, 4 open grass/low cover. The test runs at 20 m.
- For each scar, I took a 40 m band just inside the edge and a 40 m band just outside, excluding ground already burned earlier that season.
- Null: the same outline shifted 500-800 m, where inside and outside should look alike.

**Share of each cover class, inside vs outside the edge.**

| | Deciduous tree | Green tree | Open grass/low |
|---|---|---|---|
| Real edge, inside | 66.4% | 9.8% | 23.7% |
| Real edge, outside | 61.7% | 9.6% | 28.5% |
| Shifted null, inside / outside | 61.2 / 61.3% | 9.8 / 9.6% | 28.8 / 28.8% |

- The same pattern holds in each period: 15 Feb-Mar 67.4 vs 62.4% deciduous; April 63.3 vs 59.4%; May-June 63.8 vs 59.8%.
- Fires stay inside deciduous tree cover and tend to end where it gives way to open grass or low cover. Deciduous is 1.08x over-represented inside the edge; grass is 0.83x.
- Leaf-fall progress at the fire date does not separate the two sides. In Feb-Mar it is 85% shed inside and 86% outside, and almost 100% on both sides later. By 15 Feb most deciduous canopy has already shed, so what matters is tree versus open ground, not this week's leaf drop.

**Caveats.**
- Scars in open grass may be harder to see in Sentinel-2 than burnt litter under trees, and that alone would produce part of this pattern.
- 38% of v1 outlines are clipped at the 3 km chip edge. That adds straight edges but no class bias.

**For the spread model.** [inference] Treat open grass/low cover after mid-February as a weak barrier: already cured, grazed or burnt in January. Treat continuous deciduous tree cover as the carrying fuel. This matches the fuel-continuity finding in spread README 4d.

**Rerun on scar outlines v2 (16 Oct, big fires no longer clipped).** The result holds and is slightly stronger.
- Deciduous tree: 65.7% inside vs 60.4% outside, against 60.7 / 60.7% for the shifted null.
- Open grass/low cover: 23.6% vs 29.0%, against 29.1 / 29.2% for the null.
- Each period shows the same pattern: Feb-Mar 66.4 vs 61.0% deciduous; April 63.1 vs 58.5%; May-June 63.9 vs 59.6%.
- Files: `h2_v2.py`, `data/akkshay_checks/h2_v2_out.txt`.
