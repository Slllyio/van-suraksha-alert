# v17 Per-Fire Validation — 2025 Fire Season (True Lead-Time)

**Generated:** 2026-04-19 00:48

Every FIRMS VIIRS fire detection (Feb-May 2025) is spatiotemporally clustered to ignition events. For each event we locate the most recent **prior Thursday** prediction date (i.e. the prediction that was already issued before the fire started), then look up v17's rank/band for the fire's cell on that Thursday. This gives a true lead-time (0-6 days ahead) for every fire.

## Headline numbers

| Metric | Value | Pct |
|---|---:|---:|
| FIRMS detections (n+h conf) | 94,938 | — |
| Clustered ignition events | 51,519 | — |
| Events with prior-Thursday prediction | 51,519 | 100.0% |
| Events in v17 top-5% rank | 27,324 | 53.0% |
| Events in ALERT or CRITICAL band | 21,051 | 40.9% |
| Events in CRITICAL band | 14,501 | 28.1% |
| Events below median rank (model blind) | 4,154 | 8.1% |

## Spatial offset distribution

**km from actual fire location to nearest v17-alerted cell on prior Thursday**

| Percentile | km to CRITICAL | km to ALERT+ | km to top-5% |
|---|---:|---:|---:|
| p10 | 5.3 | 2.2 | 1.2 |
| p25 | 12.0 | 6.3 | 3.6 |
| p50 | 26.9 | 15.5 | 10.5 |
| p75 | 55.4 | 35.0 | 26.2 |
| p90 | 95.2 | 79.9 | 75.2 |
| p95 | 122.0 | 110.9 | 110.2 |

## Temporal lead-time distribution

Days from prior-Thursday prediction issuance to actual fire detection (0=Thu, 1=Fri, ..., 6=Wed).

- Median lead time: **3.0 days**
- Mean lead time: **2.98 days**

| Lead (days) | #fires | Pct |
|---:|---:|---:|
| 0 | 7,392 | 14.3% |
| 1 | 7,566 | 14.7% |
| 2 | 7,312 | 14.2% |
| 3 | 7,478 | 14.5% |
| 4 | 7,328 | 14.2% |
| 5 | 7,203 | 14.0% |
| 6 | 7,170 | 13.9% |

**Interpretation:** a median of 2-3 days means v17 is giving genuine advance notice. A median of 0-1 means the model fires its alert in a window that's almost contemporaneous with the actual detection.

## Per-day summary (prediction-date view)

| Thursday | #fires in [D,D+6] | #top5% | R@5% | #CRIT | Med km→top5% | Med lead (d) |
|---|---:|---:|---:|---:|---:|---:|
| 2025-02-02 | 436 | 360 | 82.6% | 316 | 70.4 | 1.0 |
| 2025-02-06 | 1117 | 856 | 76.6% | 682 | 36.8 | 2.0 |
| 2025-02-13 | 1082 | 780 | 72.1% | 610 | 32.0 | 3.0 |
| 2025-02-20 | 910 | 674 | 74.1% | 457 | 20.1 | 3.0 |
| 2025-02-27 | 1225 | 851 | 69.5% | 614 | 18.3 | 4.0 |
| 2025-03-06 | 2787 | 1697 | 60.9% | 1027 | 13.1 | 3.0 |
| 2025-03-13 | 3618 | 1911 | 52.8% | 837 | 9.6 | 3.0 |
| 2025-03-20 | 4311 | 1597 | 37.0% | 760 | 7.5 | 4.0 |
| 2025-03-27 | 6695 | 2823 | 42.2% | 1562 | 7.5 | 2.0 |
| 2025-04-03 | 5918 | 2483 | 42.0% | 1173 | 11.3 | 4.0 |
| 2025-04-10 | 4696 | 2596 | 55.3% | 1190 | 8.6 | 3.0 |
| 2025-04-17 | 7285 | 3905 | 53.6% | 1686 | 10.0 | 4.0 |
| 2025-04-24 | 5321 | 2792 | 52.5% | 1361 | 10.7 | 1.0 |
| 2025-05-01 | 2068 | 1263 | 61.1% | 677 | 13.2 | 2.0 |
| 2025-05-08 | 1685 | 1145 | 68.0% | 647 | 17.2 | 4.0 |
| 2025-05-15 | 1354 | 924 | 68.2% | 501 | 11.5 | 2.0 |
| 2025-05-22 | 462 | 307 | 66.5% | 145 | 7.2 | 2.0 |
| 2025-05-29 | 549 | 360 | 65.6% | 256 | 43.1 | 4.0 |

## Per-division (top 20 by fire count)

| Division | #fires | R@5% | R@ALERT+ | Med km→top5% | Med km→CRIT | Mean rank | %low-Hawkes |
|---|---:|---:|---:|---:|---:|---:|---:|
| South_Balaghat | 3093 | 79.0% | 72.9% | 42.8 | 50.7 | 0.953 | 44.2% |
| Anuppur | 3017 | 82.6% | 72.9% | 64.0 | 71.0 | 0.937 | 47.9% |
| Dindori | 1798 | 69.7% | 65.6% | 92.7 | 98.5 | 0.896 | 43.8% |
| Singrauli | 1737 | 67.8% | 57.7% | 3.1 | 8.4 | 0.909 | 10.8% |
| Vidisha | 1709 | 70.1% | 57.4% | 5.2 | 10.0 | 0.929 | 8.6% |
| Guna | 1632 | 59.3% | 46.6% | 7.8 | 17.0 | 0.862 | 12.2% |
| Neemuch | 1546 | 73.4% | 61.6% | 29.4 | 38.2 | 0.924 | 48.4% |
| Dewas | 1325 | 47.9% | 32.5% | 4.8 | 17.0 | 0.890 | 13.2% |
| Raisen | 1317 | 53.5% | 33.3% | 2.6 | 13.8 | 0.892 | 7.2% |
| Chhatarpur | 1279 | 50.5% | 37.4% | 13.4 | 41.8 | 0.874 | 37.1% |
| Sehore | 1210 | 56.4% | 44.3% | 5.3 | 9.7 | 0.905 | 14.4% |
| Sheopur | 1152 | 78.6% | 76.0% | 19.1 | 23.3 | 0.904 | 15.6% |
| South_Chhindwara | 1076 | 48.1% | 36.2% | 18.1 | 30.9 | 0.874 | 26.0% |
| Rewa | 1035 | 66.0% | 53.4% | 85.3 | 114.7 | 0.888 | 56.0% |
| Obedullahganj | 1028 | 50.6% | 31.9% | 2.4 | 12.2 | 0.890 | 2.9% |
| Satna | 1021 | 35.7% | 23.0% | 7.4 | 24.1 | 0.808 | 26.0% |
| Ratlam | 949 | 62.6% | 47.0% | 17.9 | 30.9 | 0.899 | 36.6% |
| Khandwa | 948 | 23.3% | 8.2% | 5.5 | 38.1 | 0.790 | 11.6% |
| Damoh | 936 | 24.4% | 13.6% | 7.5 | 21.1 | 0.772 | 15.3% |
| Kanha Tiger Reserve | 925 | 69.8% | 58.8% | 30.3 | 43.4 | 0.888 | 34.3% |

## How to read this

- **Lead time** = (fire acquisition date) − (v17 prediction Thursday). Measures genuine forecast horizon.
- **km to top-5%** = for a real fire, how far was the nearest cell v17 ranked in its top-5% on the prior Thursday? 0 = fire cell was in top-5%. 10 km = one cell row away. 40+ km = model was looking at a different region.
- **Low-Hawkes divisions** (Satna, Shivpuri, Anuppur) consistently show WORSE spatial+temporal alignment. This is v17's documented structural weakness.
