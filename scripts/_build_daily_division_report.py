"""Generate operator-readable per-date × per-division validation tables.

Reads `outputs/validation_reports/2026_per_division_per_day.csv` (5,742 rows)
and emits `outputs/validation_reports/2026_DAILY_DIVISION_TABLE.md` with:

  Section 1 — Daily timeline (66 rows: one per date, statewide totals)
  Section 2 — Per-division season totals (87 rows)
  Section 3 — ASCII heatmap (66 dates × 30 most-active divisions)
  Section 4 — Drill-down per-day matrix for the worst 5 days
  Section 5 — Drill-down per-day matrix for the best 5 days
  Section 6 — Per-division daily timeline (top 10 fire divisions)

The full 5,742-row matrix is also written as a sortable CSV that the user
can open in Excel / DuckDB.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "outputs" / "validation_reports" / "2026_per_division_per_day.csv"
DST_MD = ROOT / "outputs" / "validation_reports" / "2026_DAILY_DIVISION_TABLE.md"
DST_PIVOT = ROOT / "outputs" / "validation_reports" / "2026_daily_division_pivot_recall.csv"


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


def heat_char(rate: float | None, fires: int) -> str:
    """One-char heatmap glyph keyed to recall rate + fire-load.

      .  no fires
      X  fires + 0% recall
      o  fires + <30%
      O  fires + 30-70%
      ▣  fires + ≥70%
    """
    if not fires or fires == 0:
        return "."
    if rate is None or pd.isna(rate):
        return "X"
    if rate >= 0.70:
        return "▣"
    if rate >= 0.30:
        return "O"
    if rate > 0.0:
        return "o"
    return "X"


def main() -> int:
    df = pd.read_csv(SRC)
    df["date"] = pd.to_datetime(df["date"])
    n_dates = df["date"].nunique()
    n_divs = df["division"].nunique()
    print(f"Loaded {len(df)} rows ({n_dates} dates × {n_divs} divisions)")

    lines: list[str] = []
    lines.append("# 2026 Fire Season — Per-Date × Per-Division Validation\n")
    lines.append(f"Source: `2026_per_division_per_day.csv` "
                 f"({len(df):,} rows × {n_dates} backfilled days × {n_divs} MP divisions)")
    lines.append(f"Method: forest-clipped FIRMS in `[D, D+7]` window, matched to alerts "
                 f"in same beat within 4 km radius. Pixel-level recall.")
    lines.append(f"Updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # ============================================================
    # Section 1 — Daily statewide timeline
    # ============================================================
    lines.append("## 1. Daily statewide timeline (66 days)\n")
    daily = df.groupby("date").agg(
        n_div_with_fires=("n_fires_observed", lambda s: int((s > 0).sum())),
        total_fires=("n_fires_observed", "sum"),
        total_caught=("n_fires_caught", "sum"),
        total_alerts=("n_alerts_total", "sum"),
        total_critical=("n_critical_organic", "sum"),
        total_floor=("n_critical_floor", "sum"),
    ).reset_index()
    daily["uncovered"] = (daily["total_fires"] - daily["total_caught"]).astype(int)
    daily["day_recall"] = daily["total_caught"] / daily["total_fires"]
    daily["day_recall_pct"] = daily["day_recall"].apply(fmt_pct)

    rows = []
    for _, r in daily.iterrows():
        rows.append({
            "date": r["date"].strftime("%Y-%m-%d"),
            "div_w_fires": int(r["n_div_with_fires"]),
            "fires": int(r["total_fires"]),
            "caught": int(r["total_caught"]),
            "uncovered": int(r["uncovered"]),
            "recall": r["day_recall_pct"],
            "alerts": int(r["total_alerts"]),
            "CRIT": int(r["total_critical"]),
            "FLOOR": int(r["total_floor"]),
        })
    lines.extend(md_table(rows, ["date", "div_w_fires", "fires", "caught",
                                  "uncovered", "recall", "alerts", "CRIT", "FLOOR"]))
    lines.append("")

    # ============================================================
    # Section 2 — Per-division season totals
    # ============================================================
    lines.append("## 2. Per-division season totals (87 divisions, sorted by total fires)\n")
    perdiv = df.groupby("division").agg(
        days_with_fires=("n_fires_observed", lambda s: int((s > 0).sum())),
        total_fires=("n_fires_observed", "sum"),
        total_caught=("n_fires_caught", "sum"),
        total_alerts=("n_alerts_total", "sum"),
        total_critical=("n_critical_organic", "sum"),
        total_floor=("n_critical_floor", "sum"),
    ).reset_index()
    perdiv["uncovered"] = (perdiv["total_fires"] - perdiv["total_caught"]).astype(int)
    perdiv["recall"] = perdiv["total_caught"] / perdiv["total_fires"].where(perdiv["total_fires"] > 0)
    perdiv = perdiv.sort_values("total_fires", ascending=False)

    rows = []
    for _, r in perdiv.iterrows():
        rows.append({
            "division": r["division"],
            "days_w_fires": int(r["days_with_fires"]),
            "fires": int(r["total_fires"]),
            "caught": int(r["total_caught"]),
            "uncovered": int(r["uncovered"]),
            "recall": fmt_pct(r["recall"]),
            "alerts": int(r["total_alerts"]),
            "CRIT": int(r["total_critical"]),
            "FLOOR": int(r["total_floor"]),
        })
    lines.extend(md_table(rows, ["division", "days_w_fires", "fires", "caught",
                                  "uncovered", "recall", "alerts", "CRIT", "FLOOR"]))
    lines.append("")

    # ============================================================
    # Section 3 — ASCII heatmap: date rows × top-30 divisions
    # ============================================================
    lines.append("## 3. ASCII heatmap — date × top-30 fire-active divisions\n")
    lines.append("**Glyphs:**  `.` no fires · `o` <30% recall · `O` 30-70% · `▣` ≥70% · `X` fires + 0% recall")
    lines.append("")
    top30_divs = perdiv.head(30)["division"].tolist()
    pivot = df[df["division"].isin(top30_divs)].pivot_table(
        index="date", columns="division",
        values=["n_fires_observed", "n_fires_caught"],
        aggfunc="sum", fill_value=0,
    )
    # Rebuild as parallel arrays
    fires_pivot = pivot["n_fires_observed"]
    caught_pivot = pivot["n_fires_caught"]
    # Re-order columns to match top30 order
    fires_pivot = fires_pivot.reindex(columns=top30_divs)
    caught_pivot = caught_pivot.reindex(columns=top30_divs)

    short_names = [(d[:8] if len(d) > 8 else d).ljust(2) for d in top30_divs]
    header = "    date    | " + "".join(d[:2] for d in top30_divs) + " | divs:"
    lines.append("```")
    lines.append("            " + " " * 12 + "Top 30 fire divisions (2-char codes, hover for full name)")
    # Build legend for codes -> div names (just first 2 chars for compactness)
    code_legend = []
    seen = set()
    for d in top30_divs:
        code = d[:2]
        if code not in seen:
            code_legend.append(f"{code}={d}")
            seen.add(code)
    # 2-char codes may collide; use abbreviated table instead
    lines.append("Date         " + "".join((d[:2]).ljust(2) for d in top30_divs))
    for d in fires_pivot.index:
        line = d.strftime("%Y-%m-%d") + "  "
        for col in top30_divs:
            f = int(fires_pivot.loc[d, col])
            c = int(caught_pivot.loc[d, col])
            rate = (c / f) if f > 0 else None
            line += heat_char(rate, f) + " "
        line = line.rstrip()
        # Append totals
        total_f = int(fires_pivot.loc[d].sum())
        total_c = int(caught_pivot.loc[d].sum())
        line += f"  | {total_f}f / {total_c}c"
        lines.append(line)
    lines.append("```")
    lines.append("")
    lines.append("### Top-30 division code legend (2-char prefix may collide)")
    lines.append("")
    legend_rows = []
    for i, d in enumerate(top30_divs):
        legend_rows.append({"i": i + 1, "code": d[:2], "division": d,
                            "season_fires": int(perdiv[perdiv["division"] == d]["total_fires"].iloc[0]),
                            "season_recall": fmt_pct(perdiv[perdiv["division"] == d]["recall"].iloc[0])})
    lines.extend(md_table(legend_rows, ["i", "code", "division", "season_fires", "season_recall"]))
    lines.append("")

    # ============================================================
    # Section 4 — Worst 5 days drill-down
    # ============================================================
    lines.append("## 4. Worst 5 days drill-down (most uncovered fires)\n")
    worst_days = daily.nlargest(5, "uncovered")["date"].tolist()
    for d in worst_days:
        d_str = d.strftime("%Y-%m-%d")
        day_df = df[(df["date"] == d) & (df["n_fires_observed"] > 0)].sort_values(
            "n_fires_observed", ascending=False
        )
        total_f = int(day_df["n_fires_observed"].sum())
        total_c = int(day_df["n_fires_caught"].sum())
        recall = total_c / total_f if total_f else 0
        lines.append(f"### {d_str} — {total_f} fires across {len(day_df)} divs, "
                     f"caught {total_c} ({recall*100:.1f}%)")
        lines.append("")
        rows = []
        for _, r in day_df.head(20).iterrows():
            rows.append({
                "division": r["division"],
                "fires": int(r["n_fires_observed"]),
                "caught": int(r["n_fires_caught"]),
                "recall": fmt_pct(r["catch_rate"]) if r["n_fires_observed"] > 0 else "—",
                "alerts": int(r["n_alerts_total"]),
                "CRIT": int(r["n_critical_organic"]),
                "FLOOR": int(r["n_critical_floor"]),
            })
        lines.extend(md_table(rows, ["division", "fires", "caught", "recall",
                                      "alerts", "CRIT", "FLOOR"]))
        if len(day_df) > 20:
            lines.append(f"\n_... {len(day_df) - 20} more divisions; see full row in `2026_per_division_per_day.csv`_")
        lines.append("")

    # ============================================================
    # Section 5 — Best 5 days drill-down
    # ============================================================
    lines.append("## 5. Best 5 days drill-down (highest recall, ≥20 fires)\n")
    eligible = daily[daily["total_fires"] >= 20]
    best_days = eligible.nlargest(5, "day_recall")["date"].tolist()
    for d in best_days:
        d_str = d.strftime("%Y-%m-%d")
        day_df = df[(df["date"] == d) & (df["n_fires_observed"] > 0)].sort_values(
            "n_fires_observed", ascending=False
        )
        total_f = int(day_df["n_fires_observed"].sum())
        total_c = int(day_df["n_fires_caught"].sum())
        recall = total_c / total_f if total_f else 0
        lines.append(f"### {d_str} — {total_f} fires across {len(day_df)} divs, "
                     f"caught {total_c} ({recall*100:.1f}%)")
        lines.append("")
        rows = []
        for _, r in day_df.head(20).iterrows():
            rows.append({
                "division": r["division"],
                "fires": int(r["n_fires_observed"]),
                "caught": int(r["n_fires_caught"]),
                "recall": fmt_pct(r["catch_rate"]) if r["n_fires_observed"] > 0 else "—",
                "alerts": int(r["n_alerts_total"]),
                "CRIT": int(r["n_critical_organic"]),
                "FLOOR": int(r["n_critical_floor"]),
            })
        lines.extend(md_table(rows, ["division", "fires", "caught", "recall",
                                      "alerts", "CRIT", "FLOOR"]))
        lines.append("")

    # ============================================================
    # Section 6 — Per-division timeline for top-10 fire divisions
    # ============================================================
    lines.append("## 6. Per-division daily timeline — top 10 fire divisions\n")
    top10_divs = perdiv.head(10)["division"].tolist()
    for div in top10_divs:
        div_df = df[df["division"] == div].sort_values("date")
        season = perdiv[perdiv["division"] == div].iloc[0]
        lines.append(f"### {div}  —  {int(season['total_fires'])} fires across "
                     f"{int(season['days_with_fires'])} active days, "
                     f"recall = {fmt_pct(season['recall'])}")
        lines.append("")
        rows = []
        for _, r in div_df.iterrows():
            if r["n_fires_observed"] == 0 and r["n_alerts_total"] == 0:
                continue  # skip pure-empty days
            rows.append({
                "date": r["date"].strftime("%Y-%m-%d"),
                "fires": int(r["n_fires_observed"]),
                "caught": int(r["n_fires_caught"]),
                "recall": fmt_pct(r["catch_rate"]) if r["n_fires_observed"] > 0 else "—",
                "alerts": int(r["n_alerts_total"]),
                "CRIT": int(r["n_critical_organic"]),
                "FLOOR": int(r["n_critical_floor"]),
            })
        lines.extend(md_table(rows, ["date", "fires", "caught", "recall",
                                      "alerts", "CRIT", "FLOOR"]))
        lines.append("")

    # ============================================================
    # Pivot CSV — full date × division recall matrix
    # ============================================================
    pivot_recall = df.pivot_table(
        index="date", columns="division",
        values="catch_rate", aggfunc="mean",
    )
    pivot_recall.to_csv(DST_PIVOT)

    DST_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {DST_MD.relative_to(ROOT)}")
    print(f"  Lines: {len(lines):,}")
    print(f"  Sections: 6 (timeline / per-div / heatmap / worst5 / best5 / top10-timelines)")
    print(f"\nWrote {DST_PIVOT.relative_to(ROOT)}")
    print(f"  Pivot: 66 dates (rows) × {len(pivot_recall.columns)} divisions (cols), values=catch_rate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
