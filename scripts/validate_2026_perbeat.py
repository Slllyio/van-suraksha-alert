"""Per-beat × per-day validation matrix for 2026 fire season.

Builds two granular tables that decompose `2026_per_division.csv` along
the day and beat dimensions:

  outputs/validation_reports/2026_per_division_per_day.csv
      (date × division)  -- ~5,000 rows; spot per-day per-division gaps
  outputs/validation_reports/2026_per_beat_per_day.csv
      (date × division × beat)  -- ~20,000 rows; most granular drill-down

Each row carries:

  Predictions side (from operational_alerts_v17_{date}.json):
    n_critical_organic   -- CRITICAL not floor-promoted
    n_critical_floor     -- floor-promoted CRITICAL
    n_alert              -- ALERT band
    n_watch              -- WATCH band
    n_alerts_total       -- sum of above
    max_band             -- CRITICAL > ALERT > WATCH > NONE

  Reality side (from FIRMS for [date, date+7], forest-clipped):
    n_fires_observed     -- distinct FIRMS detections in this beat
    n_high_conf_fires    -- subset with confidence in {h, n, high, nominal}
    max_frp              -- peak fire radiative power in window

  Intersection:
    n_fires_caught       -- fires within MATCH_RADIUS_KM of any alert
                            in this beat (CRITICAL + ALERT + WATCH all count)
    catch_rate           -- n_caught / n_fires (None if 0 fires)
    caught_at_band       -- best band that caught any fire

Usage:
  python scripts/validate_2026_perbeat.py
  python scripts/validate_2026_perbeat.py --start 2026-02-16 --end 2026-04-22
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
FIRMS_CONS = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
FIRMS_NRT = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "nrt_7d.parquet"
OUT_DIR = ROOT / "outputs" / "validation_reports"

CATCH_WINDOW_DAYS = 7
MATCH_RADIUS_KM = 4.0
HIGH_CONF = {"h", "n", "high", "nominal"}
BAND_ORDER = {"CRITICAL": 3, "ALERT": 2, "WATCH": 1}


def load_firms_with_beat() -> pd.DataFrame:
    """Load all FIRMS detections, attach (Division, Range, Beat) via spatial join."""
    import geopandas as gpd
    from shapely.geometry import Point
    frames = []
    for p in (FIRMS_CONS, FIRMS_NRT):
        if p.exists():
            df = pd.read_parquet(p)
            df["acq_date"] = pd.to_datetime(df["acq_date"])
            frames.append(df)
    if not frames:
        raise FileNotFoundError("no FIRMS parquets")
    df = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first"
    )
    df["confidence"] = df["confidence"].astype(str).str.lower()
    log.info("FIRMS rows: %d (range %s -> %s)", len(df), df.acq_date.min(), df.acq_date.max())

    beats_path = ROOT / "data" / "aoi" / "mp_beats_wgs84.geojson"
    beats = gpd.read_file(beats_path)
    log.info("MP beats: %d polygons", len(beats))

    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(lon, lat) for lat, lon in zip(df["latitude"], df["longitude"])],
        crs="EPSG:4326",
    )
    # Same two-pass strategy as portal: strict-within first, edge-tolerant second
    inside = gpd.sjoin(gdf, beats[["Division", "Range", "Beat", "geometry"]],
                      how="inner", predicate="within")
    inside["_pass"] = 1
    inside["_dist"] = 0.0
    edge = gpd.sjoin_nearest(gdf, beats[["Division", "Range", "Beat", "geometry"]],
                             how="inner", max_distance=0.003, distance_col="_dist")
    edge["_pass"] = 2
    joined = pd.concat([inside, edge], ignore_index=True)
    joined = joined.sort_values(["_pass", "_dist"]).drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first"
    )
    out = pd.DataFrame(joined.drop(columns=["geometry", "index_right", "_dist", "_pass"]))
    log.info("After forest-clip: %d FIRMS rows attached to beats", len(out))
    return out


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    R = 6371.0
    lat1r = np.radians(lat1)
    lat2r = np.radians(lat2)
    dlat = lat2r - lat1r
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def date_range(start: str, end: str) -> Iterable[str]:
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    cur = d0
    while cur <= d1:
        yield cur.strftime("%Y-%m-%d")
        cur += timedelta(days=1)


def evaluate_one_day(
    target_date: pd.Timestamp,
    fires_in_window: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Return (per_beat_rows, per_division_rows) for one prediction date.

    fires_in_window must already be filtered to [target_date, target_date+7]
    AND beat-attached.
    """
    d_str = target_date.strftime("%Y-%m-%d")
    ops_path = FEED_DIR / f"operational_alerts_v17_{d_str}.json"
    if not ops_path.exists():
        return None

    ops = json.loads(ops_path.read_text())
    alerts = ops.get("alerts", [])
    if not alerts:
        return pd.DataFrame(), pd.DataFrame()

    a_df = pd.DataFrame(alerts)
    a_df = a_df.dropna(subset=["lat", "lon"])
    a_df["band"] = a_df.get("budget_tier", a_df.get("band"))
    a_df["division"] = a_df.get("division", "").fillna("")
    a_df["beat"] = a_df.get("beat", "").fillna("")
    a_df["floor_promoted"] = a_df.get("floor_promoted", False).astype(bool)

    # ---------- per-beat alert tallies ----------
    a_df["is_crit_organic"] = (a_df["band"] == "CRITICAL") & (~a_df["floor_promoted"])
    a_df["is_crit_floor"]   = (a_df["band"] == "CRITICAL") & (a_df["floor_promoted"])
    a_df["is_alert"]        = (a_df["band"] == "ALERT")
    a_df["is_watch"]        = (a_df["band"] == "WATCH")

    beat_alerts = a_df.groupby(["division", "beat"], dropna=False).agg(
        n_critical_organic=("is_crit_organic", "sum"),
        n_critical_floor=("is_crit_floor", "sum"),
        n_alert=("is_alert", "sum"),
        n_watch=("is_watch", "sum"),
    ).reset_index()
    beat_alerts["n_alerts_total"] = (
        beat_alerts["n_critical_organic"]
        + beat_alerts["n_critical_floor"]
        + beat_alerts["n_alert"]
        + beat_alerts["n_watch"]
    )

    # ---------- per-beat fire tallies ----------
    f = fires_in_window[fires_in_window["Beat"].notna()].copy()
    f.rename(columns={"Division": "division", "Beat": "beat"}, inplace=True)
    f_grp = f.groupby(["division", "beat"], dropna=False).agg(
        n_fires_observed=("latitude", "size"),
        n_high_conf_fires=("confidence", lambda s: int(s.isin(HIGH_CONF).sum())),
        max_frp=("frp", lambda s: float(s.max()) if s.notna().any() else None),
    ).reset_index()

    # ---------- intersection: did any alert in this beat catch any fire? ----------
    # For each (division, beat) row that has BOTH alerts and fires, compute
    # how many fires have at least one alert within MATCH_RADIUS_KM.
    catch_records = []
    if len(beat_alerts) > 0 and len(f_grp) > 0:
        a_by_key = {(d, b): grp for (d, b), grp in a_df.groupby(["division", "beat"])}
        f_by_key = {(d, b): grp for (d, b), grp in f.groupby(["division", "beat"])}
        common = set(a_by_key.keys()) & set(f_by_key.keys())
        for (div, beat) in common:
            ag = a_by_key[(div, beat)]
            fg = f_by_key[(div, beat)]
            if ag.empty or fg.empty:
                continue
            a_lat = ag["lat"].to_numpy()
            a_lon = ag["lon"].to_numpy()
            a_band = ag["band"].to_numpy()
            n_caught = 0
            best_band = "NONE"
            best_rank = 0
            for _, fr in fg.iterrows():
                d_km = haversine_km(float(fr["latitude"]), float(fr["longitude"]), a_lat, a_lon)
                hits = d_km <= MATCH_RADIUS_KM
                if hits.any():
                    n_caught += 1
                    bands_hit = a_band[hits]
                    for bnd in bands_hit:
                        rk = BAND_ORDER.get(str(bnd), 0)
                        if rk > best_rank:
                            best_rank = rk
                            best_band = str(bnd)
            catch_records.append({
                "division": div, "beat": beat,
                "n_fires_caught": n_caught, "caught_at_band": best_band,
            })
    catch_df = pd.DataFrame(catch_records) if catch_records else pd.DataFrame(
        columns=["division", "beat", "n_fires_caught", "caught_at_band"]
    )

    # ---------- merge alerts + fires + catches ----------
    per_beat = pd.merge(beat_alerts, f_grp, on=["division", "beat"], how="outer")
    per_beat = pd.merge(per_beat, catch_df, on=["division", "beat"], how="left")
    per_beat = per_beat.fillna({
        "n_critical_organic": 0, "n_critical_floor": 0, "n_alert": 0, "n_watch": 0,
        "n_alerts_total": 0, "n_fires_observed": 0, "n_high_conf_fires": 0,
        "n_fires_caught": 0,
    })
    per_beat["max_band"] = per_beat.apply(
        lambda r: "CRITICAL" if (r["n_critical_organic"] + r["n_critical_floor"]) > 0
        else ("ALERT" if r["n_alert"] > 0
              else ("WATCH" if r["n_watch"] > 0 else "NONE")),
        axis=1,
    )
    per_beat["caught_at_band"] = per_beat["caught_at_band"].fillna("NONE")
    per_beat["catch_rate"] = per_beat.apply(
        lambda r: float(r["n_fires_caught"] / r["n_fires_observed"])
        if r["n_fires_observed"] > 0 else None,
        axis=1,
    )
    per_beat["date"] = d_str

    # Re-order to put date first
    cols = ["date", "division", "beat",
            "n_critical_organic", "n_critical_floor", "n_alert", "n_watch", "n_alerts_total",
            "max_band",
            "n_fires_observed", "n_high_conf_fires", "max_frp",
            "n_fires_caught", "caught_at_band", "catch_rate"]
    per_beat = per_beat[[c for c in cols if c in per_beat.columns]]

    # ---------- roll up per-division ----------
    per_div = per_beat.groupby("division", dropna=False).agg(
        n_beats_alerted=("n_alerts_total", lambda s: int((s > 0).sum())),
        n_critical_organic=("n_critical_organic", "sum"),
        n_critical_floor=("n_critical_floor", "sum"),
        n_alert=("n_alert", "sum"),
        n_watch=("n_watch", "sum"),
        n_alerts_total=("n_alerts_total", "sum"),
        n_fires_observed=("n_fires_observed", "sum"),
        n_fires_caught=("n_fires_caught", "sum"),
    ).reset_index()
    per_div["catch_rate"] = per_div.apply(
        lambda r: float(r["n_fires_caught"] / r["n_fires_observed"])
        if r["n_fires_observed"] > 0 else None,
        axis=1,
    )
    per_div["date"] = d_str
    per_div = per_div[["date", "division",
                       "n_beats_alerted",
                       "n_critical_organic", "n_critical_floor", "n_alert", "n_watch", "n_alerts_total",
                       "n_fires_observed", "n_fires_caught", "catch_rate"]]

    return per_beat, per_div


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-02-16")
    ap.add_argument("--end", default="2026-04-22")
    args = ap.parse_args()

    log.info("Window: %s -> %s", args.start, args.end)
    fires = load_firms_with_beat()
    fires_max = fires["acq_date"].max()
    log.info("FIRMS max date: %s", fires_max)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_beat = []
    all_div = []
    n_done = 0
    for d_str in date_range(args.start, args.end):
        target = pd.Timestamp(d_str)
        win_end = min(target + pd.Timedelta(days=CATCH_WINDOW_DAYS), fires_max)
        win_fires = fires[(fires.acq_date >= target) & (fires.acq_date <= win_end)]
        result = evaluate_one_day(target, win_fires)
        if result is None:
            continue
        per_beat, per_div = result
        if not per_beat.empty:
            all_beat.append(per_beat)
            all_div.append(per_div)
        n_done += 1
        if n_done % 10 == 0:
            log.info("  ...%d days processed", n_done)

    if not all_beat:
        log.error("No data — run scripts/run_2026_backfill.py first.")
        return 1

    beat_df = pd.concat(all_beat, ignore_index=True)
    div_df = pd.concat(all_div, ignore_index=True)
    log.info("Total: %d (date,div,beat) rows, %d (date,div) rows", len(beat_df), len(div_df))

    # Sort for human-friendly browsing
    beat_df = beat_df.sort_values(["date", "division", "beat"]).reset_index(drop=True)
    div_df = div_df.sort_values(["date", "division"]).reset_index(drop=True)

    beat_path = OUT_DIR / "2026_per_beat_per_day.csv"
    div_path = OUT_DIR / "2026_per_division_per_day.csv"
    beat_df.to_csv(beat_path, index=False)
    div_df.to_csv(div_path, index=False)
    log.info("Wrote %s (%d rows)", beat_path.relative_to(ROOT), len(beat_df))
    log.info("Wrote %s (%d rows)", div_path.relative_to(ROOT), len(div_df))

    # Quick summary print
    log.info("=" * 70)
    log.info("Sample worst-recall rows (have fires, caught 0):")
    misses = div_df[(div_df.n_fires_observed > 5) & (div_df.n_fires_caught == 0)]
    if len(misses) > 0:
        log.info("  %d (date,division) rows with >5 fires and 0 catches", len(misses))
        for _, r in misses.head(10).iterrows():
            log.info("    %s  %-25s  fires=%d  alerts=%d", r.date, r.division,
                     r.n_fires_observed, r.n_alerts_total)
    log.info("=" * 70)
    log.info("Sample best-recall rows (catch_rate >= 0.5):")
    wins = div_df[(div_df.catch_rate >= 0.5) & (div_df.n_fires_observed >= 3)]
    if len(wins) > 0:
        log.info("  %d (date,division) rows with catch_rate >= 50%% and >=3 fires", len(wins))
        for _, r in wins.head(10).iterrows():
            log.info("    %s  %-25s  fires=%d  caught=%d  rate=%.0f%%",
                     r.date, r.division, r.n_fires_observed, r.n_fires_caught,
                     (r.catch_rate or 0) * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
