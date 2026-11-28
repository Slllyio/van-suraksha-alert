> Note: figures below were written at 654 finished chunks. Current tables are in `report/` (669 chunks). Everything here is interim and changes as chunks finish.

# Interim forest loss summary, finished chunks only

**Provisional. Based on 654 chunks, 2,072,200 ha, 22.2% of recorded forest.** The covered area is not a random sample: it is mostly the north (Sheopur, Gwalior, Shivpuri, Guna) plus scattered chunks, so do not scale these rates to MP.

Mapped loss in the covered area: **3,018 ha, 0.15% of covered forest**. Not corrected for errors.

|   year |   clearing |   tree_to_shrub |   shrub_to_crop |   total |
|-------:|-----------:|----------------:|----------------:|--------:|
|   2018 |         10 |              39 |               3 |      52 |
|   2019 |         21 |              50 |              11 |      82 |
|   2020 |        157 |             342 |              93 |     592 |
|   2021 |         96 |             335 |              44 |     476 |
|   2022 |        102 |             536 |              55 |     693 |
|   2023 |        133 |             639 |              73 |     845 |
|   2024 |         21 |             179 |              10 |     210 |
|   2025 |          7 |              57 |               4 |      67 |

Year of change is approximate. Accuracy is known only for Guna (56% precision, 48% recall on the owner's labels).

## Point-based comparison
- Same rule at 510 random points, state: 15,312 ha, 0.164% of forest.
- Same points inside the covered area (122 points, 27 flagged): 0.274%.
- Mapped rate here: 0.15%.
- The point method counts any flagged pixel in a 50 m box, so it should run higher than mapped pixel area.

Tables: interim_by_{state,forest_zone,district,division,range}_{total,year_class}.csv. `partly_covered` marks units under 99.5% covered.