# What shapes Ratapani fire outlines: barrier maps, open data, and a test on our own scars (scouting round 9, topic "barrier", 15 Oct 2026)

Written for the spread-model thread. The spread thread has only Microsoft road detections. It found that fuel breaks, not wind, set the shape of the scars, and that the barriers that matter (fire lines and dry stream beds) are on no map it has (`ratapani/spread/README.md` §4d).

This note does three things:

1. It finds and pulls every open map of linear features for the Ratapani box.
2. It tests, on our 3,640 event scars, whether scar edges sit on those lines more often than chance. It also measures how often each kind of line stops a fire that reaches it.
3. It reads the method papers on fire boundaries and fuel-break effectiveness.

**Not repeated here.** MP fire-line budgets, widths and NAPFF rules are in `fire_management_practice.md` (A1-A7, D1). Narayanaraj & Wimberly 2011, Syphard et al. 2011 (Los Padres), Holsinger 2016 and Price 2014 at abstract or full level, plus "scars as leaky barriers", are in `cold_start_cells.md` (B4, B6, B13, B14). OSM emptiness, Microsoft roads and Open Buildings are in `access_paths.md`. The MPFD ArcGIS lead is in `open_datasets.md`.

**Tags.** **FULL** = full text read. **PARTIAL** = parts read. **ABSTRACT ONLY**. **DATA** = I downloaded and analysed it. My own reasoning is marked [inference].

**Files.** Scripts are in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9code_barrier/` and data in `/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/`. Both are scratch folders, so copy them to `fsi/scouting/code/` to keep them. The clean barrier layer is `fsi/scouting/data/barriers_ratapani.geojson`: 27,116 lines, 14.6 MB, EPSG:4326, with per-class hold rates as attributes (see "The barrier layer").

---

## Headline findings

1. **No open source serves the department's fire lines or compartments, from this container.**
   - The MP Forest Department GIS (`gis.mpforest.gov.in`) and `mpforest.gov.in` reset the connection.
   - The Van Agni geoportal is refused by our egress proxy.
   - The FSI fire portal has no map service (`/geoserver` gives 404).
   - No Obedullaganj, Raisen or Sehore working plan or Ratapani Tiger Conservation Plan text is online.

   So fire lines still have to come from the department or from the fires themselves (finding 5).
2. **NRSC Bhuvan's WMS is open and serves useful vector layers as images.** WFS is disabled, but GetMap works with no login. I pulled four things:
   - The national 1:50k-type drainage (`hydrology:bdrain_qgs`): about 2,000-2,500 km of drainage lines inside the 814 km² sanctuary, close to Survey of India toposheet density.
   - MapmyIndia roads and hydrology (Q4 2022) for MP.
   - The 2023 village layer.
   - The SIS-DP v2 1:10,000 land-use maps for Raisen and Sehore. Their legend has "Grassland & Grazing land", "Forest Plantation" and "Scrub land" classes, but inside the sanctuary they map 90% as plain "Forest" and no grazing land at all (A5).

   Overture Maps (Sep 2026 release) gave OSM plus TomTom roads, power lines and water in one query. Inside the sanctuary, mapped roads of all sources total only about 240 km (0.3 km/km²), and rail and power lines 22 and 26 km.
3. **Scar edges do sit on roads and streams more than chance, but these mapped lines carry only a small share of all scar edge.**
   - **Test design:** each scar was moved up to 500 m in a random direction (with and without rotation, 200 draws) and compared with itself (after Choi & Chae 2026).
   - **Microsoft roads:** 3.0% of scar perimeter lies within 30 m of one, against 2.2% for the moved scars (ratio 1.35, 95% CI 1.28-1.43). Edges that run *along* the road are enriched 2.4× (2.2% vs 0.9%).
   - **Bhuvan drainage:** 14.6% vs 13.0% (ratio 1.12). Along-the-line edges: 1.56×.
   - **DEM streams (≥0.25 km² catchment):** ratio 1.11.
   - **Negative controls:** ridges (1.00), power lines (1.01) and railway (0.92) show no enrichment.
   - **Bottom line:** most scar edge is more than 30 m from any mapped line. Roads, rail, power and OSM water together are near 4.1% of perimeter and Bhuvan drainage near 14.6%; I did not compute their union, so at least about 80% of edge is unexplained [inference].
4. **When a fire reaches a line, how often does the line hold?** This is a direct number for the spread model. The test looks 60 m either side of the line: burned on one side only means the line held; burned on both sides means the fire crossed. The equivalent figure for the same line layout shifted 300-1,000 m is 0.36-0.45. As "stop probability" = (hold − shifted)/(1 − shifted):

   | Line | Stop probability, all fires | Fires that started more than 1 km from the line |
   |---|---|---|
   | OSM roads | 0.69 | 0.78 |
   | Railway | 0.75 | 0.76 |
   | Microsoft roads ≥10 m wide | 0.47 | 0.68 |
   | Microsoft roads 7-10 m wide | 0.30 | 0.47 |
   | DEM stream, catchment ≥25 km² | 0.72 | 0.83 |
   | DEM stream, 5-25 km² | 0.45 | 0.56 |
   | DEM stream, 1-5 km² | 0.29 | 0.31 |
   | DEM stream, 0.25-1 km² | 0.20 | n/a |
   | Power lines | 0.0 | 0.13 |
   | Ridges | 0.0 | 0.0 |

   - Small streams hold much better in Jan-Feb (stop probability 0.68 for 1-5 km² catchments) than in Mar-Jun (0.29-0.33). [inference] Stream beds and riparian strips are still green or moist early in the season and dry out later.
5. **The fires themselves map a hidden barrier network.** I counted pixels that were an in-forest scar edge in 5 or more of the 10 seasons (with an edge share of at least 0.5 when a scar was within 100 m).
   - That gives a network of 1,160 km inside the sanctuary (1.43 km/km²). This matches the fire-line density expected from MP budgets (~1.5 km/km², `fire_management_practice.md` A3) [inference: suggestive, not proof].
   - **Tested honestly**, building the layer without the test season (leave-one-season-out): held-out scar edges sit within 30 m of it 13.0% of the time, against 9.8% by chance (ratio 1.33). Edges along it are enriched 1.95×. That is about four times the excess perimeter that Microsoft roads explain.
   - The layer is 2× enriched near drainage lines and is *not* near mapped roads. Only 30% of its pieces are straight. So it mixes stream beds, fuel-type edges and, probably, fire lines.
6. **Earlier scars of the same season stop later fires.** Scar perimeters lie within 30 m of an earlier same-season scar's edge 13.9% of the time, against 10.8% by chance (ratio 1.29). The research thread's season burn maps give the *opposite* sign (0.60), because they miss 66% of event-scar pixels; do not use them as a barrier layer.

---

## Part A. Own tests on the Ratapani scars (DATA)

### A1. What is mapped inside the sanctuary (814 km² AOI polygon)

| Layer | km inside sanctuary | km per km² |
|---|---|---|
| Microsoft road detections, 7-10 m wide | 68 | 0.084 |
| Microsoft road detections, ≥10 m wide | 63 | 0.077 |
| OSM roads (via Overture) | 56 | 0.069 |
| TomTom roads (via Overture; overlaps the others) | 57 | 0.070 |
| Railway (Bhopal-Itarsi line) | 22 | 0.027 |
| Power lines (OSM) | 26 | 0.032 |
| DEM streams, catchment 0.25-1 / 1-5 / 5-25 / ≥25 km² | 684 / 255 / 104 / 35 | 0.84 / 0.31 / 0.13 / 0.04 |
| Bhuvan drainage (skeletonised from the WMS image; diagonal steps inflate length ~1.3×) | 2,535 | 3.1 |
| Recurrent scar edges (≥5 of 10 seasons) | 1,160 | 1.43 |

- OSM through Overture adds almost nothing new: 13 footways, 5 tracks and 1 path inside the sanctuary. There are no village tracks or cattle paths. This confirms `access_paths.md`.
- Bhuvan MapmyIndia roads in the box are mainly NH-46/45 and district roads.
- Overpass was flaky (500/502/504 errors, 3 of 8 tiles returned). Geofabrik's download server reset the connection.

### A2. Do scar edges coincide with lines? (`edge_test.py`, `summ_edge.py`)

**Method.**
- **Scars:** event scars Jan-Jun 2017-2026 that do not touch the 3 km chip edge (3,640 used). Only parts of 1 ha or more were kept, using their outer rings only.
- **Perimeter points:** sampled every 20 m. Each point's direction was taken from neighbours ±40 m along the ring.
- **Null model** (Choi & Chae 2026): each scar moved by a random vector within a 500 m disc, either with a random rotation (`rt`) or without (`t`). 200 draws, compared with the same line raster at 20 m.
- **Metrics:**
  - **R30:** share of perimeter within 30 m of a line.
  - **S30:** as R30, but leaving out "gap" points where the same scar resumes 60-100 m further out. Those are places where the fire crossed a narrow unburned strip such as a road surface.
  - **A30:** within 30 m *and* running within 30° of the line's direction.
- **Pooled ratio:** observed / null, weighted by perimeter length, with bootstrap CIs over scars.
- **Sign test:** I report the per-scar sign test as in the paper, but it is biased for sparse layers. A scar with no line contact scores 0 against a small positive null mean, so it always counts as "below". Read the pooled ratio and the mean per-scar percentile (PIT, where 0.5 means no effect).

**Results (translation-only null `v2t`/`v3t`; the rotation null gives the same R30 to ±0.02).**

| Layer | Scars with the layer nearby | R30 observed | R30 null | Ratio (95% CI) | S30 ratio | A30 ratio (translation null) | A30 ratio (rotation null) |
|---|---|---|---|---|---|---|---|
| Microsoft roads | 1,505 | 3.01% | 2.22% | **1.35 (1.28-1.43)** | 1.44 | **2.43** | 2.92 |
| OSM roads | 289 | 2.81% | 2.60% | 1.08 (0.90-1.29) | 1.14 | 1.98 | 2.34 |
| TomTom roads | 521 | 2.47% | 2.24% | 1.10 (0.98-1.22) | 1.16 | 2.01 | 2.22 |
| MapmyIndia roads | 426 | 2.64% | 2.54% | 1.04 (0.91-1.17) | 1.05 | 1.52 | 1.66 |
| All mapped roads/rail/power/water | 1,920 | 4.06% | 3.66% | 1.11 (1.06-1.16) | 1.16 | 1.92 | 2.19 |
| Bhuvan drainage | 3,451 | 14.55% | 12.98% | **1.12 (1.10-1.14)** | 1.10 | **1.56** | 1.75 |
| MapmyIndia hydrology | 1,720 | 4.87% | 4.21% | 1.15 (1.10-1.21) | 1.19 | 1.97 | 2.24 |
| DEM stream ≥0.25 km² | 3,628 | 10.05% | 9.01% | 1.11 (1.09-1.14) | 1.12 | 1.47 | 1.71 |
| DEM stream ≥1 km² | 3,310 | 5.18% | 4.70% | 1.10 (1.07-1.14) | 1.13 | 1.50 | 1.77 |
| DEM stream ≥5 km² | 1,747 | 2.95% | 2.85% | 1.04 (0.97-1.10) | 1.07 | 1.43 | 1.70 |
| DEM stream ≥25 km² | 601 | 2.39% | 2.61% | 0.92 (0.81-1.02) | 0.95 | 1.37 | 1.62 |
| OSM water (rivers, reservoirs) | 567 | 2.92% | 3.45% | 0.84 (0.73-0.95) | 0.86 | 1.44 | 1.67 |
| Railway | 105 | 2.98% | 3.25% | 0.92 (0.70-1.13) | 0.98 | 1.58 | 2.07 |
| Power lines | 161 | 4.26% | 4.20% | 1.01 (0.93-1.10) | 1.00 | 1.17 | 0.96 |
| Ridges (inverted DEM, 100 cells) | 3,635 | 24.4% | 24.7% | 0.99 (0.98-1.00) | 0.99 | 1.00 | 1.08 |
| Ridges (500 cells) | 3,262 | 8.13% | 8.10% | 1.00 (0.99-1.02) | 1.01 | 1.04 | 1.15 |
| Burnable/non-burnable land edge (WorldCover) | 3,144 | 5.00% | 5.38% | 0.93 (0.90-0.96) | 0.95 | n/a | n/a |
| Edge of earlier same-season event scars | 2,413 | 13.91% | 10.82% | **1.29 (1.24-1.32)** | 1.34 | n/a | n/a |
| Edge of earlier burns in the season maps | 2,328 | 4.09% | 6.82% | 0.60 (0.57-0.62) | 0.65 | n/a | n/a |
| Recurrent scar edges, ≥3 seasons (leave-one-season-out) | 3,563 | 40.3% | 34.3% | 1.17 (1.17-1.18), PIT 0.67 | 1.18 | 1.53 | n/a |
| Recurrent scar edges, ≥5 seasons (leave-one-season-out) | 3,247 | 13.04% | 9.83% | **1.33 (1.30-1.35)**, PIT 0.61 | 1.34 | **1.95** | n/a |

Reading the table:
- **Rotation inflates A30.** Our scars are 20 m pixel staircases and the DEM streams follow D8 (0/45/90°) paths. Rotating the scar breaks that shared grid alignment and inflates A30 for every layer. Use the translation-only A30. On that measure ridges score 1.00, a clean negative control, while roads (2.4×) and drainage (1.5×) stay enriched: fire edges run *along* roads and stream lines.
- **Large rivers and the cropland edge score below 1.** Scars rarely reach large rivers, reservoirs and the cropland edge at all. Those edges sit at the forest margin, and the forest margin burns less (`cold_start_cells.md` A3: crop-edge cells rarely burn).
- **Season burn maps disagree with event scars.** The season-map "earlier burns" result is a label mismatch. Inside event scars, 66% of pixels are unburned in the season maps, and a 0-60 m ring around each scar holds fewer season-map burns of any date (earlier 2.2%, later 2.0%) than a 200-500 m ring (5.7%, 4.3%).
- **Mapped lines carry only a small share of scar edge.** Microsoft roads explain an *excess* of 0.8 points of perimeter, the drainage network about 1.6 points, and the held-out recurrent edges 3.2 points.

### A3. Hold rate: when a fire reaches a line, does the line stop it? (`hold_rate.py`, `hold_rate_far.py`, `hold_rate_month.py`)

**Method.**
- **Burned map:** for each season, the union of that season's event scars (Jan-Jun).
- **Sampling:** at every line pixel, look 60 m either side along the line's normal. Use only places where both sides are burnable WorldCover land.
- **Classify each contact:** "reached" = at least one side burned that season; "held" = exactly one side burned; "crossed" = both burned.
- **Null:** the same line layout shifted by a random 300-1,000 m (10 draws; SD ≤0.06).
- **Stop probability** = (hold − null hold)/(1 − null hold): the extra share of contacts where the line stopped the fire.
- **Ignition check:** "far" repeats the test using only scars whose alert point is more than 1 km from the line. That rules out fires lit at the roadside that burn away from it, which would look like a hold.

| Line class | Contacts (all) | Hold, all | Null hold | Stop prob., all | Hold, far >1 km | Null, far | Stop prob., far |
|---|---|---|---|---|---|---|---|
| Microsoft roads, all | 23,302 | 0.606 | 0.373 | 0.37 | 0.739 | 0.410 | 0.56 |
| Microsoft roads, 7-10 m | 12,594 | 0.563 | 0.374 | 0.30 | 0.679 | 0.393 | 0.47 |
| Microsoft roads, ≥10 m | 10,403 | 0.665 | 0.368 | 0.47 | 0.808 | 0.396 | 0.68 |
| OSM roads | 4,878 | 0.806 | 0.376 | 0.69 | 0.865 | 0.399 | 0.78 |
| TomTom roads | 4,438 | 0.570 | 0.418 | 0.26 | 0.765 | 0.432 | 0.59 |
| MapmyIndia roads | 12,235 | 0.607 | 0.390 | 0.36 | 0.586 | 0.406 | 0.30 |
| Railway | 2,038 | 0.856 | 0.427 | 0.75 | 0.868 | 0.454 | 0.76 |
| Power lines | 7,890 | 0.355 | 0.360 | 0.00 | 0.505 | 0.429 | 0.13 |
| Bhuvan drainage | 424,415 | 0.456 | 0.386 | 0.11 | (too few far fires) | | |
| MapmyIndia hydrology | 50,535 | 0.662 | 0.417 | 0.42 | 0.710 | 0.439 | 0.48 |
| DEM stream 0.25-1 km² network (all ≥0.25) | 217,114 | 0.505 | 0.379 | 0.20 | n/a | | |
| DEM stream ≥1 km² | 98,348 | 0.565 | 0.384 | 0.29 | 0.596 | 0.413 | 0.31 |
| DEM stream ≥5 km² | 25,861 | 0.670 | 0.399 | 0.45 | 0.742 | 0.420 | 0.56 |
| DEM stream ≥25 km² | 5,324 | 0.838 | 0.413 | 0.72 | 0.901 | 0.429 | 0.83 |
| Ridges, 100 cells | 883,185 | 0.359 | 0.365 | 0.00 | | | |
| Ridges, 500 cells | 206,124 | 0.377 | 0.380 | 0.00 | 0.430 | 0.440 | 0.00 |
| Recurrent scar edges ≥3 seasons (leave-one-season-out) | 930,820 | 0.429 | 0.378 | 0.08 | | | |
| Recurrent scar edges ≥5 seasons (leave-one-season-out) | 233,192 | 0.492 | 0.375 | 0.19 | | | |

**By month.** Stop probability, calculated the same way:

| Line class | Jan-Feb | Mar | Apr-Jun |
|---|---|---|---|
| Microsoft roads | 0.65 | 0.38 | 0.58 |
| OSM roads | 0.81 | 0.63 | 0.85 |
| DEM stream ≥1 km² | 0.68 | 0.33 | 0.29 |
| DEM stream ≥5 km² | 0.84 | 0.51 | 0.45 |
| DEM stream ≥25 km² | 0.86 | 0.85 | 0.67 |
| Ridges | 0.00 | 0.00 | 0.00 |

- Roads hold worse in March. [inference] March is the peak month, with the most fires burning at once under the driest fuels.
- Small streams lose most of their holding power after February.

**What it means.**
- **Wider roads hold better.** Within the Microsoft detections, ≥10 m holds better than 7-10 m (0.47 vs 0.30; 0.68 vs 0.47 for far fires).
- **Larger streams hold better.** The stream gradient (0.20 → 0.29 → 0.45 → 0.72) is monotonic in catchment area. It is the best-supported barrier law we have.
- **Ignition does not explain the hold rates.** Far-ignition rates are *higher*, so fires lit at the road are not what makes roads look like barriers.
- **Two negative controls pass.** Power lines (cleared corridors, but not kept free of grass) and ridges show no effect.

### A4. The fires' own barrier map: recurrent in-forest edges (`recurrent_edges.py`, `recurrent_edges_p.py 5 0.5`, `recur_char.py`)

**Method.**
- For each season, rasterise all Jan-Jun event scars at 20 m.
- Mark the unburned *burnable* pixels touching a scar: the places where a fire stopped in fuel.
- Count, per pixel (after a 1-pixel dilation for registration), the seasons it was such an edge (C). Count the seasons it was within 100 m outside a scar (N).
- Keep C ≥ 5 and C/N ≥ 0.5, skeletonise, and drop pieces under 160 m.
- Build each test season's layer from the other nine.

**Results.**
- **Size:** 1,190 km in the grid box, 1,160 km of it inside the sanctuary.
- **Proximity to other lines:** 25.8% of it lies within 40 m of Bhuvan drainage (12.6% of all burnable land does), 19.6% near DEM streams ≥0.25 km² (10.8%) and 1.7% near Microsoft roads (2.8%). It is 23% near ridges (base 26%).
- **Shape:** of 914 pieces ≥300 m long, the median straightness (bounding-box diagonal / length) is 0.70, and 30% are above 0.8.
- **Appearance:** an 8 × 8 km view of the core (`r9_barrier_data/recur_window.png`) shows edge-frequency halos and short branched skeletons along stream lines and around blocks. Long straight fire lines are not obvious at 20 m.

**Use.**
- It is a better perimeter predictor than any mapped layer (ratio 1.33, A30 1.95, PIT 0.61 on held-out seasons). As a "hold" layer it is weak (stop probability 0.19), because it is a zone of frequent stopping rather than a wall.
- [inference] Feed it to the spread model as a *resistance* (a raised stop chance per crossing) or as a learned-footprint feature (`spread/README.md` §4i), not as a hard barrier.
- It is also the best candidate map to show the department and ask "are these your fire lines?".

### A5. SIS-DP 1:10k land use: no grazing or fuel classes inside the sanctuary (`lulc_sisdp.py`)

I rendered `sisdpv2:MP_Raisen_lulc_v2` and `MP_Sehore_lulc_v2` at ~10 m, decoded the legend colours (97% of rendered pixels matched a class) and resampled to the 20 m grid.

- **Inside the sanctuary:** 90.4% "Forest", 2.3% crop, 0.7% water, and 0.1% each scrub and built-up; 6.4% is not covered.
- **"Grassland & Grazing land" and "Forest Plantation":** effectively absent (0 ha and 0 ha in the sanctuary). In the whole box they are 0.0% and 0.02%.
- **Whole grid box:** 55% forest and 38% crop.

So SIS-DP treats the forest as one block and maps no village grazing land, and it cannot supply fuel-type or grazing edges [inference: grazing happens inside "Forest", unmapped]. The only usable part is its "River/Stream/Drain" class, which duplicates the drainage layers. I did not test it further.

### A6. Caveats

- **Scar boundaries are approximate.** Scars are 20 m and grown in two passes. They merge neighbouring fires from the same image gap, so some "edges" are where two fires met, and the 30 m tolerance is 1.5 pixels.
- **Fire lines appear in the scars themselves.** The department burns fire lines in Dec-Feb (`fire_management_practice.md` A2). Those burns are inside our Jan-Feb scars, and a burned line then stops later fires. That is part of why the earlier-scar edges show up as barriers (A2).
- **Layers are not independent.** Roads follow streams in places, and Overture/OSM, TomTom, Microsoft and MapmyIndia roads overlap; I tested them separately and did not de-duplicate.
- **Bhuvan layers are images, not vectors.** They are WMS renders at ~10 m, skeletonised. Symbol widths and the "bhuvan" watermark were filtered by colour and blob size, which leaves small positional errors of ~10-20 m.

---

## Part B. Sources

### B1. Choi & Chae 2026, "Wildfire Perimeters Align with Topographic Ridge Lines: A Null Model Benchmark for Fire-Spread Modelling in 118 Korean Wildfires (2018-2025)", *Fire* 9(6):247. **FULL** (MDPI PDF, CC BY)
https://doi.org/10.3390/fire9060247

- **Data:** 118 Sentinel-2 burn masks at 20 m (5-16,302 ha). Ridges come from a 30 m SRTM DEM by D8 flow accumulation on the *inverted* DEM, thresholded at 100 cells (50 and 200 in sensitivity tests) and skeletonised.
- **Sampling:** perimeters sampled every 20 m, with direction taken over a 60 m window.
- **Metrics:** R30 (share within 30 m) and Aθ (within 30 m and within 30° of the ridge direction).
- **Null model:** translate within a 500 m disc and rotate 0-360°, with 500 draws. The fire is the unit, tested by a two-sided sign test and bootstrap CIs.
- **Results:**
  - Aθ enrichment: mean 2.30 (median 1.78), >1 in 91 of 118 fires, p = 2.7×10⁻⁹.
  - R30: mean 1.48, 95 of 118 fires.
  - Ridge+valley combined: 1.05 (not significant).
  - Rotation-only null: 1.91. 250 m translation: 2.15.
  - Short ridge pieces carry no signal (0.97). The signal is weaker on the steepest ridges (1.78 vs 2.69).
  - Removing ridges within 60 m of OSM roads (12% of ridge length) leaves 2.37.
- **Concrete action for us.**
  - I copied this design (A2), with two changes: a translation-only null to avoid the grid-alignment artefact, and a pooled ratio because sparse layers break the sign test.
  - Ratapani gives the opposite topographic answer. Ridges carry no signal (1.00) and streams do. [inference] Low-intensity litter fires in a dissected plateau stop at moist stream lines; they do not run up to crests.
  - For the spread model: no ridge term; yes to stream terms.

### B2. Povak, Hessburg & Salter 2018, "Evidence for scale-dependent topographic controls on wildfire spread", *Ecosphere* 9(10):e02443. **FULL** (OA PDF via nwfirescience.org)
https://www.nwfirescience.org/sites/default/files/publications/Ecosphere%20-%202018%20-%20Povak%20-%20Evidence%20for%20scale%E2%80%90dependent%20topographic%20controls%20on%20wildfire%20spread.pdf

- **Data:** about 11,000 California fires in 16 ecoregions. The "boundary" is the 100 m interior buffer of each perimeter and the rest of the fire is the interior.
- **Test:** a paired t-test of feature share at the boundary against the interior. Significance comes from a neutral model that moves each fire at random within its ecoregion (500 iterations), never onto water, rock or snow.
- **Features:** north-south aspect breaks, ridge index, valley index, and roads (2012 TIGER at 90 m).
- **Results:**
  - Roads were "the dominant control across all ecoregions", strongest for fires of 10²-10⁴ ha.
  - Ridgetops showed "little control".
  - Valley bottoms and aspect breaks showed consistent control.
  - Removing road pixels did not change the topographic results.
- **Concrete action for us.**
  - The same pattern holds here: roads and valleys, not ridges.
  - Their boundary-vs-interior design is a cheap second check we can run on each scar. Compare the share of road or stream pixels in the 40 m interior ring with the interior. It needs no line orientation.
  - Their 10²-10⁴ ha peak suggests testing our scar size classes separately (most of ours are 20-150 ha).

### B3. Syphard, Keeley & Brennan 2011, "Comparing the role of fuel breaks across southern California national forests", *Forest Ecology and Management* 261:2038-2048. **FULL** (methods and results read; author copy at consbio.org)
https://consbio.org/wp-content/uploads/2022/05/Comparingtheroleoffuelbreaks.pdf

- **Data:** four national forests, 1980-2007, 641 fires (CALFIRE perimeters, minimum 4.04 ha) overlaid on digitised fuel breaks: 1,834 / 482 / 550 / 1,199 km by forest.
- **What counts as an intersection:** any fire perimeter within 100 m of a break. Each event was classed as *stopped* or *crossed* and confirmed by interviewing firefighters. Partial holds were classed as crossed.
- **Results:**
  - 23% of fires intersected a break.
  - Of those, 22-47% stopped at it and 29-65% crossed, depending on the forest.
  - 25-50% of break area never met a fire, and 10-45% met two or more.
  - Factors: firefighter access, maintenance condition (rated 1-3), fire size and weather (season) mattered most. "Fuel breaks played an important role ... only when they facilitated fire management."
- **Concrete action for us.**
  - Their stopped/crossed classification is what A3 automates (60 m both-side test).
  - Our stop probabilities (0.3-0.8) sit in their 22-47% stopped range once the shifted-line baseline is added back [inference].
  - Two of their variables matter for us:
    - *Maintenance condition*: a fire line burned or cleared this winter versus regrown. A yearly map of which lines were burned is fire-line detector D1 in `fire_management_practice.md`.
    - *Access*: a road is also a suppression anchor. In Ratapani that means the beat guard reaching the fire on foot [inference].

### B4. Mo 2024, "Modeling Wildfire Perimeter Formation for Strategic Containment Line Planning in the Boreal Forest Region of Alberta, Canada", MSc thesis, University of Alberta. **PARTIAL** (abstract, methods sections 1.2, 2.3-2.6 and the road and water results; 155 pp)
https://doi.org/10.7939/r3-hhtz-xk31

- **Data:** more than 100 perimeters, 2008-2018.
- **Sampling:** matched case-control. Every 200 m along the perimeter, a 100 m transect at 90° gives an outside "case" and an inside "control" point. Badly matched pairs are cleaned automatically.
- **Models:** conditional logistic regression plus a matched random forest; 29 variables, of which 20 key ones are selected.
- **Results:**
  - AUC 0.70 on four held-out fires.
  - Distance to roads, water, aspen and grass favour stopping.
  - Recent burns stop fire, but the effect fades with time since fire, and burns 70 or more years old act like ordinary fuel.
  - Distance to roads "almost doubles the likelihood" (random forest importance). In conditional logistic regression with all 20 variables, road distance was not significant.
- **Concrete action for us.**
  - The paired transect design is a clean alternative to A2 for a per-point "stop" model. Features would be road and stream distance and catchment, earlier-scar edge, recurrent-edge, WorldCover and SIS-DP class, slope, and month.
  - [inference] With 3,640 scars × ~275 perimeter points, a stop model could be fitted per point and used directly as the spread model's stop probability.

### B5. Archibald, Staver & Levin 2012, "Evolution of human-driven fire regimes in Africa", *PNAS* 109:847-852. **FULL** (PMC3271907, read through the fetch tool)

- **Model:** a percolation fire model on a 100 × 100 grid of 500 m cells.
- **Results:**
  - Fires "suddenly cannot spread" when the flammable fraction ρ falls below about 0.6, or the cell-to-cell spread probability λ below about 0.6.
  - Below about 1,400 kW/m fireline intensity, savanna fires do not burn.
  - Raising ignitions 10× (μ 1 → 10) adds only 6% burned area in connected landscapes. Ignitions matter only in fragmented ones.
  - Barriers listed: tree clumps, agriculture, bare ground, roads, topography and rivers.
- **Concrete action for us.**
  - [inference] Ratapani is in the "ignition-limited, fragmented" regime: low-intensity litter fires, a dense drainage and fire-line network, and 25 ha scars. Here *where* people light matters as much as connectivity.
  - One cheap check for the spread thread: compute, per beat, the flammable fraction left after removing barrier strips (lines buffered by their width, plus earlier scars), and see if mean scar size jumps below about 0.6.

### B6. Narayanaraj & Wimberly 2011, *IJWF* 20:792-803, "Influences of forest roads on the spatial pattern of wildfire boundaries". **ABSTRACT ONLY** (no open copy; the SDSU dissertation is campus-only)

- **Design:** matched case-control points at 200 m intervals along the perimeters of 6 fires, Wenatchee NF (Washington).
- **Result:** in 4 of 6 fires the boundaries were closer to roads than the controls, and the road effect was stronger than any other variable where it was significant.
- **Concrete action:** nothing new beyond B4. Cited for the design.

### B7. Price, Borah & Maier 2014, *Austral Ecology* 39:135-144. **ABSTRACT ONLY** (Unpaywall and Semantic Scholar: closed)

Nine late-dry-season fires in Arnhem Land on 250 m MODIS:
- 92% of points with a recent burn within 500 m were fire boundaries.
- Roads, rivers and topography had only small effects.
- About half of all stops were unexplained.

**Concrete action:** our result agrees. Earlier same-season scars (ratio 1.29) beat roads, and most scar edge is unexplained by mapped lines.

### B8. O'Connor, Calkin & Thompson 2017, "An empirical machine learning method for predicting potential fire control locations", *IJWF* 26:587-597. **ABSTRACT ONLY** (the ConnectSci PDF link returned a web page)

- **Model:** boosted logistic regression on topography, fuels, roads and suppression effort at the perimeters of 238 large fires (34,000 km², Idaho/Nevada).
- **Results:** 69% accuracy on independent fires. The output is the US "Potential Control Locations" raster, published as a USFS ImageServer.
- **Concrete action:** the same idea as B4, at agency scale. A Ratapani "potential stop location" raster from our scars (A4 plus a model) is the analogue.

### B9. Oliveira, Rocha & Fernandes 2016, "Assessing the effect of a fuel break network to reduce burnt area and wildfire risk transmission", *IJWF* 25:619-632. **ABSTRACT ONLY**

- **Design:** simulation of 150,000 Algarve fires with 120 m wide fuel breaks covering 3% of the area.
- **Results:** burned area fell by up to 17%, and burn probability by 4-31%. Treatment leverage was 1:26.
- **Concrete action:** none directly. It is simulation, with a much wider break class than ours.

### B10. Other sources checked

- **Bandipur VHR deep learning:** Pradhan et al. 2025, *PLoS ONE* 20:e0327125 (PMC12266457). **PARTIAL.** PlanetScope 3 m, one date (25 Feb 2019). UNET-GRU, F1 0.967, IoU 0.94. Fire lines, roads and streams are *not* discussed. No use for barriers.
- **Pacific Fire Exchange fuel-break quick reference:** search-level only. A *fuel break* reduces fuel and slows fire; a *firebreak* is cleared to mineral soil. Fires tend to jump breaks mid-slope. MP's fire lines are cleared and burned (`fire_management_practice.md` A2), so they behave as firebreaks once burned and as fuel breaks when not [inference].
- **Indian fire-line effectiveness:** searched in English and Hindi (fire lines, Raisen, Obedullaganj, Ratapani, Telangana, Maharashtra). There is no study measuring Indian fire-line effectiveness, and no MP working plan with line lengths online. Ratapani-specific pages (KBA factsheet, Mongabay Jan 2025) mention fire as a threat only.

---

## Part C. Portals and services checked (15 Oct 2026, from the container)

| Service | Result | What it would give |
|---|---|---|
| MPFD ArcGIS `gis.mpforest.gov.in/server/rest/services` | Connection reset (as in `open_datasets.md`) | Compartments, beats, maybe fire lines. Try from an Indian IP. |
| `mpforest.gov.in`, `mpforest.mp.gov.in` | Reset / proxy 502 | Working plans |
| FSI Van Agni geoportal `vanagniportal.fsiforestfire.gov.in` | Refused by our egress proxy (host not allowlisted) | FSI burnt-area polygons, possibly beat/compartment layers. Needs the allowlist or an Indian browser. |
| FSI fire portal `fsiforestfire.gov.in` | Loads; `/geoserver/wms` and `/ows` 404; the home page links only Van Agni | No map service |
| Bhuvan `bhuvan-vec1.nrsc.gov.in/bhuvan/wms` | **Works** (7,238 layers; WFS disabled; intermittent resets, retry needed) | Drainage, MapmyIndia roads and hydrology, villages 2023, SIS-DP 1:10k LULC |
| Bhuvan `bhuvan-vec2` | Timeout | |
| Survey of India `onlinemaps.surveyofindia.gov.in` | Page loads (200); downloads need a login | 1:50k toposheet vectors (needs login, so not tried) |
| Overpass API | 500/502/504 errors and resets; 3 of 8 tiles succeeded | Same OSM content as Overture |
| Geofabrik India extracts | Connection reset | |
| Overture Maps S3 (2026-09-23.0) via DuckDB | **Works**, no key | Roads (OSM + TomTom), water, land use, infrastructure (power lines) |
| Copernicus GLO-30 DEM on AWS (`copernicus-dem-30m`) | **Works**, no key | 30 m DEM → streams and ridges |

The Bhuvan layer names that matter for us (all `EPSG:4326` GetMap, PNG):
- `hydrology:bdrain_qgs`: national basin drainage, detailed.
- `hydrology:BDRN_12_Narmada` and `hydrology:BDRN_2A_Ganga`: per-basin drainage. Ratapani straddles the Narmada-Betwa divide.
- `mmi:MP_ROAD_NETWORK_Q4_2022`, `mmi:MP_HYDROLOGY_R_Q4_2022`, `mmi:MP_RAIL_NETWORK_Q4_2022`: MapmyIndia (proprietary; view-only terms likely).
- `basemap:mp_village2023`.
- `sisdpv2:MP_Raisen_lulc_v2` and `sisdpv2:MP_Sehore_lulc_v2`: SIS-DP v2 1:10k LULC.
- `sdv:mp_Raisen_slope`.

---

## Datasets

| Name | Link | Resolution | Years | Licence | How to access | Obtained? |
|---|---|---|---|---|---|---|
| Microsoft Road Detections | github.com/microsoft/RoadDetections | vector, width attribute | 2025-04 release | ODbL | Already in `fsi/scouting/data/ms_roads_rata.tsv` | Yes (existing) |
| Overture transportation (OSM + TomTom) | docs.overturemaps.org | vector | release 2026-09-23.0 | ODbL / CDLA | DuckDB `read_parquet('s3://overturemaps-us-west-2/release/2026-09-23.0/theme=transportation/type=segment/*')` with a bbox filter (`overture.py`) | **Yes**: 78,672 segments in the bbox |
| Overture base: water, land_use, land, infrastructure | same | vector | 2026-09-23.0 | ODbL | same script | **Yes**: 375 / 949 / 450 / 5,147 features |
| OSM via Overpass | overpass-api.de | vector | live | ODbL | `osm_pull.sh` (4 tiles, retries) | Partial (3 of 8 queries); redundant with Overture |
| Copernicus GLO-30 DEM | copernicus-dem-30m.s3.amazonaws.com | 30 m | 2011-2015 acquisition | Copernicus DEM licence (free, attribution) | 4 tiles N22-23 E077-078 | **Yes** |
| DEM streams and ridges (derived) | `dem_streams.py`, `dem_ridges.py` (pysheds D8) | 30 m | – | derived | streams at 0.25/1/5/25 km²; ridges at 100/500 cells | **Yes** |
| Bhuvan national drainage `hydrology:bdrain_qgs` | bhuvan-vec1.nrsc.gov.in/bhuvan/wms | rendered at 0.0001° (~10 m); source ~1:50k | not stated | NRSC terms unclear; treat as view-only, internal research | `bhuvan_tiles.py` → GeoTIFF mosaic, skeleton → `bhuvan_drainage_vector.geojson` | **Yes** (scratch only, not in the shared layer) |
| MapmyIndia roads, hydrology (on Bhuvan) | same WMS | ~10 m render | Q4 2022 | proprietary | same | **Yes** (scratch only) |
| Bhuvan villages 2023 | same WMS, `basemap:mp_village2023` | render | 2023 | NRSC | same | Yes (image only, not analysed) |
| SIS-DP v2 LULC 1:10k (Raisen, Sehore) | same WMS | ~10 m render of 1:10k | ~2018-2021 [inference: SIS-DP phase 2] | NRSC | same | Yes; no grazing or plantation class inside the sanctuary (A5) |
| Recurrent scar edges (derived) | `recurrent_edges_p.py 5 0.5` | 20 m skeleton | 2017-2026 | project | `r9_barrier_data/recurrent_edges_5_0.5.npz` (with leave-one-season-out layers) | **Yes** |
| Event scars | `fire-alert-scars/event_scars.geojson` | 20 m polygons | 2017-2026 | project | existing | Yes |
| MPFD compartments / fire lines | gis.mpforest.gov.in | vector | 2023 | unknown | blocked from here | No |
| FSI Van Agni layers | vanagniportal.fsiforestfire.gov.in | – | – | – | proxy refuses | No |
| Survey of India OVSF 1:50k | onlinemaps.surveyofindia.gov.in | vector | – | SoI open series | login | No |
| US Potential Control Locations | apps.fs.usda.gov/fsgisx03/rest/services/wo_spf_fam/Potential_Control_Location/ImageServer | 30 m | – | US public | – | Not needed (method reference) |

---

## The barrier layer (`fsi/scouting/data/barriers_ratapani.geojson`)

- **Extent and size:** clipped to the spread thread's 20 m grid box (UTM 43N 737,300-816,740 E, 2,523,020-2,560,500 N); 27,116 features.
- **Attributes:** `cls`, `source`, `licence`, `hold_rate`, `hold_null`, `p_stop` (all fires), `p_stop_far` (fires lit more than 1 km away), `width_m` (Microsoft roads), `osm_class`, `upstream_km2` (DEM streams), `len_m`.

| cls | Features | km | p_stop | p_stop_far |
|---|---|---|---|---|
| road_ms_7_10m | 2,586 | 575 | 0.30 | 0.47 |
| road_ms_ge10m | 2,638 | 1,082 | 0.47 | 0.68 |
| road_osm | 5,224 | 1,275 | 0.69 | 0.78 |
| road_tomtom | 2,536 | 814 | 0.26 | 0.59 |
| rail | 49 | 182 | 0.75 | 0.76 |
| power_line | 23 | 191 | 0.00 | 0.13 |
| stream_dem_0.25_1km2 | 3,964 | 2,704 | 0.20 | – |
| stream_dem_1_5km2 | 1,053 | 885 | 0.29 | 0.31 |
| stream_dem_5_25km2 | 696 | 515 | 0.45 | 0.56 |
| stream_dem_ge25km2 | 536 | 373 | 0.72 | 0.83 |
| recurrent_scar_edge | 7,811 | 1,186 | 0.19 | – |

- **Road overlaps:** the road classes overlap (the same road can appear in Microsoft, OSM and TomTom). For a spread model, take the maximum `p_stop` per pixel.
- **What is left out:** Bhuvan and MapmyIndia layers stay out because of licence doubt. The Bhuvan drainage vector is in scratch (`r9_barrier_data/bhuvan_drainage_vector.geojson`, 7,497 km of skeleton).
- **Season:** `p_stop` is a Jan-Jun average. Use the month table in A3 for small streams.

---

## Ranked action list (gain and effort are my estimates [inference] unless measured)

1. **Spread thread: add DEM streams as leaky barriers whose stop probability depends on catchment size and month** (A3). Use 0.20 / 0.29 / 0.45 / 0.72 by catchment class; the 1-5 km² class goes from 0.68 in Jan-Feb to 0.3 after.
   - Gain: almost every scar has a stream nearby (3,628 of 3,640 have a DEM stream inside their test window, against 1,505 for Microsoft roads). Stream contacts outnumber road contacts about 10 to 1 (217,114 against 23,302 line-pixel contacts in A3). This is the largest mapped-feature effect available.
   - Effort: low. The layer is ready, and the spread thread already supports road barriers.
   - Test: the end-footprint Sorensen and outline score on the 1,398 fires.
2. **Spread thread: switch roads from hard barriers to leaky ones with width-dependent stop probability.**
   - Use Microsoft ≥10 m 0.47-0.68, 7-10 m 0.30-0.47, OSM 0.69-0.78, rail 0.75. Drop power lines, which have no effect.
   - The current strict rule (no crossing ever) over-stops: roads were crossed in 39% of contacts.
   - Effort: low.
3. **Spread thread: use earlier same-season scars as barriers** (ratio 1.29; cold_start found the same). The event scar polygons with dates are already there.
   - Effort: low. Gain: medium in March-April, when scars pile up.
4. **Use the recurrent-edge layer (leave-one-season-out) as a learned resistance or footprint feature, not a hard barrier.**
   - It is the strongest perimeter predictor found: ratio 1.33, A30 1.95, PIT 0.61. Hold is weak: 0.19.
   - Add `dist_recurrent_edge` and `recurrent_edge_density` to the learned-footprint model (§4i) and check the held-out Sorensen.
   - Effort: low.
5. **Fit a per-point "stop" model on our scars** (B4 / B8 design: outside-inside pairs 50 m from every perimeter point).
   - Features: stream catchment and month, road width, earlier-scar edge, recurrent edge, WorldCover and SIS-DP class, slope, and the VIIRS pass hour.
   - Output: a stop-probability raster for the spread model.
   - Effort: medium. Gain: replaces hand-set barrier rules with measured ones.
6. **Send the recurrent-edge map to the Ratapani DFO / Obedullaganj division with the specific ask "mark which of these are fire lines, and which were burned in which winter"**, citing NAPFF §6.3 (`fire_management_practice.md` A1) and the NTCA audit item on fire-line km.
   - This is a desk exercise for them, not field work.
   - Effort: an email. Gain: the true fire-line layer, which no open source has.
7. **Try the MPFD GIS server and Van Agni from an Indian connection, or ask for Van Agni to be allowlisted** (compartments, beats, possibly fire lines).
   - Effort: low. Gain: high if fire lines are there.
8. **Fire-line detector from imagery** (`fire_management_practice.md` D1). Use the recurrent-edge layer to seed and validate it. Look for straight 6-12 m burned strips in Dec-Feb Sentinel-2 10 m dNBR near recurrent edges.
   - Effort: medium-high. Gain: a yearly "line burned this winter" flag, which Syphard (B3) found to be a top factor.
9. **Run a Povak-style boundary-ring vs interior check by scar size class** (B2), as a robustness check of A2. Effort: low.
10. **Percolation check** (B5): per beat, the flammable fraction after barrier strips and earlier scars, against mean scar size. Effort: low. Gain: explanatory.

## Reading status

| Source | Status |
|---|---|
| Choi & Chae 2026 *Fire* | FULL |
| Povak et al. 2018 *Ecosphere* | FULL (methods, results, discussion) |
| Syphard et al. 2011 *FEM* | FULL (methods, results; SEM details skimmed) |
| Archibald et al. 2012 *PNAS* | FULL (via fetch tool) |
| Mo 2024 MSc thesis | PARTIAL |
| Pradhan et al. 2025 *PLoS ONE* (Bandipur) | PARTIAL |
| Narayanaraj & Wimberly 2011, Price et al. 2014, O'Connor et al. 2017, Oliveira et al. 2016 | ABSTRACT ONLY (closed; Unpaywall null) |

---

## Addendum (15 Oct 2026, 12:00Z): the department's own fire-line classes

Akkshay listed the fire lines on the ground: (1) forest block (compartment) lines, (2) district lines, (3) range and beat boundary lines, (4) roads and railways.

I built (2) and (3) from the MP beat map (`beats/mp_beats.geojson`, 160 beats around the sanctuary). Division boundaries stand in for district lines here (Sehore, Obedullaganj, Bhopal, Sehore Project). Lines are only the shared boundaries between two units: division 232 km, range-only 128 km, beat-only 706 km. Files: `data/admin_lines/*.geojson`, code `code/admin_lines/admin_lines.py`. I used the same hold test as finding 4 (60 m either side, null = same layout shifted 300-1,000 m).

| Line (as drawn on the beat map) | Times a fire reached it | Stop probability, all months | Jan-Feb | Mar-Jun |
|---|---|---|---|---|
| Division / district boundary | 16,495 px | 0.16 | 0.15 | 0.19 |
| Range boundary | 16,047 | 0.14 | 0.15 | 0.13 |
| Beat boundary | 85,965 | 0.08 | 0.17 | 0.07 |
| Microsoft roads (all widths), same run | 23,302 | 0.37 | | |
| Railway, same run | 2,038 | 0.75 | | |

Scar edges are only slightly enriched near these lines (1.1-1.2x within 30 m for division lines, 1.0-1.1x for range and beat lines). This holds for every scar edge and for the recurrent-edge network alike, and it shows no peak at a fixed offset, so a simple shift of the map does not explain it.

**What it means.**
- Roads and railways are real, strong barriers: stop probability 0.3-0.78 by width, and 0.75 for rail.
- Beat, range and division lines as drawn on the beat map behave almost like random lines.
- [inference] There are two possible reasons. The cleared strip on the ground may not follow the digitised boundary closely: beat maps were traced from old toposheets, and many boundaries follow nala and ridge lines. Or interior lines may not be cleared, or not cleared every year, so fires cross them.
- Forest block (compartment) lines are the main working-plan fire lines. They could not be tested because no compartment map is available here.
- The fires' own recurrent-edge network (1,160 km, finding 5) is still the best stand-in for hidden fire lines.

**For the spread model.**
- Keep roads and rail at the measured stop values.
- Give beat, range and division lines at most a weak stop of about 0.1 (about 0.2 for division lines).
- Add compartment lines only if a compartment map can be obtained (MP FD GIS / Van Agni, from Akkshay's PC), then re-run this test on them.
