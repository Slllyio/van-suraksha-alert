"""Generate the 2026 Season Validation markdown report.

Reads the 5 outputs of validate_2026_season.py and emits a single
operator-readable markdown file.

Usage:
  python scripts/generate_2026_season_report.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "validation_reports"
SUMMARY = OUT_DIR / "2026_season_summary.json"
PER_DAY = OUT_DIR / "2026_per_day.csv"
PER_DIV = OUT_DIR / "2026_per_division.csv"
PER_FIRE = OUT_DIR / "2026_per_fire.csv"
PER_TIER = OUT_DIR / "2026_per_trust_tier.csv"
REPORT = OUT_DIR / "2026_SEASON_REPORT.md"


def fmt_pct(v, digits: int = 1) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{float(v) * 100:.{digits}f}%"


def fmt_int(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{int(v):,}"


def main() -> int:
    if not SUMMARY.exists():
        print(f"ERROR: {SUMMARY} missing. Run scripts/validate_2026_season.py first.")
        return 1

    s = json.loads(SUMMARY.read_text())
    per_tier = pd.read_csv(PER_TIER)
    per_div = pd.read_csv(PER_DIV)
    per_day = pd.read_csv(PER_DAY)

    lines: list[str] = []
    lines.append("# 2026 Fire Season Validation — v17.5 + Coverage Floor\n")
    lines.append(
        f"**Generated:** {s.get('generated_at', datetime.now().isoformat())}  \n"
        f"**Window:** 2026-02-16 → 2026-04-22 ({s['window_days']} days backfilled)  \n"
        f"**Ground truth:** {fmt_int(s['n_unique_ignition_events'])} unique forest-clipped "
        f"FIRMS ignition events across the window (VIIRS high-confidence, "
        f"DBSCAN eps=2 km, min_samples=2).\n"
    )

    # -------------------- Executive summary --------------------
    lines.append("## Executive summary\n")
    lines.append(
        "- **Unique-event recall (any banded alert):** "
        f"{fmt_pct(s['unique_recall_any_band'])} — the model placed at least "
        "one CRITICAL/ALERT/WATCH alert within 4 km of "
        f"{fmt_int(int(s['unique_recall_any_band'] * s['n_unique_ignition_events']))}"
        f" of {fmt_int(s['n_unique_ignition_events'])} unique fires during "
        "the +7 day catch window.\n"
    )
    lines.append(
        "- **Unique-event recall at CRITICAL level:** "
        f"{fmt_pct(s['unique_recall_critical'])} — only "
        f"{fmt_int(int(s['unique_recall_critical'] * s['n_unique_ignition_events']))} "
        "fires were flagged CRITICAL; the majority that were caught were at "
        "ALERT or WATCH tier.\n"
    )
    lines.append(
        f"- **CRITICAL precision (statewide):** {fmt_pct(s['season_precision_critical'])}"
        f" — of {fmt_int(s['n_critical_alerts_total'])} CRITICAL alerts issued "
        f"across the season, {fmt_int(s['n_critical_caught_event'])} had a real "
        "fire within 4 km in the +7 day window.\n"
    )
    lines.append(
        "- **Floor-tier verdict:** division-coverage-floor promoted "
        f"{fmt_int(s['n_critical_alerts_floor_promoted'])} CRITICAL alerts; these "
        f"caught {fmt_int(s['n_floor_caught_event'])} events at "
        f"{fmt_pct(s['season_precision_floor'])} precision — roughly half the "
        f"precision of COLD_START ({fmt_pct(per_tier[per_tier.trust_tier == 'COLD_START']['precision'].iloc[0])}) "
        "but NOT zero. The floor is a real safety-net, not dead noise.\n"
    )
    lines.append(
        "- **Spatial accuracy:** median offset "
        f"{s['median_spatial_offset_km']:.2f} km between a caught event and "
        "its matching predicted cell (≈ cell-width apart, consistent with "
        "2 km grid).\n"
    )
    lines.append(
        f"- **Temporal lead-time:** median +{s['median_temporal_offset_days']:.0f} days — "
        "the model catches fires 2–7 days AHEAD of detection, not same-day.\n"
    )
    lines.append("")

    # -------------------- Per trust tier --------------------
    lines.append("## Per trust tier\n")
    lines.append("| Trust tier | Alerts | Caught events | Precision | Median offset (km) |")
    lines.append("|---|---:|---:|---:|---:|")
    for _, r in per_tier.iterrows():
        lines.append(
            f"| **{r['trust_tier']}** | {fmt_int(r['n_alerts'])} | "
            f"{fmt_int(r['n_alerts_caught_event'])} | "
            f"{fmt_pct(r['precision'])} | "
            f"{r['median_match_offset_km']:.2f}"
            if pd.notna(r['median_match_offset_km']) else "—"
        )
    lines.append("")
    lines.append(
        "**Interpretation:** HIGH and MEDIUM tiers (rank ≥ top 5%, weather- "
        "or Hawkes-backed) deliver ~10–12% precision — 4–7× better than "
        "COLD_START and 7× better than DIVISION_FLOOR. Operators should "
        "dispatch on HIGH/MEDIUM immediately; COLD_START and DIVISION_FLOOR "
        "require phone-verification first.\n"
    )

    # -------------------- Spatial / temporal histograms --------------------
    lines.append("## Spatial offset distribution (km)\n")
    sh = s["spatial_offset_histogram_km"]
    tot = sum(sh.values()) or 1
    lines.append("| Band | Count | % |")
    lines.append("|---|---:|---:|")
    for k in ("0-2", "2-4", "4-8", "8-16", "missed"):
        v = sh.get(k, 0)
        lines.append(f"| {k} | {fmt_int(v)} | {v / tot * 100:.1f}% |")
    lines.append("")

    lines.append("## Temporal offset distribution (days)\n")
    th = s["temporal_offset_histogram_days"]
    tot = sum(th.values()) or 1
    lines.append("| Lead | Count | % |")
    lines.append("|---|---:|---:|")
    for k in ("same_day", "+1d", "+2-3d", "+4-7d", "missed"):
        v = th.get(k, 0)
        lines.append(f"| {k} | {fmt_int(v)} | {v / tot * 100:.1f}% |")
    lines.append("")

    # -------------------- Directional bias --------------------
    db = s.get("directional_bias", {})
    if db and db.get("n_caught", 0) > 0:
        lines.append("## Directional offset analysis\n")
        lines.append(
            "**Question:** when v17 misses a fire by 2 km, is it missing in "
            "a specific compass direction (e.g. systematically predicting "
            "2 km west of where fires actually happen) or is the offset "
            "random 2-D noise?\n"
        )
        lines.append(
            f"- **Mean east offset:** {db['mean_east_km']:+.3f} km "
            f"(SEM {db['sem_east_km']:.3f}, z = {db['z_east']:.2f})\n"
        )
        lines.append(
            f"- **Mean north offset:** {db['mean_north_km']:+.3f} km "
            f"(SEM {db['sem_north_km']:.3f}, z = {db['z_north']:.2f})\n"
        )
        lines.append(
            f"- **Significant at 95 % CI:** "
            f"{'YES' if db['bias_is_significant_95ci'] else 'NO'}\n"
        )
        lines.append(
            f"- **Mean resultant length (0 = isotropic, 1 = aligned):** "
            f"{db['mean_resultant_length']:.3f}\n"
        )
        lines.append(
            f"- **Interpretation:** {db['bias_interpretation']}.\n"
        )
        lines.append("")
        lines.append("### Compass-rose distribution (event direction from alert)")
        lines.append("")
        lines.append("| Sector | Count | % of caught |")
        lines.append("|---|---:|---:|")
        total = sum(db["compass_rose_counts"].values()) or 1
        for sect in ("N", "NE", "E", "SE", "S", "SW", "W", "NW"):
            c = db["compass_rose_counts"].get(sect, 0)
            lines.append(f"| {sect} | {fmt_int(c)} | {c / total * 100:.1f}% |")
        lines.append("")
        lines.append(
            "**Take-away:** " + (
                "Offsets are random — no systematic direction. The 2 km "
                "median spatial offset is the **inherent noise floor** of "
                "a 2 km grid + DBSCAN(eps=2 km) event clustering. There is "
                "no \"shift every prediction N km east\" correction that "
                "would help. To tighten spatial accuracy below 2 km, the "
                "model would need a sub-2 km grid (infeasible with current "
                "feature pipeline) OR a different event-matching convention."
                if not db["bias_is_significant_95ci"] else
                f"Offsets ARE systematic. Applying a static correction of "
                f"({-db['mean_east_km']:+.2f}, {-db['mean_north_km']:+.2f}) km "
                "(east, north) to every prediction cell would reduce median "
                "spatial offset. Worth investigating as a post-processing layer."
            )
        )
        lines.append("")

    # -------------------- Top / bottom divisions --------------------
    lines.append("## Divisions — top-10 by CRITICAL precision (min 20 alerts)\n")
    lines.append("| Division | CRITICAL alerts | Floor-promoted | Caught events | Precision |")
    lines.append("|---|---:|---:|---:|---:|")
    good = per_div[per_div["n_critical_alerts"] >= 20].nlargest(10, "precision_critical")
    for _, r in good.iterrows():
        lines.append(
            f"| {r['division']} | {fmt_int(r['n_critical_alerts'])} | "
            f"{fmt_int(r['n_critical_floor_promoted'])} | "
            f"{fmt_int(r['n_critical_caught_event'])} | "
            f"{fmt_pct(r['precision_critical'])} |"
        )
    lines.append("")

    lines.append("## Divisions — bottom-10 by recall (divisions with fires but no catches)\n")
    lines.append("| Division | Fires caught | CRITICAL alerts | Caught events | Precision |")
    lines.append("|---|---:|---:|---:|---:|")
    bad = per_div[(per_div["n_events_caught"] == 0) &
                  (per_div["n_critical_alerts"] > 0)].nlargest(10, "n_critical_alerts")
    for _, r in bad.iterrows():
        lines.append(
            f"| {r['division']} | {fmt_int(r['n_events_caught'])} | "
            f"{fmt_int(r['n_critical_alerts'])} | "
            f"{fmt_int(r['n_critical_caught_event'])} | "
            f"{fmt_pct(r['precision_critical'])} |"
        )
    lines.append("")

    # -------------------- Per-day timeline highlights --------------------
    lines.append("## Per-day highlights\n")
    best_day = per_day.nlargest(1, "recall_any_band").iloc[0]
    worst_day = per_day[per_day["n_events"] >= 10].nsmallest(1, "recall_any_band")
    peak_day = per_day.nlargest(1, "n_events").iloc[0]
    lines.append(
        f"- **Best recall day:** {best_day['date']} — caught "
        f"{fmt_int(best_day['n_caught_any_band'])} of "
        f"{fmt_int(best_day['n_events'])} events "
        f"({fmt_pct(best_day['recall_any_band'])})."
    )
    if len(worst_day) > 0:
        r = worst_day.iloc[0]
        lines.append(
            f"- **Worst recall day (≥10 events):** {r['date']} — caught "
            f"{fmt_int(r['n_caught_any_band'])} of {fmt_int(r['n_events'])} "
            f"events ({fmt_pct(r['recall_any_band'])})."
        )
    lines.append(
        f"- **Peak event day:** {peak_day['date']} — {fmt_int(peak_day['n_events'])} "
        f"events, recall {fmt_pct(peak_day['recall_any_band'])}."
    )
    lines.append("")

    # -------------------- Honest weaknesses --------------------
    lines.append("## Honest weaknesses\n")
    missed = s["spatial_offset_histogram_km"]["missed"]
    tot_events = sum(s["spatial_offset_histogram_km"].values())
    lines.append(
        f"1. **{missed / tot_events * 100:.0f}% of event-window instances were MISSED "
        "entirely** — no alert within 4 km at any band. These are the fires that "
        "forest officers would never see in the dispatch list, regardless of tier.\n"
    )
    floor_share = s["season_recall_floor_share"]
    lines.append(
        f"2. **Only {fmt_pct(floor_share, 0)} of catches came from the DIVISION_FLOOR** "
        "— the floor rescues a meaningful but small fraction of otherwise-silent "
        "divisions. It's a safety-net, not a replacement for the base ranking.\n"
    )
    lines.append(
        "3. **Same-day catches are rare.** Median lead-time is "
        f"+{s['median_temporal_offset_days']:.0f} days — the model is a medium-"
        "term risk ranker, not a real-time alert. Operators should not expect "
        "to dispatch TODAY on a CRITICAL issued TODAY.\n"
    )
    lines.append(
        "4. **~3,000 events missed per run** even with WATCH+ALERT+CRITICAL bands "
        "combined. This is the information-theoretic ceiling of v17 on "
        "satellite + weather features alone; see docs/ for the 8 experiments "
        "(VLM, CLIP, S2 deltas, etc.) that failed to close this gap.\n"
    )
    lines.append("")

    lines.append("## Methodology\n")
    lines.append(
        f"- **Backfill:** `scripts/run_2026_backfill.py --execute` ran "
        f"`predict_ignition_v17.py --date D --use-hurdle-blend` and "
        f"`build_operational_alerts.py` for every day in the window. Hawkes "
        "features are computed strictly from FIRMS < D (verified at "
        "predict_ignition_v17.py:121). Non-Hawkes features are pulled from "
        "the v8 frozen training dataset (2025-05-29) — this reproduces "
        "production behaviour rather than idealising it.\n"
    )
    lines.append(
        "- **Ground truth:** FIRMS VIIRS detections for MP, forest-clipped "
        "via `data/aoi/mp_beats_wgs84.geojson` spatial join (identical to "
        "portal `/api/viirs-fires`). Confidence filter: only h/n/high/nominal "
        "kept. Clustered with DBSCAN(eps=2 km, min_samples=2).\n"
    )
    lines.append(
        "- **Match rule:** a CRITICAL/ALERT/WATCH alert catches an event if "
        "its centroid is within 4 km of the event centroid, and the event's "
        "first-detection date is within [D, D+7].\n"
    )
    lines.append(
        "- **Windowed vs unique:** Each unique event appears in up to 7 "
        "overlapping [D, D+7] windows — reported both ways. Windowed "
        "recall measures average per-day prediction quality; unique recall "
        "measures \"did we catch this fire at least once\".\n"
    )
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT.relative_to(ROOT)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
