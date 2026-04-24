---
title: v17.5 Known Weaknesses
tags: [model, limitations]
---

# Known Weaknesses

## Cold-start blind spot

**77% of fires actually start in low-Hawkes cells** (quiet regions with no recent activity). v17.5 is near-random in this regime: **5.9% R@5% in low-Hawkes vs 25.5% R@5% in high-Hawkes**.

**Mitigation:** operational pipeline applies a **CLIMATOLOGY FLOOR** decoration — any cell whose 5-year week-of-year fire rate exceeds the 80th percentile gets auto-promoted to WATCH. See [[../02-Operations/Daily Alert Pipeline]].

## Visual precursor: dead end

Multiple experiments confirmed anthropogenic fire-precursor signals are NOT visible at our 2 km cell resolution:

- **VLM (LLaVA-7b) on S2 chips** — MW p=0.74, templated responses, image-agnostic
- **CLIP-ViT-L/14 embeddings** — 5-fold ROC 0.562, perm p=0.095
- **Temporal NDVI/BSI delta features** — 5-fold ROC 0.539
- **Sentinel-1 SAR amplitude** — ρ≈0.01, p>0.3
- **Dynamic World monthly LULC** — model ignored features (1 of 30 in top-30 gain)
- **Prithvi-EO-2.0 BurnScars (US-pretrained)** — median F1=0.013

The common failure mode: 50-200 m² farmer clearings are **sub-cell** at 2 km aggregation. See [[Confirmed Dead Ends]].

## GDELT/news data

GDELT ActionGeo is district-centroid only. 7,204 MP events → 0 village-level geocoded fire matches. Would need Hindi NER + Nominatim for ~5-7 days of work.

## Related

- [[v17.5 Model Card]]
- [[Confirmed Dead Ends]]
- [[../06-Swarm-Reports/Architect Review]]
- Home: [[INDEX]]
