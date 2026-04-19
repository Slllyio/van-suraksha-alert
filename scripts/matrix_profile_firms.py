"""STUMPY matrix profile anomaly detection on daily statewide FRP.

Computes the matrix profile over a 28-day subsequence window across 12 years
of daily FRP history. Flags weeks whose pattern is historically unprecedented
(matrix profile value > p99) as NEW_REGIME.

Output:
  outputs/dashboard_feed/matrix_profile_firms.json
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
FIRMS = ROOT / "data_lake" / "fire_detections" / "firms_mp_viirs" / "firms_mp_consolidated.parquet"
OUT = ROOT / "outputs" / "dashboard_feed" / "matrix_profile_firms.json"

SUBSEQ_LEN = 28   # 4-week pattern window
TOP_K_ANOMALIES = 10
TOP_K_MOTIFS = 5


def main() -> int:
    import stumpy

    if not FIRMS.exists():
        log.error("FIRMS missing: %s", FIRMS); return 1

    log.info("Loading FIRMS daily...")
    f = pd.read_parquet(FIRMS, columns=["acq_date", "frp", "confidence"])
    f["acq_date"] = pd.to_datetime(f["acq_date"])
    f = f[f["confidence"].isin(["n", "h", "nominal", "high"])]
    daily = f.groupby("acq_date").agg(
        frp_sum=("frp", "sum"),
        n_detect=("frp", "count"),
    ).reset_index().sort_values("acq_date").reset_index(drop=True)
    # Fill gaps
    full_range = pd.date_range(daily["acq_date"].min(), daily["acq_date"].max(), freq="D")
    daily = daily.set_index("acq_date").reindex(full_range, fill_value=0)
    daily["acq_date"] = daily.index
    daily = daily.reset_index(drop=True)
    log.info("  %d days (%s to %s)", len(daily),
             daily["acq_date"].min().date(), daily["acq_date"].max().date())

    # Log-transform to handle heavy tails
    series = np.log1p(daily["frp_sum"].to_numpy())

    log.info("Computing matrix profile with %d-day window...", SUBSEQ_LEN)
    mp = stumpy.stump(series, m=SUBSEQ_LEN)
    profile = mp[:, 0].astype(float)
    log.info("  Matrix profile shape: %s, min=%.3f, max=%.3f, median=%.3f",
             profile.shape, profile.min(), profile.max(), np.median(profile))

    # Anomaly = global maxima (subsequences with no near neighbor)
    anomaly_threshold = float(np.quantile(profile, 0.99))
    log.info("  Anomaly threshold (p99): %.3f", anomaly_threshold)

    def window_dates(idx: int) -> tuple[str, str]:
        start = daily["acq_date"].iloc[idx]
        end = daily["acq_date"].iloc[idx + SUBSEQ_LEN - 1]
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    # Top-K anomalies — but spread them out so we don't get overlapping windows
    anomaly_records = []
    sorted_by_mp = np.argsort(-profile)
    selected_idx = []
    for idx in sorted_by_mp:
        too_close = any(abs(idx - prev) < SUBSEQ_LEN * 2 for prev in selected_idx)
        if too_close:
            continue
        selected_idx.append(idx)
        if len(selected_idx) >= TOP_K_ANOMALIES:
            break
    for idx in selected_idx:
        start_date, end_date = window_dates(int(idx))
        anomaly_records.append({
            "start_date": start_date,
            "end_date": end_date,
            "matrix_profile": float(profile[idx]),
            "nearest_neighbor_idx": int(mp[idx, 1]),
            "frp_sum_in_window": float(daily["frp_sum"].iloc[idx:idx+SUBSEQ_LEN].sum()),
            "n_detect_in_window": int(daily["n_detect"].iloc[idx:idx+SUBSEQ_LEN].sum()),
        })

    # Top-K motifs (most common patterns)
    motif_records = []
    sorted_ascending = np.argsort(profile)
    selected_motif_idx = []
    for idx in sorted_ascending:
        too_close = any(abs(idx - prev) < SUBSEQ_LEN * 2 for prev in selected_motif_idx)
        if too_close:
            continue
        selected_motif_idx.append(idx)
        if len(selected_motif_idx) >= TOP_K_MOTIFS:
            break
    for idx in selected_motif_idx:
        start_date, end_date = window_dates(int(idx))
        motif_records.append({
            "start_date": start_date,
            "end_date": end_date,
            "matrix_profile": float(profile[idx]),
            "nearest_neighbor_idx": int(mp[idx, 1]),
        })

    # Is the *most recent* 28-day window anomalous?
    last_window_idx = len(profile) - 1
    last_mp = float(profile[last_window_idx])
    last_start, last_end = window_dates(last_window_idx)
    is_current_unprecedented = bool(last_mp > anomaly_threshold)
    percentile = float((profile < last_mp).mean() * 100)

    log.info("\nLatest 28-day window (%s to %s): MP=%.3f, percentile=%.1f%%",
             last_start, last_end, last_mp, percentile)
    if is_current_unprecedented:
        log.info("  => UNPRECEDENTED (above p99). Current pattern is unlike anything in 12-year history.")
    else:
        log.info("  => Typical. Current pattern matches historical motifs.")

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "subsequence_length_days": SUBSEQ_LEN,
        "n_days_analyzed": int(len(daily)),
        "mp_stats": {
            "min": float(profile.min()),
            "median": float(np.median(profile)),
            "p90": float(np.quantile(profile, 0.9)),
            "p99": anomaly_threshold,
            "max": float(profile.max()),
        },
        "current_window": {
            "start_date": last_start,
            "end_date": last_end,
            "matrix_profile": last_mp,
            "percentile_in_history": percentile,
            "status": "UNPRECEDENTED" if is_current_unprecedented else "TYPICAL",
            "frp_sum_in_window": float(daily["frp_sum"].tail(SUBSEQ_LEN).sum()),
        },
        "top_anomalies": anomaly_records,
        "top_motifs": motif_records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    log.info("Wrote: %s", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
