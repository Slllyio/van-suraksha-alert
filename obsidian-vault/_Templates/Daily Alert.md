---
date: {{date:YYYY-MM-DD}}
prediction-date: {{date:YYYY-MM-DD}}
critical: 0
alert: 0
watch: 0
total-alerts: 0
model-version: v17.5
trust-tier: MEDIUM
fwi-max: 0
fwi-label: Normal
divisions-covered: 87
fires-observed: 0
status: fresh
tags: [daily, alerts, v17]
cssclasses: [daily-alert]
---

# Fire Alert Brief — {{date:YYYY-MM-DD}}

> v17.5 model prediction for {{date:YYYY-MM-DD}}. See live portal at http://localhost:5173/ or API: `GET /api/v2/ignition-v17?date={{date:YYYY-MM-DD}}`.

## At a glance

- **CRITICAL:** `= this.critical` cells — `= "🔴"`
- **ALERT:** `= this.alert` cells — `= "🟠"`
- **WATCH:** `= this.watch` cells — `= "🟡"`
- **Total:** `= this.["total-alerts"]`
- **Fire Weather Index (peak):** `= this.["fwi-max"]` (`= this.["fwi-label"]`)
- **Observed fires yesterday:** `= this.["fires-observed"]` (FIRMS VIIRS)

## Top divisions at risk

Links are auto-generated from the highest-confidence cells.

- [[03-Divisions/Betul]] — 0 CRITICAL
- [[03-Divisions/Guna]] — 0 CRITICAL
- [[03-Divisions/Hoshangabad]] — 0 CRITICAL

## Action log (operators, add inline)

- [ ] ⏰ {{time:HH:mm}} — ___Dispatch decision pending___

```dataview
TABLE WITHOUT ID
  file.link AS "Alert",
  action AS "Action",
  officer AS "Officer",
  status AS "Status"
FROM "02-Operations/Daily/"
WHERE date = this.date
AND action
```

## Model confidence context

- Pixel-level recall (rolling): see [[04-Model/Honest Metrics]]
- Model trust tier applied: `= this.["trust-tier"]`
- If tier=LOW: validate with local patrol before dispatch — see [[02-Operations/Escalation SOP]]

## Related

- Model: [[04-Model/v17.5 Model Card]]
- Pipeline: [[02-Operations/Daily Alert Pipeline]]
- Prev: [[02-Operations/Daily/{{date:YYYY-MM-DD,-1}}]]
- Next: [[02-Operations/Daily/{{date:YYYY-MM-DD,+1}}]]
