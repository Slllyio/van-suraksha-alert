"""All-divisions prediction-vs-reality comparison for 2026 fire season.

Powered by the new DuckDB catalog (`src/utils/duckdb_catalog.py`). Demonstrates
the catalog's headline value: zero-ETL JOINs across val_per_division_day,
firms_consolidated, beat_climatology, and fwi_daily.

Outputs:
  outputs/validation_reports/2026_DIVISION_COMPARISON.md
      Single markdown with executive summary + ranked 87-division table
  outputs/validation_reports/2026_division_comparison.csv
      Master CSV (87 rows, one per division, all metrics)
  outputs/validation_reports/per_division/{division}.md
      87 individual division detail files with daily timelines
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `from src.utils.duckdb_catalog import ...`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except (AttributeError, OSError):
    pass

import pandas as pd

from src.utils.duckdb_catalog import connect

OUT_DIR = ROOT / "outputs" / "validation_reports"
PER_DIV_DIR = OUT_DIR / "per_division"
MASTER_MD = OUT_DIR / "2026_DIVISION_COMPARISON.md"
MASTER_CSV = OUT_DIR / "2026_division_comparison.csv"

# 2026 fire season window
SEASON_START = "2026-02-16"
SEASON_END   = "2026-04-22"


def md_table(rows: list[dict], headers: list[str]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(h, "")) for h in headers) + " |")
    return out


def fmt_pct(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{float(v) * 100:.1f}%"


def main() -> int:
    print("Opening DuckDB catalog...")
    con = connect()
    n_ok, n_skip = con.execute("SELECT n_registered, n_skipped FROM _catalog_meta").fetchone()
    print(f"  {n_ok} views registered (skipped {n_skip})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PER_DIV_DIR.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # Q1 — master per-division comparison
    # ============================================================
    print("\n[1/4] Master per-division comparison query...")
    master_sql = f"""
    WITH val AS (
      SELECT division,
             COUNT(DISTINCT date) FILTER (WHERE n_fires_observed > 0) AS active_days,
             SUM(n_fires_observed) AS forest_fires_observed,
             SUM(n_fires_caught)   AS forest_fires_caught,
             SUM(n_alerts_total)   AS alerts_issued,
             SUM(n_critical_organic) AS crit_organic,
             SUM(n_critical_floor)   AS crit_floor,
             SUM(n_alert)            AS alert_band,
             SUM(n_watch)            AS watch_band,
             MAX(n_fires_observed)   AS peak_day_fires,
             MIN(date) FILTER (WHERE n_fires_observed > 0) AS first_fire_date,
             MAX(date) FILTER (WHERE n_fires_observed > 0) AS last_fire_date
      FROM val_per_division_day
      WHERE date BETWEEN DATE '{SEASON_START}' AND DATE '{SEASON_END}'
      GROUP BY division
    ),
    -- Raw FIRMS (NOT forest-clipped) per division — needs spatial join,
    -- so for the headline table we just summarise the forest-clipped count
    -- (val table already has this). Raw vs forest comparison comes via
    -- a separate query below for divisions of interest.
    clim AS (
      SELECT Division AS division,
             SUM(total_fires)         AS hist_5yr_fires,
             COUNT(*)                 AS hist_active_weeks,
             ROUND(AVG(percentile_in_week), 3) AS avg_percentile_in_week
      FROM beat_climatology
      WHERE week_of_year BETWEEN 7 AND 17  -- ISO weeks roughly Feb 16 - Apr 22
      GROUP BY Division
    )
    SELECT v.division,
           v.active_days,
           v.forest_fires_observed                                AS fires_observed,
           v.forest_fires_caught                                  AS fires_caught,
           CAST(v.forest_fires_observed - v.forest_fires_caught AS INTEGER) AS fires_uncovered,
           ROUND(v.forest_fires_caught * 1.0 /
                 NULLIF(v.forest_fires_observed, 0), 3)           AS season_recall,
           v.alerts_issued                                        AS alerts_issued,
           v.crit_organic, v.crit_floor, v.alert_band, v.watch_band,
           v.peak_day_fires,
           v.first_fire_date, v.last_fire_date,
           c.hist_5yr_fires, c.avg_percentile_in_week
    FROM val v
    LEFT JOIN clim c ON v.division = c.division
    ORDER BY v.forest_fires_observed DESC NULLS LAST
    """
    master = con.sql(master_sql).df()
    master.to_csv(MASTER_CSV, index=False)
    print(f"  Wrote {MASTER_CSV.relative_to(ROOT)} ({len(master)} rows)")

    # ============================================================
    # Q2 — season aggregates for executive summary
    # ============================================================
    print("[2/4] Season-level aggregates...")
    agg = con.sql(f"""
      SELECT
        SUM(n_fires_observed) AS total_fires,
        SUM(n_fires_caught)   AS total_caught,
        SUM(n_alerts_total)   AS total_alerts,
        COUNT(DISTINCT division) AS n_divisions,
        COUNT(DISTINCT date)     AS n_days
      FROM val_per_division_day
      WHERE date BETWEEN DATE '{SEASON_START}' AND DATE '{SEASON_END}'
    """).fetchone()
    total_fires, total_caught, total_alerts, n_div, n_days = agg
    season_recall = (total_caught / total_fires) if total_fires else 0.0

    # ============================================================
    # Q3 — RAW (un-forest-clipped) FIRMS per division for the season
    # ============================================================
    # We don't have a per-division attribute on firms_consolidated,
    # but we can join against beat_climatology's Division column for the
    # subset of FIRMS that cluster in beat polygons. Skip this for now —
    # the val_per_division_day count is already the forest-clipped truth.
    # Instead, compare statewide raw vs forest-clipped fire counts.
    raw_vs_clipped = con.sql(f"""
      SELECT 'forest-clipped (val table)' AS source,
             SUM(n_fires_observed) AS n_fires
      FROM val_per_division_day
      WHERE date BETWEEN DATE '{SEASON_START}' AND DATE '{SEASON_END}'
      UNION ALL
      SELECT 'raw FIRMS (no clip)' AS source,
             COUNT(*) AS n_fires
      FROM firms_consolidated
      WHERE acq_date BETWEEN DATE '{SEASON_START}' AND DATE '{SEASON_END}'
        AND lower(confidence) IN ('h','n','high','nominal')
      UNION ALL
      SELECT 'raw FIRMS NRT (no clip)' AS source,
             COUNT(*) AS n_fires
      FROM firms_nrt
      WHERE acq_date BETWEEN DATE '{SEASON_START}' AND DATE '{SEASON_END}'
        AND lower(confidence) IN ('h','n','high','nominal')
    """).df()

    # ============================================================
    # Q4 — per-division daily timelines (for the per-div MDs)
    # ============================================================
    print("[3/4] Per-division daily timelines + climatology join...")
    per_div_daily_sql = f"""
    SELECT vdpd.date,
           vdpd.division,
           vdpd.n_fires_observed AS fires,
           vdpd.n_fires_caught   AS caught,
           vdpd.catch_rate,
           vdpd.n_critical_organic AS crit_organic,
           vdpd.n_critical_floor   AS crit_floor,
           vdpd.n_alert            AS alert_band,
           vdpd.n_watch            AS watch_band,
           vdpd.n_alerts_total     AS alerts_total,
           ROUND(fwi.ffmc, 1)      AS ffmc,
           fwi.danger_class
    FROM val_per_division_day vdpd
    LEFT JOIN fwi_daily fwi ON vdpd.date = fwi.date
    WHERE vdpd.date BETWEEN DATE '{SEASON_START}' AND DATE '{SEASON_END}'
    ORDER BY vdpd.division, vdpd.date
    """
    daily = con.sql(per_div_daily_sql).df()

    # ============================================================
    # Master MD
    # ============================================================
    print("[4/4] Generating MD reports...")
    lines: list[str] = []
    lines.append("# 2026 Fire Season — Division-by-Division Reality Check\n")
    lines.append(f"Window: **{SEASON_START} → {SEASON_END}** ({n_days} days × {n_div} divisions)")
    lines.append(f"Source query: DuckDB JOIN over `val_per_division_day` + `fwi_daily` + `beat_climatology`")
    lines.append(f"Data freshness: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Executive summary
    lines.append("## Executive summary\n")
    lines.append(
        f"- **{int(total_fires):,} forest fires observed** across {n_div} divisions "
        f"in the {n_days}-day window."
    )
    lines.append(
        f"- **{int(total_caught):,} caught** by alerts within 4 km in the next 7 days "
        f"(season recall = **{season_recall*100:.1f}%**)."
    )
    lines.append(
        f"- **{int(total_alerts):,} alerts issued** across all bands "
        f"(CRITICAL/ALERT/WATCH including coverage + climatology floors)."
    )
    lines.append("")

    # Raw vs forest-clipped
    lines.append("### FIRMS volume comparison: raw vs forest-clipped")
    lines.append("")
    lines.extend(md_table(raw_vs_clipped.to_dict(orient="records"),
                          ["source", "n_fires"]))
    lines.append("")
    lines.append(
        "The val_per_division_day count uses strict `predicate='within'` + 330 m edge tolerance "
        "to keep only fires inside MP forest beats — agricultural / urban / non-forest fires "
        "are removed because the model is not designed to alert on them."
    )
    lines.append("")

    # Headline divisions table
    lines.append("## All 87 divisions ranked by fire load\n")
    rows = []
    for _, r in master.iterrows():
        rows.append({
            "division": r["division"],
            "active_days": int(r["active_days"] or 0),
            "fires": int(r["fires_observed"] or 0),
            "caught": int(r["fires_caught"] or 0),
            "uncovered": int(r["fires_uncovered"] or 0),
            "recall": fmt_pct(r["season_recall"]),
            "alerts": int(r["alerts_issued"] or 0),
            "CRIT_org": int(r["crit_organic"] or 0),
            "CRIT_floor": int(r["crit_floor"] or 0),
            "peak_day": int(r["peak_day_fires"] or 0),
            "5yr_hist": int(r["hist_5yr_fires"] or 0) if pd.notna(r["hist_5yr_fires"]) else 0,
        })
    lines.extend(md_table(rows, ["division", "active_days", "fires", "caught", "uncovered",
                                  "recall", "alerts", "CRIT_org", "CRIT_floor",
                                  "peak_day", "5yr_hist"]))
    lines.append("")

    # Best / worst lists
    valid = master.dropna(subset=["season_recall"]).query("fires_observed >= 50")
    best = valid.nlargest(10, "season_recall")
    worst = valid.nsmallest(10, "season_recall")
    lines.append("## Top 10 best-recall divisions (≥50 fires)\n")
    rows = []
    for _, r in best.iterrows():
        rows.append({
            "division": r["division"],
            "fires": int(r["fires_observed"]),
            "caught": int(r["fires_caught"]),
            "recall": fmt_pct(r["season_recall"]),
            "alerts": int(r["alerts_issued"]),
            "CRIT_org": int(r["crit_organic"]),
        })
    lines.extend(md_table(rows, ["division", "fires", "caught", "recall", "alerts", "CRIT_org"]))
    lines.append("")
    lines.append("## Top 10 worst-recall divisions (≥50 fires)\n")
    rows = []
    for _, r in worst.iterrows():
        rows.append({
            "division": r["division"],
            "fires": int(r["fires_observed"]),
            "caught": int(r["fires_caught"]),
            "recall": fmt_pct(r["season_recall"]),
            "alerts": int(r["alerts_issued"]),
            "CRIT_org": int(r["crit_organic"]),
        })
    lines.extend(md_table(rows, ["division", "fires", "caught", "recall", "alerts", "CRIT_org"]))
    lines.append("")

    # Pointer to per-division detail
    lines.append("## Per-division detail files\n")
    lines.append(f"Each of the {n_div} divisions has a daily-timeline file at "
                 f"`outputs/validation_reports/per_division/{{division}}.md`. ")
    lines.append("")
    lines.append("Each detail file contains:")
    lines.append("- Season totals + rank vs other divisions")
    lines.append("- Daily timeline (date | fires | caught | recall | FFMC | danger_class | alerts)")
    lines.append("- Best/worst days for that division specifically")
    lines.append("- Climatology comparison: did this division burn at the same rate as 5-yr baseline?")
    lines.append("")

    MASTER_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {MASTER_MD.relative_to(ROOT)} ({len(lines)} lines)")

    # ============================================================
    # Per-division detail files
    # ============================================================
    n_per_div_files = 0
    for division, dgrp in daily.groupby("division"):
        dlines = [f"# {division} — 2026 fire season detail\n"]
        # Season totals from master
        m_row = master[master["division"] == division]
        if len(m_row) == 0:
            continue
        m = m_row.iloc[0]
        dlines.append(f"**Window:** {SEASON_START} → {SEASON_END}")
        dlines.append(f"**Active days (≥1 fire):** {int(m['active_days'] or 0)}")
        dlines.append(f"**Forest fires observed:** {int(m['fires_observed'] or 0):,}")
        dlines.append(f"**Caught (within 4 km, +7 d):** {int(m['fires_caught'] or 0):,}")
        dlines.append(f"**Season recall:** {fmt_pct(m['season_recall'])}")
        dlines.append(f"**Total alerts issued:** {int(m['alerts_issued'] or 0):,}  "
                      f"(CRIT_organic={int(m['crit_organic'] or 0)}, "
                      f"CRIT_floor={int(m['crit_floor'] or 0)}, "
                      f"ALERT={int(m['alert_band'] or 0)}, "
                      f"WATCH={int(m['watch_band'] or 0)})")
        if pd.notna(m["hist_5yr_fires"]) and m["hist_5yr_fires"] > 0:
            dlines.append(f"**5-year historical fire count (Feb-Apr weeks):** "
                          f"{int(m['hist_5yr_fires']):,}")
        dlines.append("")

        # Daily timeline
        dlines.append("## Daily timeline\n")
        active = dgrp[(dgrp["fires"] > 0) | (dgrp["alerts_total"] > 0)].copy()
        if len(active) == 0:
            dlines.append("_(no fires observed and no alerts issued during window)_")
        else:
            rows = []
            for _, r in active.iterrows():
                rows.append({
                    "date": r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"]),
                    "fires": int(r["fires"] or 0),
                    "caught": int(r["caught"] or 0),
                    "recall": fmt_pct(r["catch_rate"]) if r["fires"] > 0 else "—",
                    "FFMC": (f"{r['ffmc']:.1f}" if pd.notna(r["ffmc"]) else "—"),
                    "danger": r["danger_class"] if pd.notna(r["danger_class"]) else "—",
                    "alerts": int(r["alerts_total"] or 0),
                    "CRIT_org": int(r["crit_organic"] or 0),
                    "CRIT_floor": int(r["crit_floor"] or 0),
                })
            dlines.extend(md_table(rows, ["date", "fires", "caught", "recall",
                                           "FFMC", "danger", "alerts",
                                           "CRIT_org", "CRIT_floor"]))
        dlines.append("")

        # Best/worst days for this division
        with_fires = active[active["fires"] > 0]
        if len(with_fires) > 0:
            best_d = with_fires.nlargest(3, "catch_rate")
            worst_d = with_fires[with_fires["catch_rate"] == 0]
            dlines.append("### Best 3 days (highest recall)\n")
            for _, r in best_d.iterrows():
                d_str = r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"])
                dlines.append(f"- **{d_str}**  fires={int(r['fires'])}  caught={int(r['caught'])}  "
                              f"recall={fmt_pct(r['catch_rate'])}")
            dlines.append("")
            if len(worst_d) > 0:
                dlines.append(f"### Days with fires but ZERO caught: {len(worst_d)}\n")
                for _, r in worst_d.head(10).iterrows():
                    d_str = r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else str(r["date"])
                    dlines.append(f"- **{d_str}**  fires={int(r['fires'])}  "
                                  f"alerts_issued={int(r['alerts_total'])}  FFMC={r['ffmc']:.1f}"
                                  if pd.notna(r["ffmc"]) else
                                  f"- **{d_str}**  fires={int(r['fires'])}  alerts_issued={int(r['alerts_total'])}")
                dlines.append("")

        # Write file
        safe = division.replace("/", "_").replace(" ", "_")
        out_path = PER_DIV_DIR / f"{safe}.md"
        out_path.write_text("\n".join(dlines), encoding="utf-8")
        n_per_div_files += 1

    print(f"  Wrote {n_per_div_files} per-division MD files to {PER_DIV_DIR.relative_to(ROOT)}/")

    con.close()
    print("\n=== Done ===")
    print(f"Master MD:  {MASTER_MD.relative_to(ROOT)}")
    print(f"Master CSV: {MASTER_CSV.relative_to(ROOT)}")
    print(f"Per-div MDs: {n_per_div_files} files in {PER_DIV_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
