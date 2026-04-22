"""Decorate v17 raw predictions with operational metadata for forest staff.

Takes raw `outputs/dashboard_feed/ignition_risk_v17.json` and enriches each
banded alert with:
  - trust_level: HIGH / MEDIUM / COLD_START (confidence calibration)
  - is_cold_start: bool (new outbreak risk = low-Hawkes + top-rank)
  - action: DISPATCH / PATROL / AWARENESS
  - action_text: plain-language instruction for beat guard
  - weather_escalation: extreme-fire-weather day flag
  - calendar_hint: festival / seasonal note if applicable
  - budget_tier: final deliverable tier after statewide / DFO / beat caps

Outputs:
  outputs/dashboard_feed/operational_alerts_v17.json
  outputs/dashboard_feed/division_briefings.json (per-division digest)

Design principles:
  - Pure function from (v17 json, fwi parquet, calendar, alerts history) -> json
  - No model inference; decoration layer only
  - Idempotent: running twice produces identical output
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V17_JSON = ROOT / "outputs" / "dashboard_feed" / "ignition_risk_v17.json"
FWI_PARQUET = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
CELLS_CSV = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_ALERTS = ROOT / "outputs" / "dashboard_feed" / "operational_alerts_v17.json"
OUT_BRIEFINGS = ROOT / "outputs" / "dashboard_feed" / "division_briefings.json"

# Budget caps (from validation analysis)
STATEWIDE_CRITICAL_CAP = 130
PER_DIVISION_CRITICAL_CAP = 5
PER_BEAT_CRITICAL_CAP = 2
PER_BEAT_ALERT_CAP = 3

# Coverage floor — guarantee each division sees at least 1 CRITICAL each day,
# 2 during extreme weather, so no officer concludes "no risk today" falsely
# because v17's Hawkes-dominated ranking concentrated on 10 hotspot divisions.
# Floor-promoted alerts carry a distinct trust tier (DIVISION_FLOOR) so the
# portal styles them differently from statewide-top CRITICALs.
PER_DIVISION_CRITICAL_FLOOR = 1
PER_DIVISION_CRITICAL_FLOOR_EXTREME = 2

# Trust calibration thresholds (from v17 per-division validation)
HIGH_TRUST_HAWKES_N = 3   # fires nearby past 7d
COLD_START_HAWKES_N = 1   # less-than-or-equal is cold-start

# Weather escalation thresholds (fire weather science)
EXTREME_FFMC = 92.0
EXTREME_RH_PCT = 25.0
EXTREME_WIND_KMH = 15.0

# Festival calendar (from scripts/build_calendar_features.py)
HOLI_DATES: dict[int, date] = {
    2024: date(2024, 3, 25), 2025: date(2025, 3, 14), 2026: date(2026, 3, 4),
    2027: date(2027, 3, 22),
}
AKSHAYA_TRITIYA: dict[int, date] = {
    2024: date(2024, 5, 10), 2025: date(2025, 4, 30), 2026: date(2026, 4, 19),
    2027: date(2027, 5, 9),
}
BHAGORIA_START = {year: date(year, 3, 1) for year in range(2024, 2028)}
BHAGORIA_END = {year: date(year, 3, 15) for year in range(2024, 2028)}
MAHUA_COLLECTION_START = {year: date(year, 3, 10) for year in range(2024, 2028)}
MAHUA_COLLECTION_END = {year: date(year, 5, 10) for year in range(2024, 2028)}
TENDU_WINDOW_START = {year: date(year, 2, 15) for year in range(2024, 2028)}
TENDU_WINDOW_END = {year: date(year, 4, 15) for year in range(2024, 2028)}


@dataclass(frozen=True)
class WeatherContext:
    date: str
    ffmc: float
    rh_pct: float
    wind_kmh: float
    temp_c: float
    fwi: float
    danger_class: str
    is_extreme: bool

    def banner(self) -> str | None:
        if not self.is_extreme:
            return None
        return (
            f"EXTREME FIRE WEATHER: FFMC {self.ffmc:.0f} RH {self.rh_pct:.0f}% "
            f"wind {self.wind_kmh:.0f} km/h ({self.danger_class}). "
            "All divisions: heightened patrols. Cold-start alerts may undercount."
        )


@dataclass(frozen=True)
class CalendarContext:
    target_date: str
    events: tuple[str, ...]
    notes: tuple[str, ...]

    def banner(self) -> str | None:
        if not self.events:
            return None
        return (
            f"CALENDAR FLAGS: {', '.join(self.events)}. "
            f"{' '.join(self.notes)}"
        )


def load_weather_context(target: date) -> WeatherContext:
    if not FWI_PARQUET.exists():
        return WeatherContext(str(target), 0, 100, 0, 0, 0, "Unknown", False)
    fwi = pd.read_parquet(FWI_PARQUET)
    fwi["date"] = pd.to_datetime(fwi["date"]).dt.date
    match = fwi[fwi["date"] == target]
    if match.empty:
        match = fwi[fwi["date"] <= target].tail(1)
    if match.empty:
        return WeatherContext(str(target), 0, 100, 0, 0, 0, "Unknown", False)
    row = match.iloc[0]
    danger = str(row["danger_class"]).strip()
    is_extreme = danger in ("Extreme", "Very High") or (
        float(row["ffmc"]) >= EXTREME_FFMC
        and float(row["rh_pct"]) <= EXTREME_RH_PCT
    )
    return WeatherContext(
        date=str(row["date"]),
        ffmc=float(row["ffmc"]),
        rh_pct=float(row["rh_pct"]),
        wind_kmh=float(row["wind_kmh"]),
        temp_c=float(row["temp_c"]),
        fwi=float(row["fwi"]),
        danger_class=str(row["danger_class"]),
        is_extreme=bool(is_extreme),
    )


def load_calendar_context(target: date) -> CalendarContext:
    events: list[str] = []
    notes: list[str] = []
    year = target.year

    holi = HOLI_DATES.get(year)
    if holi and abs((target - holi).days) <= 3:
        events.append("Holi week")
        notes.append(
            "Ritual bonfires common; pre-position staff near tribal villages."
        )

    akshaya = AKSHAYA_TRITIYA.get(year)
    if akshaya and abs((target - akshaya).days) <= 2:
        events.append("Akshaya Tritiya")
        notes.append(
            "Anthropogenic land-clearing fires spike; brief NGO/VFPC liaisons."
        )

    if year in BHAGORIA_START and BHAGORIA_START[year] <= target <= BHAGORIA_END[year]:
        events.append("Bhagoria period")
        notes.append("Jhabua/Alirajpur tribal market season — higher forest traffic.")

    if year in MAHUA_COLLECTION_START and MAHUA_COLLECTION_START[year] <= target <= MAHUA_COLLECTION_END[year]:
        events.append("Mahua collection window")
        notes.append(
            "Understory fires at tree bases (to aid flower collection) are common."
        )

    if year in TENDU_WINDOW_START and TENDU_WINDOW_START[year] <= target <= TENDU_WINDOW_END[year]:
        events.append("Tendu fire window")
        notes.append("Leaf-litter clearing fires ahead of tendu collection.")

    return CalendarContext(str(target), tuple(events), tuple(notes))


def load_cell_metadata() -> dict[str, dict[str, str]]:
    """Load per-cell division/range/beat + centroid lat/lon.

    lat/lon are needed when the coverage floor promotes a cell from
    alerts_all_cells — those records only carry cell_id+ignition_risk,
    so the decorated alert would render at NaN coordinates without this
    lookup.
    """
    if not CELLS_CSV.exists():
        return {}
    cells = pd.read_csv(CELLS_CSV)
    needed = [c for c in ("division", "range", "beat") if c in cells.columns]
    lat_col = next((c for c in ("centroid_lat", "lat", "latitude") if c in cells.columns), None)
    lon_col = next((c for c in ("centroid_lon", "lon", "longitude") if c in cells.columns), None)
    out: dict[str, dict[str, str]] = {}
    for _, r in cells.iterrows():
        meta = {k: str(r[k]) if k in r else "" for k in needed}
        if lat_col is not None:
            meta["lat"] = float(r[lat_col])
        if lon_col is not None:
            meta["lon"] = float(r[lon_col])
        out[str(r["cell_id"])] = meta
    return out


def calibrate_trust(rank: float, hawkes_n: int) -> tuple[str, bool]:
    """Returns (trust_level, is_cold_start).

    - HIGH: top 1% rank AND hawkes_n >= 3 (validated 30-58% precision)
    - MEDIUM: top 5% rank, mid-Hawkes (validated ~15% precision)
    - COLD_START: top 1% rank BUT hawkes_n <= 1 (new outbreak; ~6% precision)
    """
    if rank >= 0.99 and hawkes_n <= COLD_START_HAWKES_N:
        return "COLD_START", True
    if rank >= 0.99 and hawkes_n >= HIGH_TRUST_HAWKES_N:
        return "HIGH", False
    if rank >= 0.95:
        return "MEDIUM", False
    return "LOW", False


def classify_action(band: str, trust: str, weather_extreme: bool) -> tuple[str, str]:
    """Returns (action_code, plain_language_instruction)."""
    if band == "CRITICAL" and trust == "HIGH":
        return "DISPATCH", (
            "Dispatch 2-person fire-line team to cell GPS within 2 hours. "
            "Active ignition front likely."
        )
    if band == "CRITICAL" and trust == "COLD_START":
        return "VERIFY", (
            "Cold-start alert — drive-by verification before deploying team. "
            "Model uncertain here; confirm via phone with local VFPC first."
        )
    if band == "CRITICAL":
        return "DISPATCH", (
            "Dispatch patrol team to cell GPS within 4 hours. "
            "Review fuel + wind before entry."
        )
    if band == "ALERT":
        if weather_extreme:
            return "DISPATCH", (
                "Extreme weather elevates ALERT to dispatch-equivalent. "
                "Intensify patrol + keep fire-line equipment in vehicle."
            )
        return "PATROL", (
            "Intensify patrols in 3 km radius. Brief VFPC and beat guard."
        )
    return "AWARENESS", (
        "Routine awareness — note in log, no deployment required unless "
        "reports come in from villagers."
    )


def enforce_budget(
    alerts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply statewide / per-division / per-beat caps.

    Order: sort by (band priority, ignition_risk desc), preserve top N per tier.
    Demote excess CRITICAL to ALERT, excess ALERT to WATCH, excess WATCH dropped.
    """
    band_rank = {"CRITICAL": 3, "ALERT": 2, "WATCH": 1}
    sorted_alerts = sorted(
        alerts,
        key=lambda a: (-band_rank.get(a["band"], 0), -a["ignition_risk"]),
    )

    statewide_critical = 0
    per_division_critical: dict[str, int] = {}
    per_beat_critical: dict[tuple[str, str, str], int] = {}
    per_beat_alert: dict[tuple[str, str, str], int] = {}

    result = []
    for alert in sorted_alerts:
        div = alert.get("division", "")
        rng = alert.get("range", "")
        beat = alert.get("beat", "")
        beat_key = (div, rng, beat)
        original_band = alert["band"]
        final_band = original_band

        if original_band == "CRITICAL":
            if (
                statewide_critical >= STATEWIDE_CRITICAL_CAP
                or per_division_critical.get(div, 0) >= PER_DIVISION_CRITICAL_CAP
                or per_beat_critical.get(beat_key, 0) >= PER_BEAT_CRITICAL_CAP
            ):
                final_band = "ALERT"
            else:
                statewide_critical += 1
                per_division_critical[div] = per_division_critical.get(div, 0) + 1
                per_beat_critical[beat_key] = per_beat_critical.get(beat_key, 0) + 1

        if final_band == "ALERT":
            if per_beat_alert.get(beat_key, 0) >= PER_BEAT_ALERT_CAP:
                final_band = "WATCH"
            else:
                per_beat_alert[beat_key] = per_beat_alert.get(beat_key, 0) + 1

        alert["budget_tier"] = final_band
        alert["budget_demoted"] = final_band != original_band
        alert.setdefault("floor_promoted", False)
        result.append(alert)

    return result


def apply_division_coverage_floor(
    alerts: list[dict[str, Any]],
    all_cells: list[dict[str, Any]],
    cell_meta: dict[str, dict[str, str]],
    weather_extreme: bool,
    calendar_ctx: CalendarContext,
) -> tuple[list[dict[str, Any]], int]:
    """Promote the highest-rank cell in each under-covered division to CRITICAL.

    Runs AFTER enforce_budget. For every MP division that currently has fewer
    than the floor of CRITICAL alerts, pick the top-ranked cell in that division
    from the FULL MP grid (alerts_all_cells, ~42K cells) — including divisions
    with zero banded alerts in the original v17 output — and promote it.

    Tagged with trust_level='DIVISION_FLOOR' and floor_promoted=True so the
    portal shows them as dashed-ring markers — they are lower-confidence than
    a statewide-top CRITICAL but demand visibility so no division falsely
    reads as "safe" during extreme weather.

    Returns (updated_alerts_list, n_promoted). alerts_list may grow if
    divisions with zero banded alerts get a freshly-decorated floor cell.
    """
    floor = PER_DIVISION_CRITICAL_FLOOR_EXTREME if weather_extreme else PER_DIVISION_CRITICAL_FLOOR

    # Tally current CRITICAL per division (banded only)
    crit_per_div: dict[str, int] = {}
    cells_in_alerts: set[str] = set()
    for a in alerts:
        div = a.get("division") or ""
        if not div or div == "Unknown":
            continue
        cells_in_alerts.add(a["cell_id"])
        if a["budget_tier"] == "CRITICAL":
            crit_per_div[div] = crit_per_div.get(div, 0) + 1

    # Group ALL cells by division for floor candidate lookup
    all_by_div: dict[str, list[dict[str, Any]]] = {}
    for c in all_cells:
        meta = cell_meta.get(c["cell_id"], {})
        div = meta.get("division", "")
        if not div:
            continue
        all_by_div.setdefault(div, []).append(c)

    n_promoted = 0
    for div, div_cells in all_by_div.items():
        current = crit_per_div.get(div, 0)
        if current >= floor:
            continue
        need = floor - current
        # Highest-rank candidates in this division (full grid)
        candidates = sorted(div_cells, key=lambda c: -c.get("rank", 0))
        promoted_for_this_div = 0
        for c in candidates:
            if promoted_for_this_div >= need:
                break
            cid = c["cell_id"]
            # Already-banded cell in this division? Promote in-place.
            existing = next(
                (a for a in alerts
                 if a["cell_id"] == cid and a.get("budget_tier") != "CRITICAL"),
                None,
            )
            if existing is not None:
                existing["budget_tier"] = "CRITICAL"
                existing["floor_promoted"] = True
                existing["trust_level"] = "DIVISION_FLOOR"
                existing["action"] = "VERIFY"
                existing["action_text"] = _floor_action_text(div)
            elif cid not in cells_in_alerts:
                # New floor cell — decorate from scratch. alerts_all_cells
                # records only carry {cell_id, ignition_risk}, so we pull
                # lat/lon from cell_meta (loaded from cells.csv centroid_*).
                meta = cell_meta.get(cid, {})
                trust, is_cold = calibrate_trust(
                    c.get("rank", 0), c.get("hawkes_n_recent_10km_7d", 0)
                )
                new_alert = {
                    **c,
                    "lat": meta.get("lat", c.get("lat")),
                    "lon": meta.get("lon", c.get("lon")),
                    "band": "CRITICAL",
                    "division": meta.get("division", div),
                    "range": meta.get("range", ""),
                    "beat": meta.get("beat", ""),
                    "trust_level": "DIVISION_FLOOR",
                    "is_cold_start": is_cold,
                    "action": "VERIFY",
                    "action_text": _floor_action_text(div),
                    "weather_escalated": weather_extreme,
                    "calendar_flags": list(calendar_ctx.events),
                    "budget_tier": "CRITICAL",
                    "budget_demoted": False,
                    "floor_promoted": True,
                }
                alerts.append(new_alert)
                cells_in_alerts.add(cid)
            else:
                continue
            promoted_for_this_div += 1
            n_promoted += 1

    return alerts, n_promoted


def _floor_action_text(division: str) -> str:
    return (
        f"Division-coverage floor: highest-rank cell in {division} promoted "
        "to CRITICAL because the division would otherwise have zero alerts "
        "during high-risk conditions. Verify manually before deploying — "
        "treat as cold-start."
    )


def build_division_briefings(
    alerts: list[dict[str, Any]],
    weather: WeatherContext,
    calendar_ctx: CalendarContext,
) -> dict[str, Any]:
    by_division: dict[str, list[dict[str, Any]]] = {}
    for a in alerts:
        div = a.get("division", "Unknown")
        by_division.setdefault(div, []).append(a)

    briefings = []
    for division, div_alerts in sorted(
        by_division.items(), key=lambda kv: -len(kv[1])
    ):
        critical = [a for a in div_alerts if a["budget_tier"] == "CRITICAL"]
        alert_tier = [a for a in div_alerts if a["budget_tier"] == "ALERT"]
        cold_start = [a for a in div_alerts if a.get("is_cold_start")]
        floor_promoted = [a for a in div_alerts if a.get("floor_promoted")]
        organic_critical = [a for a in critical if not a.get("floor_promoted")]

        # Silent-in-danger: this division has NO model-organic alerts (no
        # CRITICAL before the coverage floor AND no ALERT tier) during
        # extreme weather — the floor just lit up the least-bad cell so
        # the operator sees SOMETHING, but the model is not confident here.
        silent_in_danger = (
            weather.is_extreme
            and len(organic_critical) == 0
            and len(alert_tier) == 0
        )

        briefings.append({
            "division": division,
            "n_critical": len(critical),
            "n_critical_organic": len(organic_critical),
            "n_critical_floor_promoted": len(floor_promoted),
            "n_alert": len(alert_tier),
            "n_cold_start": len(cold_start),
            "silent_in_danger": silent_in_danger,
            "high_trust_hits": [
                {"cell_id": a["cell_id"], "beat": a.get("beat", ""),
                 "risk": a["ignition_risk"], "action": a["action"]}
                for a in critical if a.get("trust_level") == "HIGH"
            ][:5],
            "cold_start_watchlist": [
                {"cell_id": a["cell_id"], "beat": a.get("beat", ""),
                 "risk": a["ignition_risk"]}
                for a in cold_start
            ][:5],
            "weather_banner": weather.banner(),
            "calendar_banner": calendar_ctx.banner(),
        })

    return {
        "generated_at": datetime.now().isoformat(),
        "n_divisions_with_alerts": len(briefings),
        "statewide_weather": asdict(weather),
        "statewide_calendar": asdict(calendar_ctx),
        "briefings": briefings,
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-v17", default=str(V17_JSON),
                    help="Path to raw v17 predictions JSON (default: production feed)")
    ap.add_argument("--output-alerts", default=str(OUT_ALERTS),
                    help="Path to write operational_alerts JSON (default: production feed)")
    ap.add_argument("--output-briefings", default=str(OUT_BRIEFINGS),
                    help="Path to write division_briefings JSON (default: production feed)")
    args = ap.parse_args()
    in_v17 = Path(args.input_v17)
    out_alerts = Path(args.output_alerts)
    out_briefings = Path(args.output_briefings)

    if not in_v17.exists():
        log.error("v17 json not found: %s", in_v17)
        log.error("Run `python scripts/predict_ignition_v17.py` first.")
        return 1

    log.info("Loading v17 raw predictions from %s...", in_v17)
    raw = json.loads(in_v17.read_text())
    banded_alerts = raw.get("banded_alerts", [])
    all_cells = raw.get("alerts_all_cells", [])
    if not banded_alerts:
        log.warning("No banded alerts in v17 JSON; nothing to decorate.")
        return 0

    target = datetime.fromisoformat(raw["prediction_date"]).date()
    log.info("Prediction date: %s (%d raw banded alerts)", target, len(banded_alerts))

    weather = load_weather_context(target)
    calendar_ctx = load_calendar_context(target)
    cell_meta = load_cell_metadata()

    log.info("Weather: FFMC=%.1f RH=%.0f%% wind=%.0f km/h (%s) extreme=%s",
             weather.ffmc, weather.rh_pct, weather.wind_kmh,
             weather.danger_class, weather.is_extreme)
    if calendar_ctx.events:
        log.info("Calendar flags: %s", ", ".join(calendar_ctx.events))
    else:
        log.info("Calendar: no festival/season flags today")

    decorated: list[dict[str, Any]] = []
    for a in banded_alerts:
        trust, is_cold = calibrate_trust(a["rank"], a["hawkes_n_recent_10km_7d"])
        action_code, action_text = classify_action(a["band"], trust, weather.is_extreme)
        meta = cell_meta.get(a["cell_id"], {})
        decorated.append({
            **a,
            "division": meta.get("division", ""),
            "range": meta.get("range", ""),
            "beat": meta.get("beat", ""),
            "trust_level": trust,
            "is_cold_start": is_cold,
            "action": action_code,
            "action_text": action_text,
            "weather_escalated": weather.is_extreme and a["band"] in ("WATCH", "ALERT"),
            "calendar_flags": list(calendar_ctx.events),
        })

    log.info("Enforcing budget caps...")
    final_alerts = enforce_budget(decorated)
    n_crit_raw = sum(1 for a in final_alerts if a["budget_tier"] == "CRITICAL")
    n_demoted = sum(1 for a in final_alerts if a["budget_demoted"])
    log.info("Budget enforcement: CRITICAL=%d (cap %d) demoted=%d",
             n_crit_raw, STATEWIDE_CRITICAL_CAP, n_demoted)

    log.info("Applying per-division coverage floor (extreme=%s floor=%d/%d)...",
             weather.is_extreme,
             PER_DIVISION_CRITICAL_FLOOR,
             PER_DIVISION_CRITICAL_FLOOR_EXTREME)
    final_alerts, n_floor = apply_division_coverage_floor(
        final_alerts, all_cells, cell_meta, weather.is_extreme, calendar_ctx,
    )
    log.info("Coverage floor: promoted %d cells to CRITICAL (DIVISION_FLOOR trust)", n_floor)

    n_crit = sum(1 for a in final_alerts if a["budget_tier"] == "CRITICAL")
    n_alert = sum(1 for a in final_alerts if a["budget_tier"] == "ALERT")
    n_watch = sum(1 for a in final_alerts if a["budget_tier"] == "WATCH")
    n_high_trust = sum(1 for a in final_alerts if a["trust_level"] == "HIGH")
    n_medium = sum(1 for a in final_alerts if a["trust_level"] == "MEDIUM")
    n_cold_start = sum(1 for a in final_alerts if a["is_cold_start"])
    n_floor_tier = sum(1 for a in final_alerts if a.get("floor_promoted"))
    log.info("Final: CRITICAL=%d (base=%d floor=%d) ALERT=%d WATCH=%d",
             n_crit, n_crit_raw, n_floor_tier, n_alert, n_watch)
    log.info("Trust tiers: HIGH=%d MEDIUM=%d COLD_START=%d DIVISION_FLOOR=%d",
             n_high_trust, n_medium, n_cold_start, n_floor_tier)

    output = {
        "model": raw.get("model", "v17_ba_pu"),
        "prediction_date": raw["prediction_date"],
        "generated_at": datetime.now().isoformat(),
        "counts": {
            "raw_banded": len(banded_alerts),
            "final_critical": n_crit,
            "final_alert": n_alert,
            "final_watch": n_watch,
            "budget_demoted": n_demoted,
            "high_trust": n_high_trust,
            "medium_trust": n_medium,
            "cold_start": n_cold_start,
            "division_floor_promoted": n_floor_tier,
            "critical_base": n_crit_raw,
        },
        "weather_context": asdict(weather),
        "calendar_context": asdict(calendar_ctx),
        "budget_caps": {
            "statewide_critical": STATEWIDE_CRITICAL_CAP,
            "per_division_critical": PER_DIVISION_CRITICAL_CAP,
            "per_beat_critical": PER_BEAT_CRITICAL_CAP,
            "per_beat_alert": PER_BEAT_ALERT_CAP,
        },
        "alerts": final_alerts,
    }

    out_alerts.parent.mkdir(parents=True, exist_ok=True)
    out_alerts.write_text(json.dumps(output, indent=2, default=str))
    try:
        log.info("Wrote: %s", out_alerts.relative_to(ROOT))
    except ValueError:
        log.info("Wrote: %s", out_alerts)

    briefings = build_division_briefings(final_alerts, weather, calendar_ctx)
    out_briefings.write_text(json.dumps(briefings, indent=2, default=str))
    try:
        log.info("Wrote: %s (%d divisions)",
                 out_briefings.relative_to(ROOT),
                 briefings["n_divisions_with_alerts"])
    except ValueError:
        log.info("Wrote: %s (%d divisions)",
                 out_briefings, briefings["n_divisions_with_alerts"])

    log.info("Sample top-5 CRITICAL with HIGH trust:")
    high_crit = [a for a in final_alerts
                 if a["budget_tier"] == "CRITICAL" and a["trust_level"] == "HIGH"]
    for a in high_crit[:5]:
        log.info("  %s [%s/%s] risk=%.3f rank=%.3f hawkes_n=%d -> %s",
                 a["cell_id"], a.get("division", "?"), a.get("beat", "?"),
                 a["ignition_risk"], a["rank"],
                 a["hawkes_n_recent_10km_7d"], a["action"])

    if n_cold_start > 0:
        log.info("Sample cold-start watchlist (verify before acting):")
        for a in final_alerts:
            if a["is_cold_start"]:
                log.info("  %s [%s/%s] risk=%.3f rank=%.3f hawkes_n=%d -> %s",
                         a["cell_id"], a.get("division", "?"), a.get("beat", "?"),
                         a["ignition_risk"], a["rank"],
                         a["hawkes_n_recent_10km_7d"], a["action"])
                if final_alerts.index(a) > 5:
                    break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
