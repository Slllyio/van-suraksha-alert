"""Generate an Obsidian daily-alert note from the latest v17 prediction JSON.

Writes to `obsidian-vault/02-Operations/Daily/<YYYY-MM-DD>.md` with:
  * YAML frontmatter (picked up by the alerts.base view)
  * Top-5 highest-ranked cells table
  * Wikilinks to model card / prev-next days / home

Usage::

    python scripts/export_obsidian_daily.py                 # today
    python scripts/export_obsidian_daily.py --date 2026-04-24
    python scripts/export_obsidian_daily.py --source outputs/dashboard_feed/ignition_risk_v17_2026-04-24.json

Exits 0 on success, 2 if the source JSON is missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
VAULT_DAILY = ROOT / "obsidian-vault" / "02-Operations" / "Daily"


def _resolve_source(target_date: str, explicit_source: str | None) -> Path:
    if explicit_source:
        return Path(explicit_source)
    dated = FEED_DIR / f"ignition_risk_v17_{target_date}.json"
    if dated.exists():
        return dated
    # Fallback to the canonical symlink-like file written by the pipeline.
    return FEED_DIR / "ignition_risk_v17.json"


def _fwi_context(target_date: str) -> tuple[float, str]:
    """Return (fwi_max, fwi_label) for the target date. Best-effort only."""
    fwi_path = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
    if not fwi_path.exists():
        return 0.0, "Unknown"
    try:
        import pandas as pd

        fwi = pd.read_parquet(fwi_path)
        mask = fwi["date"].astype(str) == target_date
        subset = fwi.loc[mask]
        if subset.empty:
            return 0.0, "No data"
        fwi_max = float(subset["fwi"].max())
        label = "Unknown"
        if "severity" in subset.columns:
            modes = subset["severity"].mode()
            if len(modes) > 0:
                label = str(modes.iloc[0])
        return fwi_max, label
    except Exception as exc:  # pragma: no cover — best-effort metadata
        return 0.0, f"probe-failed: {exc.__class__.__name__}"


def render(payload: dict, target_date: str) -> str:
    alerts = payload.get("banded_alerts", [])
    bands: Counter[str] = Counter(
        (a.get("band") or "").upper() for a in alerts
    )
    top = sorted(alerts, key=lambda a: -(a.get("rank") or 0.0))[:5]
    fwi_max, fwi_label = _fwi_context(target_date)

    prev_date = (
        datetime.strptime(target_date, "%Y-%m-%d").date() - timedelta(days=1)
    ).isoformat()
    next_date = (
        datetime.strptime(target_date, "%Y-%m-%d").date() + timedelta(days=1)
    ).isoformat()

    generated_at = payload.get("generated_at", "")
    hurdle_variant = (
        (payload.get("hurdle_blend") or {}).get("variant") or "unknown"
    )
    critical = bands.get("CRITICAL", 0)
    alert = bands.get("ALERT", 0)
    watch = bands.get("WATCH", 0)
    total = len(alerts)

    # Trust-tier heuristic: if critical count > 0 and the highest-rank cells
    # are high-Hawkes, flag HIGH; else MEDIUM.
    avg_hawkes_top = sum(c.get("hawkes_lambda", 0) for c in top) / max(
        1, len(top)
    )
    trust_tier = "HIGH" if avg_hawkes_top > 0.01 else "MEDIUM"
    if critical == 0:
        trust_tier = "LOW"

    lines: list[str] = []
    lines.append("---")
    lines.append(f"date: {target_date}")
    lines.append(f"prediction-date: {target_date}")
    lines.append(f"critical: {critical}")
    lines.append(f"alert: {alert}")
    lines.append(f"watch: {watch}")
    lines.append(f"total-alerts: {total}")
    lines.append("model-version: v17.5")
    lines.append(f"trust-tier: {trust_tier}")
    lines.append(f"fwi-max: {fwi_max:.1f}")
    lines.append(f"fwi-label: {fwi_label}")
    lines.append("divisions-covered: 87")
    lines.append("fires-observed: 0")
    lines.append("status: fresh")
    lines.append(f"generated-at: {generated_at}")
    lines.append("tags: [daily, alerts, v17]")
    lines.append("cssclasses: [daily-alert]")
    lines.append("---")
    lines.append("")
    lines.append(f"# Fire Alert Brief — {target_date}")
    lines.append("")
    lines.append(
        f"> v17.5 prediction, hurdle blend `{hurdle_variant}`. "
        "Live portal: http://localhost:5173/ · "
        f"API: `GET /api/v2/ignition-v17?date={target_date}`"
    )
    lines.append("")
    lines.append("## At a glance")
    lines.append("")
    lines.append(f"- **🔴 CRITICAL:** {critical:,} cells")
    lines.append(f"- **🟠 ALERT:** {alert:,} cells")
    lines.append(f"- **🟡 WATCH:** {watch:,} cells")
    lines.append(f"- **Total banded alerts:** {total:,}")
    lines.append(f"- **Fire Weather Index (peak):** {fwi_max:.1f} ({fwi_label})")
    lines.append(f"- **Generated:** {generated_at or 'unknown'}")
    lines.append("")
    lines.append("## Top 5 highest-ranked cells")
    lines.append("")
    lines.append(
        "| Rank | Cell | Band | Risk | Hawkes λ | Stage A |"
    )
    lines.append("|---|---|---|---|---|---|")
    for cell in top:
        lines.append(
            f"| {cell.get('rank', 0):.3f} | `{cell.get('cell_id', '')}` | "
            f"{cell.get('band', '')} | {cell.get('ignition_risk', 0):.3f} | "
            f"{cell.get('hawkes_lambda', 0):.4f} | "
            f"{cell.get('stage_a_risk', 0):.3f} |"
        )
    lines.append("")
    lines.append("## Action log (operators, add inline)")
    lines.append("")
    lines.append("- [ ] ⏰ 03:30 IST — Daily brief reviewed")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append("- Model: [[04-Model/v17.5 Model Card]]")
    lines.append("- Pipeline: [[02-Operations/Daily Alert Pipeline]]")
    lines.append("- Weaknesses: [[04-Model/Known Weaknesses]]")
    lines.append(f"- Prev: [[{prev_date}]] · Next: [[{next_date}]]")
    lines.append("- Home: [[INDEX]]")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--source", default=None)
    parser.add_argument("--out-dir", default=str(VAULT_DAILY))
    args = parser.parse_args(argv)

    source = _resolve_source(args.date, args.source)
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 2

    payload = json.loads(source.read_text(encoding="utf-8"))
    target_date = payload.get("prediction_date", args.date)
    body = render(payload, target_date)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date}.md"
    out_path.write_text(body, encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
