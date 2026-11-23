# Hyperspectral (Pixxel / EMIT) for fire-prone areas (22 Nov 2026)

Akkshay asked (22 Nov): how can Pixxel's hyperspectral imagery help us understand fire-prone areas, and how does it compare with Prithvi and other geospatial models?

## Pixxel's offer today (docs.pixxel.space, UP42, NASA CSDA pages, read 22 Nov 2026)
| | Firefly (in orbit, 6 sats, 2025) | Honeybee (planned 2027-28) |
|---|---|---|
| Range | 472-890 nm (visible + near-infrared only) | 470-2500 nm (adds shortwave infrared) |
| Bands | ~135 (45 per order) | ~260 (72 per order) |
| Pixel | 5.4 m | 5 m |
| Swath | 38-40 km | 30 km VNIR, 10 km SWIR |
| Revisit | <7 days at MP's latitude (UP42 says 2 days) | 1-4 days |
| Price | tasking $8/km², archive $6/km² (20% off if >1 yr old) | not priced |
No free sample/research tier found (NASA CSDA access is US-government only).

Firefly has NO shortwave infrared, so it cannot see the 2.1 um cellulose/lignin (dry litter) or 1.45/1.9 um water features. Those need Honeybee, EMIT, EnMAP or PRISMA.

Rough cost of one Firefly cover: Ratapani block ~1,300 km² ~ $8-10k; all MP forest (~77,500 km²) ~ $470-620k.

## Free stand-in: NASA EMIT (60 m, 381-2493 nm, 285 bands)
CMR search: 1,599 EMIT L2A scenes over MP Aug 2022-Oct 2026; clear Jan-Feb scenes in 2023 and 2025. Ratapani core itself only has clear passes on 30 Apr 2024 and 29 Jan 2025 (edge). Downloaded through the existing *.nasa.gov login (30 s per 1.9 GB scene).

## Test (scripts/: agg.py, test.py, robust.py, species.py)
15 clear pre-season scenes (1-14 Feb 2023, 29 Jan-14 Feb 2025), averaged to the shared 500 m grid; forest beat squares only (>50% tree+shrub, >50% beat): 89,158 squares. Target: >=30% of the square's forest burnt that season (MP scars, 15 Feb-15 Jun). Controls: scar burn history from earlier seasons + static GIS (terrain, FSI forest types, roads, villages). LightGBM, 10 km blocks held out.
Feature sets: S2-like = EMIT averaged into Sentinel-2's 10 bands + NDVI/NBR/NDMI/NDTI (same date, same pixels); Pixxel-like = 472-890 nm spectrum (15 PCs) + red-edge/PRI/CRI/ARI; full EMIT = + full-spectrum PCs + SWIR litter/water indices (CAI, LCA, SINDRI, NDLI, 970/1200 nm water).

| features | AUC | top 10% catches |
|---|---|---|
| history + GIS | 0.886 | 53.7% |
| + S2-like bands | 0.905 | 55.3% |
| + S2 + Pixxel-like VNIR | 0.915 | 57.3% |
| + S2 + full EMIT (with SWIR) | 0.918 | 58.3% |
Gain over S2-like (block bootstrap 95% CI): Pixxel-like +0.009 (0.006-0.014), full +0.013 (0.009-0.017).

Robustness:
- Whole dates held out: S2-like 0.835, Pixxel-like 0.855, full 0.855 (+0.02).
- Train one season, test the other: 2023->2025 S2 0.805 / VNIR 0.815 / full 0.797; 2025->2023 0.943 / 0.938 / 0.944. Across seasons the gain is 0 to +1 pt and SWIR adds nothing.
- SWIR dry-litter indices on their own: CAI vs burning rho 0.00, LCA -0.05 (NDTI, which S2 has, 0.25). In late Jan at 60 m the litter signal is not visible; top spectral features are PRI (leaf stress/yellowing) and SINDRI.
- Mid-March test not possible: only one clear March date (24 Mar 2025) over ~10k beat squares, a third of the season already burnt.
- Teak vs sal (FSI type map, squares >60% one type): S2-like 0.924, Pixxel-like 0.949, full 0.968 (terrain alone 0.699). Partly regional (sal belt is clustered).

## Verdict
- Daily 2-day model: no. A season "burns wholesale" score was already shown to add nothing to the daily model (Prithvi 2-day test, Oct 18), and a perfect burn map lifts brand-new fires <=1.6 pts.
- Season map of which ground burns: small real gain, the same size as Prithvi's (+0.016 over raw HLS). It does not hold up well across seasons.
- "See dry litter": not supported. Firefly cannot see the litter bands at all; EMIT can and the litter indices show no link.
- Best real uses of Pixxel: 5 m species/stand maps (teak vs sal vs bamboo/grass) and edges of the 3,867 repeat-burn patches for the control-burning programme; burn-severity mapping after fires. Sentinel-2 at 10 m covers most of this free.
- Recommendation: do not buy MP-wide. If wanted, one small Firefly archive order (~100 km², ~$600-800) over a Ratapani repeat-burn block to test 5 m patch edges/species; wait for Honeybee SWIR (2027+) for any litter-moisture work, and test on free EMIT/EnMAP first.

## Models compared
| model | trained on | what it is good for here | our result |
|---|---|---|---|
| Prithvi-EO-2.0 (NASA/IBM) | HLS 6 bands, 30 m, time series | season burn-share ranking | +0.016 AUC over raw HLS; 2-day nothing; fine-tune nothing |
| AlphaEarth (Google) | yearly 10 m embeddings from many sensors | land-cover summaries | dead end in 2-day model |
| Clay v1.5 | S2, Landsat, NAIP, S1; wavelength-aware input | could take resampled hyperspectral bands | not tested; not trained on hyperspectral |
| SatMAE / SpectralGPT | Sentinel-2 13 bands | multispectral only | not tested |
| SpectralEarth (DLR) | 11,636 EnMAP scenes, public weights | only real hyperspectral foundation model | not tested; would be the one to try on EMIT/EnMAP/Pixxel |
A foundation model only compresses what the sensor saw; it cannot add SWIR detail Sentinel-2/HLS never measured. Here plain PCA of the EMIT spectrum already gives the hyperspectral gain.

## Part 2 (22 Nov, his reframe): why chronic ground burns, and look-alikes that don't
Akkshay 13:12Z: "not in alert but in understanding why this area is so much prone and what other areas like that but not burning". Scripts lookalike.py (all MP, GIS), lookalike2.py / lookalike3.py (EMIT spectrum). Map figures/chronic_vs_lookalike_map.png; squares results/chronic_lookalike_squares.csv.gz; by division results/lookalike_by_division.csv.

Setup: 294,813 forest beat squares (>=50% tree+shrub, >=50% beat). Chronic = burnt (>=10% forest) in 5+ of 9 seasons 2017-25: 25,493. Rare = 0-1 seasons: 199,200. A "looks fire-prone" score from vegetation + terrain only (FSI forest types, WorldCover shares, elevation, slope, roughness, aspect), 10 km blocks held out: AUC 0.835 chronic vs rare. Look-alikes = rare squares scoring at least the chronic median: 20,000+.

What separates chronic squares from their look-alikes (same vegetation + terrain):
| factor | chronic | look-alike | same direction inside divisions |
|---|---|---|---|
| neighbours' burning (5 km, years burnt) | 3.6 | 0.5 | 83% of divisions, rho +0.59 |
| depth inside forest (km) | 1.6 | 1.1 | 69%, +0.21 |
| villages within 5 km | 1 | 2 | 67%, -0.23 |
| distance to road (km) | 1.5 | 1.0 | 72%, +0.19 |
| forest share within 5 km | 0.86 | 0.77 | 70%, +0.30 |
| farm share within 5 km | 0.10 | 0.17 | 69%, -0.28 |
| inside a tiger reserve | 4% | 28% | |
Chronic share by depth inside forest: 0-0.5 km 51%, 2-3 km 65%, >3 km 69%. By villages within 5 km: none 66%, 6+ 45%.
Model AUC chronic vs look-alike: people/access/reserve 0.78; + neighbours 0.97; division alone 0.87.

Spectrum (EMIT late Jan-mid Feb, squares not burnt the season before, 2,399 chronic / 4,695 look-alikes):
| what the model sees | AUC chronic vs look-alike |
|---|---|
| S2-like bands only | 0.709 |
| Pixxel-like 472-890 nm only | 0.835 |
| full EMIT only | 0.872 |
| division + look score | 0.891 |
| + people/access | 0.929 |
| + S2-like | 0.934 |
| + Pixxel-like | 0.955 |
| + full EMIT | 0.962 |
| + people + full EMIT | 0.969 |
Plain differences within division and look score: chronic squares have a lower red-edge position (-0.47 SD: canopy chlorophyll fading earlier), more carotenoid (+0.18 SD: yellowing leaves), slightly higher NDVI/NBR/NDTI (+0.2 SD) and leaf-water 1200 nm (+0.22). Dry-litter SWIR (CAI, LCA) no difference (+-0.05 SD).

Reading: fire-prone ground is a landscape, not a square. It is deep, unbroken forest far from villages, roads and farms, outside tiger reserves, with burning neighbours; and its canopy starts yellowing earlier in late January. Near villages and farm edges the same forest burns less (people put fires out / grazing and paths break fuel / fewer interior collectors), consistent with access_paths.md (5x from hamlet edge to 3 km inside) and new_questions.md section 3 (cooled patches are reachable). Look-alikes cluster in tiger reserves and in Obedullaganj, Raisen, Sanjay-Dubri, Satpura, Kanha, Pench, Harda. Caveat: the canopy signal can be cause or effect (repeated burning changes stands toward open, early-shedding, grassy teak); this data cannot split them. Hyperspectral VNIR (what Pixxel sells) sees this stand difference better than Sentinel-2 bands (0.955 vs 0.934).
