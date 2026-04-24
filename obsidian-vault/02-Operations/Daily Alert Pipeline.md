---
title: Daily Alert Pipeline
schedule: "03:00 IST daily"
runtime-min: 2
tags: [operations, pipeline]
---

# Daily Alert Pipeline

Runs daily at 03:00 IST via Windows Scheduled Task `JwalaNetra_FireEWS`.

## Steps

1. **FWI update + live weather** — `scripts/compute_fwi.py --update-nrt`
   - Pulls Open-Meteo live weather
   - Writes `data_lake/fire_weather/fwi_daily.parquet`
2. **FIRMS NRT fetch** — `scripts/nrt_alert_pipeline.py --fetch-nrt`
   - NASA FIRMS VIIRS/MODIS last 24h
   - Writes `data_lake/alerts/<date>_alert.json`
3. **v17 prediction** — `scripts/predict_ignition_v17.py --use-hurdle-blend`
   - LightGBM x Hurdle blend (geo_w0.7 variant)
   - Writes `outputs/dashboard_feed/ignition_risk_v17_<date>.json`
4. **Alert decoration** — `scripts/build_operational_alerts.py`
   - Applies coverage floor + climatology floor
   - Writes `outputs/dashboard_feed/operational_alerts_v17_<date>.json`
5. **Unified dashboard feed** — merges 1-4 for portal consumption
6. **Obsidian daily-note export** — `scripts/export_obsidian_daily.py`
   - Writes `obsidian-vault/02-Operations/Daily/<date>.md`
   - Used by the [[../_Bases/alerts.base|alerts.base view]]

## Verification after each run

```bash
curl http://localhost:8790/api/v2/healthz
curl "http://localhost:8790/api/v2/ignition-v17?limit=1" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['meta'].get('prediction_date'))"
```

## Related

- [[../04-Model/v17.5 Model Card]]
- [[../04-Model/Known Weaknesses]]
- [[Portal Playbook]]
- [[Escalation SOP]]
- Home: [[../INDEX]]
