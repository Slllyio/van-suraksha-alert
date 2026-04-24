---
title: JwalaNetra Operations Knowledge Vault
project: jwalanetra
vault-role: index
tags: [moc, home]
---

# JwalaNetra / VanAagni — Operations Knowledge Vault

> Forest fire Early Warning System for Madhya Pradesh. 87 divisions, 8,973 beats, ~94,000 km² forest. Production model **v17.5** (LightGBM × hurdle blend).

## Map of Content

### Overview
- [[01-Overview/Project Brief]]
- [[01-Overview/Architecture]]
- [[01-Overview/Production Status]]
- [[01-Overview/Confirmed Dead Ends]]

### Operations
- [[02-Operations/Daily Alert Pipeline]]
- [[02-Operations/Portal Playbook]]
- [[02-Operations/Escalation SOP]]
- Today: [[02-Operations/Daily/2026-04-24]]
- [[_Templates/Daily Alert]] (template)

### Divisions
87 forest divisions. Query the live alert count via [[_Bases/alerts.base]].
- [[03-Divisions/Betul]]
- [[03-Divisions/Guna]]
- [[03-Divisions/Hoshangabad]]
- _(others auto-created as officers record notes)_

### Model
- [[04-Model/v17.5 Model Card]]
- [[04-Model/Honest Metrics]]
- [[04-Model/Feature Importance]]
- [[04-Model/Trust Tiers]]
- [[04-Model/Known Weaknesses]]

### API & SDKs
- [[05-API/Endpoint Reference]]
- [[05-API/Envelope Contract]]
- [[05-API/Pagination Cookbook]]
- [[05-API/Error Handling]]

### Swarm Reviews (2026-04-24)
- [[06-Swarm-Reports/Architect Review]]
- [[06-Swarm-Reports/Security Audit]]
- [[06-Swarm-Reports/Frontend Review]]
- [[06-Swarm-Reports/OpenAPI Audit]]
- [[06-Swarm-Reports/Python SDK Report]]
- [[06-Swarm-Reports/TS SDK Report]]
- [[06-Swarm-Reports/Backfill Report]]

## Interactive Views

- [[_Bases/alerts|🔎 Alerts Base]] — filterable by division, band, trust, date
- [[_Bases/actions|✅ Field Actions Base]] — dispatched / monitored / awareness log
- [[_Bases/divisions|🗺 Divisions Base]] — per-division rollup

## How to use this vault

1. Open the folder `obsidian-vault/` as an Obsidian vault (**File → Open folder as vault**).
2. Install the **Bases** core plugin (Settings → Core plugins) for interactive database views.
3. Daily alerts auto-populate under `02-Operations/Daily/YYYY-MM-DD.md` when you run:
   ```
   python scripts/export_obsidian_daily.py
   ```
4. Officers record dispatches / field responses inline by editing daily notes.
5. The vault cross-links with the live backend at http://localhost:8790 — `[[02-Operations/Daily/2026-04-24]]` shows the same 1,570 alerts the portal shows.
