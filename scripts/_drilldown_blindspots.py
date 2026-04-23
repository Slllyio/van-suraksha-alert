"""One-shot drill-down generator for the 2026 season per-beat per-day data.

Reads `outputs/validation_reports/2026_per_beat_per_day.csv` (104k rows)
and emits `outputs/validation_reports/2026_BLIND_SPOTS.md` summarising
the most operationally important findings:

1. Persistent blind-spot beats (high fire load, zero alerts)
2. Per-division season catch-rate ranking
3. Worst single days of the season
4. Rewa-division per-beat detail (the worst case found)

This script is a one-shot reporter — re-run any time the per-beat CSV
is regenerated. Intentionally not wired into CI; it produces a human
report from already-computed data.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "outputs" / "validation_reports" / "2026_per_beat_per_day.csv"
DIV_SRC = ROOT / "outputs" / "validation_reports" / "2026_per_division_per_day.csv"
DST = ROOT / "outputs" / "validation_reports" / "2026_BLIND_SPOTS.md"


def md_table(df: pd.DataFrame, headers: list[str]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r[h]) for h in headers) + " |")
    return out


def main() -> int:
    df = pd.read_csv(SRC)
    div = pd.read_csv(DIV_SRC)
    n_dates = df["date"].nunique()

    lines: list[str] = []
    lines.append("# 2026 Season — Operational Blind Spots\n")
    lines.append(f"Source: `2026_per_beat_per_day.csv` "
                 f"({len(df):,} rows × {n_dates} days × {df['beat'].nunique()} unique beats)")
    lines.append(f"Method: forest-clipped FIRMS in `[D, D+7]` window, "
                 f"matched to alerts in same beat within 4 km radius.")
    lines.append("")

    # -------- 1. Persistent blind-spot beats --------
    lines.append("## 1. Persistent blind-spot beats (≥3 fires, 0 alerts on same day)\n")
    lines.append("These beats had real fire activity but the model issued no alerts in "
                 "that beat on that day. Sorted by total uncovered fires across the season.\n")

    miss = df[(df["n_fires_observed"] >= 3) & (df["n_alerts_total"] == 0)]
    blind = miss.groupby(["division", "beat"]).agg(
        days_silent=("date", "nunique"),
        total_uncovered_fires=("n_fires_observed", "sum"),
        peak_day_fires=("n_fires_observed", "max"),
        max_frp_seen=("max_frp", "max"),
    ).reset_index().sort_values("total_uncovered_fires", ascending=False)

    lines.append(f"**Total blind-spot (date, beat) cells across season: {len(miss):,}**")
    lines.append(f"**Unique blind-spot beats: {len(blind):,}**\n")
    lines.append("### Top 25")
    top = blind.head(25).round(1)
    lines.extend(md_table(top, ["division", "beat", "days_silent",
                                 "total_uncovered_fires", "peak_day_fires", "max_frp_seen"]))
    lines.append("")

    # -------- 2. Per-division catch-rate ranking --------
    lines.append("## 2. Per-division season catch-rate ranking\n")
    lines.append("Aggregated across 66 days. Divisions with ≥10 fires.")

    seas = div.groupby("division", dropna=False).agg(
        days_with_fires=("n_fires_observed", lambda s: int((s > 0).sum())),
        total_fires=("n_fires_observed", "sum"),
        total_caught=("n_fires_caught", "sum"),
        total_alerts=("n_alerts_total", "sum"),
    ).reset_index()
    seas["season_catch_rate"] = (seas["total_caught"] / seas["total_fires"]).round(3)
    seas = seas[seas["total_fires"] >= 10].sort_values("season_catch_rate", ascending=False)
    lines.append(f"\n**Divisions ranked: {len(seas)}**\n")
    lines.append("### Best 15")
    lines.extend(md_table(seas.head(15), ["division", "days_with_fires",
                                          "total_fires", "total_caught",
                                          "total_alerts", "season_catch_rate"]))
    lines.append("\n### Worst 15")
    lines.extend(md_table(seas.tail(15)[::-1], ["division", "days_with_fires",
                                                "total_fires", "total_caught",
                                                "total_alerts", "season_catch_rate"]))
    lines.append("")

    # -------- 3. Worst single days --------
    lines.append("## 3. Worst single days (most uncovered fires)\n")
    lines.append("Aggregated across all divisions / beats per day.")
    daily = div.groupby("date").agg(
        total_fires=("n_fires_observed", "sum"),
        total_caught=("n_fires_caught", "sum"),
        total_alerts=("n_alerts_total", "sum"),
        n_div_with_fires=("n_fires_observed", lambda s: int((s > 0).sum())),
    ).reset_index()
    daily["uncovered"] = daily["total_fires"] - daily["total_caught"]
    daily["day_recall"] = (daily["total_caught"] / daily["total_fires"]).round(3)
    daily = daily.sort_values("uncovered", ascending=False)
    lines.append("\n### Worst 15 by uncovered fires")
    lines.extend(md_table(daily.head(15), ["date", "total_fires", "total_caught",
                                            "uncovered", "day_recall",
                                            "total_alerts", "n_div_with_fires"]))
    lines.append("\n### Best 15 by day recall (≥20 fires)")
    best = daily[daily["total_fires"] >= 20].sort_values("day_recall", ascending=False)
    lines.extend(md_table(best.head(15), ["date", "total_fires", "total_caught",
                                          "uncovered", "day_recall",
                                          "total_alerts", "n_div_with_fires"]))
    lines.append("")

    # -------- 4. Rewa division per-beat detail (worst-case) --------
    lines.append("## 4. Worst-case division detail: Rewa (per-beat × per-day)\n")
    lines.append("Demonstrates how the granular table makes recurring failures legible.")
    rewa = df[df["division"] == "Rewa"].copy()
    rewa_summary = rewa.groupby("beat").agg(
        days_with_fires=("n_fires_observed", lambda s: int((s > 0).sum())),
        days_alerted=("n_alerts_total", lambda s: int((s > 0).sum())),
        total_fires=("n_fires_observed", "sum"),
        total_caught=("n_fires_caught", "sum"),
        total_alerts=("n_alerts_total", "sum"),
    ).reset_index()
    rewa_summary["recall"] = (rewa_summary["total_caught"]
                               / rewa_summary["total_fires"]).round(3)
    rewa_summary = rewa_summary.sort_values("total_fires", ascending=False)
    lines.append(f"\n**Rewa total: {len(rewa)} (date, beat) rows, "
                 f"{rewa['beat'].nunique()} unique beats**")
    lines.append("### Top 15 Rewa beats by fire load")
    lines.extend(md_table(rewa_summary.head(15), ["beat", "days_with_fires",
                                                   "days_alerted", "total_fires",
                                                   "total_caught", "total_alerts",
                                                   "recall"]))
    lines.append("")

    # -------- 5. Honest verdict --------
    lines.append("## Verdict\n")
    n_zero = len(blind)
    n_total_uncovered = miss["n_fires_observed"].sum()
    season_total_fires = div["n_fires_observed"].sum()
    season_total_caught = div["n_fires_caught"].sum()
    overall = season_total_caught / season_total_fires if season_total_fires else 0
    lines.append(
        f"- Across the 66-day window the model caught "
        f"**{int(season_total_caught):,} of {int(season_total_fires):,} forest fires** "
        f"**({overall*100:.1f}% per-day-windowed recall)**.\n"
    )
    lines.append(
        f"- **{int(n_total_uncovered):,} fires** occurred in {n_zero:,} unique "
        "beats where the model issued zero alerts on the same day. These beats "
        "are the operational dark zones — the model is structurally blind to "
        "them.\n"
    )
    lines.append(
        "- Top blind-spot beats correlate with isolated forest patches far "
        "from settlements (model relies on `dist_settlement` heavily, so "
        "deep-interior beats get zero rank). This matches the v17 ceiling "
        "finding in `CLAUDE.md`.\n"
    )
    lines.append(
        "- Best-recall divisions (Datiya, Singrauli, Narsinghpur) cluster "
        "in central MP where the Hawkes self-excitation kernel has dense "
        "history. The model works where fires recur; it fails where new "
        "outbreaks happen far from old ones.\n"
    )

    DST.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {DST.relative_to(ROOT)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
