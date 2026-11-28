# Survey-calibrated state models vs the current rule (Guna, 7 Nov 2026)

Labels: 2015 Forest Dept stock survey, 4,026 compartments, interior pixels (30 m erosion), 346 mixed compartments dropped (rabi NDVI IQR > 0.25).
Classes forest (UNDER STOCK, PLANTATION) / open (BLANK) / farm (CULTIVATION, ENCROACHMENT, PATTA).

Models (settings fixed before any scoring; leave-one-range-out CV over 8 ranges):
- A: Prithvi-EO-2.0-300M on HLS L30 2015, 3 seasons x 6 bands, 224 px. Blocks 1-20 frozen, blocks 21-24 + segmentation head fine-tuned on DirectML (AMD RX 9060 XT), 4 epochs.
- B: MLP on the 2017 AlphaEarth embedding (stands in for 2015).
- C: LightGBM on HLS 2015 seasonal bands and indices.
Change rule: forest in 2015 and non-forest in >= 2 of 2023-25 = loss; farm in >= 2 of 2023-25 and not farm in 2015 = new farm. HLS years z-matched to 2015.

Files: cv_A.csv, cv_B.csv, cv_C.csv (held-out state accuracy, confusion per range); head_to_head.csv (all label sets, every method); guna_totals_by_method.csv.

Result: no survey model beats the current rule. State accuracy is 70.7% (C), 68.5% (B) and 41.7% (A; it overfits and calls held-out land farm).
Differencing yearly states at ~70% accuracy turns state errors into false change: precision 9-18% at the 284 points vs 52% for the current rule, and
Guna loss area 30,000-60,000 ha vs the sample estimate of about 6,900 ha.

Caveats: the survey is compartment-level and may be mixed inside; Guna only (elsewhere the Landsat old-field model would be the 2015 baseline);
it labels state, not change; B uses 2017 as the 2015 proxy.
