# v17 Per-Fire Validation — 2025 Fire Season Hold-Out

**Generated:** 2026-04-19 00:44

**Window:** 2025-02-02 to 2025-05-29 (18 prediction Thursdays)

Every FIRMS DBSCAN ignition that occurred within 7 days of each v17 prediction date is matched to the model's output for its cell. We report (a) how confident v17 was (band + within-day rank), (b) how far away the nearest CRITICAL / ALERT / top-5% cell was in km, and (c) the temporal lead-time from prediction issuance to actual fire detection.

## Headline numbers

| Metric | Count | Pct |
|---|---:|---:|
| Total actual fires (DBSCAN ignitions) | 3,614 | 100.0% |
| Matched to FIRMS acq_datetime | 3,614 | 100.0% |
| Flagged CRITICAL | 130 | 3.6% |
| Flagged ALERT or above | 404 | 11.2% |
| Flagged WATCH or above | 820 | 22.7% |
| In top 5% rank | 820 | 22.7% |
| Below median rank (model blind) | 546 | 15.1% |

## Spatial offset distribution

Distance from each actual fire cell to nearest alerted cell on the prediction date.

| Percentile | km to CRITICAL | km to ALERT+ | km to top-5% |
|---|---:|---:|---:|
| p10 | 4.0 | 0.0 | 0.0 |
| p25 | 10.1 | 2.9 | 2.0 |
| p50 | 21.0 | 9.1 | 4.0 |
| p75 | 41.0 | 21.7 | 10.3 |
| p90 | 71.0 | 37.5 | 20.0 |
| p95 | 86.7 | 49.6 | 26.2 |

## Temporal offset distribution

Lead time from v17's prediction Thursday to the actual FIRMS detection. Negative = fire detected BEFORE prediction (shouldn't happen if pipeline correct); 0-7 days = within-window; the 7-day forecast horizon.

- Matches with timestamp: **3,614**
- Median lead time: **0.0 days**
- Mean lead time: **0.0 days**
- p10 / p25 / p50 / p75 / p90: 0.0 / 0.0 / 0.0 / 0.0 / 0.0 days

## Per-day summary

| Date | #fires | #top5% | Recall@5% | #CRIT | Med km→CRIT | Med km→top5% |
|---|---:|---:|---:|---:|---:|---:|
| 2025-02-02 | 41 | 14 | 34.1% | 5 | 10.1 | 2.0 |
| 2025-02-06 | 90 | 35 | 38.9% | 5 | 12.8 | 2.0 |
| 2025-02-13 | 84 | 31 | 36.9% | 5 | 19.2 | 2.4 |
| 2025-02-20 | 45 | 26 | 57.8% | 10 | 6.0 | 0.0 |
| 2025-02-27 | 44 | 21 | 47.7% | 5 | 18.2 | 2.0 |
| 2025-03-06 | 203 | 66 | 32.5% | 10 | 25.2 | 2.8 |
| 2025-03-13 | 359 | 107 | 29.8% | 18 | 20.2 | 2.0 |
| 2025-03-20 | 218 | 60 | 27.5% | 5 | 18.1 | 2.8 |
| 2025-03-27 | 870 | 178 | 20.5% | 30 | 15.7 | 4.0 |
| 2025-04-03 | 55 | 4 | 7.3% | 2 | 35.3 | 8.0 |
| 2025-04-10 | 303 | 42 | 13.9% | 3 | 31.8 | 6.3 |
| 2025-04-17 | 378 | 65 | 17.2% | 8 | 33.2 | 6.0 |
| 2025-04-24 | 714 | 119 | 16.7% | 14 | 25.0 | 5.7 |
| 2025-05-01 | 137 | 30 | 21.9% | 4 | 26.2 | 4.0 |
| 2025-05-08 | 16 | 5 | 31.2% | 1 | 22.4 | 2.0 |
| 2025-05-15 | 26 | 7 | 26.9% | 3 | 18.5 | 3.7 |
| 2025-05-22 | 13 | 4 | 30.8% | 1 | 60.1 | 6.0 |
| 2025-05-29 | 18 | 6 | 33.3% | 1 | 25.5 | 5.2 |

## Top-20 divisions by fire count

| Division | #fires | R@5% | R@ALERT+ | Med km→top5% | Mean rank | % low-Hawkes |
|---|---:|---:|---:|---:|---:|---:|
| Raisen | 145 | 43.4% | 25.5% | 2.0 | 0.874 | 4.1% |
| Damoh | 116 | 6.9% | 1.7% | 5.7 | 0.734 | 13.8% |
| Dewas | 115 | 33.0% | 11.3% | 2.0 | 0.838 | 7.8% |
| Khandwa | 114 | 19.3% | 11.4% | 5.9 | 0.781 | 12.3% |
| Guna | 113 | 23.9% | 8.8% | 2.8 | 0.736 | 13.3% |
| Singrauli | 113 | 58.4% | 47.8% | 0.0 | 0.864 | 5.3% |
| North_Seoni | 104 | 17.3% | 8.7% | 4.0 | 0.756 | 13.5% |
| Vidisha | 103 | 37.9% | 22.3% | 2.0 | 0.840 | 6.8% |
| Sehore | 94 | 38.3% | 25.5% | 2.0 | 0.821 | 10.6% |
| Satna | 93 | 7.5% | 4.3% | 6.3 | 0.703 | 29.0% |
| Dindori | 91 | 8.8% | 0.0% | 6.4 | 0.697 | 17.6% |
| East_Chhindwara | 89 | 16.9% | 9.0% | 7.3 | 0.761 | 4.5% |
| South_Balaghat | 87 | 29.9% | 6.9% | 2.9 | 0.828 | 8.0% |
| Shivpuri | 85 | 8.2% | 4.7% | 10.1 | 0.605 | 16.5% |
| Obedullahganj | 84 | 39.3% | 21.4% | 2.0 | 0.858 | 7.1% |
| Anuppur | 79 | 11.4% | 3.8% | 6.4 | 0.696 | 21.5% |
| Umaria | 70 | 18.6% | 14.3% | 5.1 | 0.788 | 5.7% |
| West_Chhindwara | 67 | 10.4% | 3.0% | 7.3 | 0.732 | 10.4% |
| South_Chhindwara | 67 | 34.3% | 17.9% | 2.0 | 0.826 | 11.9% |
| South_Seoni | 66 | 39.4% | 12.1% | 2.0 | 0.848 | 9.1% |

## How to read this

- **km to CRITICAL** = for a given actual fire, how far away was the nearest cell v17 flagged CRITICAL? 0 = the fire cell itself was CRITICAL. >20 km = model was looking at a different region entirely.
- **Temporal offset (days)** = positive lead time. v17 issues Thursday; fire detected N days later. If median is 2-4 days the model is giving usable advance notice. If it's close to 0 or negative, v17 is reacting, not predicting.
- **Recall@5%** varies wildly by division because Hawkes self-excitation dominates. Divisions with recent fire activity get tight spatial/temporal offsets; quiet divisions with sudden outbreaks are frequently missed.

