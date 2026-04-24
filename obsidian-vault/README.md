# JwalaNetra Operations Vault

An Obsidian knowledge vault for the MP Forest Fire EWS. Links the code repo, the live portal, and the daily-operations log in one searchable, linkable space.

## Opening

1. Install [Obsidian](https://obsidian.md/) (free).
2. **File → Open folder as vault** → select `e:\FIRE\obsidian-vault\`.
3. Enable the **Bases** core plugin (Settings → Core plugins → Bases → toggle on).
4. Start at [[INDEX]].

## Keeping it fresh

After each daily pipeline run:

```bash
python scripts/export_obsidian_daily.py --date YYYY-MM-DD
```

Writes the daily alert brief to `02-Operations/Daily/<date>.md` with frontmatter the `alerts.base` view reads.

## Structure

- `INDEX.md` — map of content
- `01-Overview/` — project brief, architecture, production status
- `02-Operations/Daily/` — one note per day (auto-generated)
- `03-Divisions/` — per-division notes (manual)
- `04-Model/` — model card, feature importance, weaknesses
- `05-API/` — endpoint reference, envelope contract, cookbook
- `06-Swarm-Reports/` — 2026-04-24 multi-agent review findings
- `_Templates/` — daily-alert template for manual note creation
- `_Bases/` — interactive filterable views (`alerts.base`)
- `_Attachments/` — images, screenshots

## Links out

- Live portal: http://localhost:5173/
- Backend: http://localhost:8790/api/v2/*
- OpenAPI spec: `dashboard/v3/openapi.yaml`
- Code repo root: `e:\FIRE\`
