---
title: JwalaNetra / VanAagni — Project Brief
project: jwalanetra
status: production
tags: [overview, brief]
---

# Project Brief

**JwalaNetra / VanAagni** is an AI-driven forest-fire Early Warning System for **Madhya Pradesh state**.

## Scale
- **State:** Madhya Pradesh (21.0-27.0°N, 74.0-83.0°E)
- **Forest divisions:** 87
- **Beats:** 8,973
- **Forest area:** ~94,000 km²
- **Forest type:** Dry deciduous (teak, tendu, mahua, bamboo)
- **Fire season:** Feb – May, peak Mar – Apr

## Production stack
- **Model:** [[04-Model/v17.5 Model Card|v17.5]] — LightGBM × Hurdle blend, 111 features
- **Backend:** `dashboard/v3/serve.py` (Python http.server, port 8790)
- **Frontend:** `dashboard/v4/` (React 19 + Vite + deck.gl + framer-motion + Plotly, port 5173)
- **API contract:** [[05-API/Envelope Contract|/api/v2]] — `{ data, meta, links }` envelope + cursor pagination
- **Data:** FIRMS VIIRS + MODIS, Open-Meteo, Copernicus CDS ERA5, MCD64A1 burn area
- **Scheduling:** Windows Task `JwalaNetra_FireEWS`, daily 03:00 IST

## Related
- [[Architecture]] — full architecture diagram
- [[Production Status]] — current model metrics + recent experiments
- [[Confirmed Dead Ends]] — what didn't work and why
- [[02-Operations/Daily Alert Pipeline]]
- Home: [[INDEX]]
