"""
VanAagni Anomaly Scorer
========================
Computes real anomaly scores for fire detections using:
  1. FRP percentile within historical distribution for Guna Division
  2. FWI deviation from seasonal baseline
  3. Temporal clustering (multiple fires in short window)

Replaces the fabricated np.random.uniform() scores.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_LAKE = ROOT / "data_lake"

# Cache for historical distributions (loaded once)
_frp_distribution: Optional[np.ndarray] = None
_fwi_seasonal: Optional[Dict[int, float]] = None


def _load_frp_distribution() -> np.ndarray:
    """Load all historical FRP values for percentile calculation.
    Includes both MODIS SP and VIIRS SNPP for a robust distribution.
    """
    global _frp_distribution
    if _frp_distribution is not None:
        return _frp_distribution

    frps = []
    # Load VIIRS SNPP detections
    viirs_dir = DATA_LAKE / "fire_detections" / "firms_viirs_snpp_sp"
    for f in sorted(viirs_dir.glob("*.parquet")):
        df = pd.read_parquet(f)
        if "frp" in df.columns and len(df) > 0:
            frps.extend(df["frp"].dropna().tolist())

    # Also load MODIS SP detections for more robust percentile distribution
    modis_dir = DATA_LAKE / "fire_detections" / "firms_modis_sp"
    for f in sorted(modis_dir.glob("*.parquet")):
        df = pd.read_parquet(f)
        if "frp" in df.columns and len(df) > 0:
            frps.extend(df["frp"].dropna().tolist())

    _frp_distribution = np.array(frps) if frps else np.array([1.0, 5.0, 10.0, 20.0])
    log.info(f"Anomaly scorer: loaded {len(_frp_distribution)} historical FRP values (VIIRS+MODIS)")
    return _frp_distribution


def _load_fwi_seasonal_means() -> Dict[int, float]:
    """Load monthly FWI means for deviation calculation."""
    global _fwi_seasonal
    if _fwi_seasonal is not None:
        return _fwi_seasonal

    try:
        fwi_path = DATA_LAKE / "fire_weather" / "fwi_daily.parquet"
        fwi = pd.read_parquet(fwi_path)
        fwi["month"] = pd.to_datetime(fwi["date"]).dt.month
        _fwi_seasonal = fwi.groupby("month")["fwi"].mean().to_dict()
    except Exception as e:
        log.warning(f"Could not load FWI seasonal means: {e}")
        _fwi_seasonal = {m: 20.0 for m in range(1, 13)}

    return _fwi_seasonal


def compute_frp_percentile(frp_mw: float) -> float:
    """
    Compute where this FRP falls in historical distribution.
    Returns 0.0-1.0 (1.0 = highest ever recorded).
    """
    dist = _load_frp_distribution()
    if len(dist) == 0:
        return 0.5
    percentile = np.searchsorted(np.sort(dist), frp_mw) / len(dist)
    return round(min(1.0, percentile), 3)


def compute_fwi_deviation(fwi_value: float, month: int) -> float:
    """
    Compute how far this FWI is from seasonal baseline.
    Returns z-score-like deviation (0.0 = normal, >2.0 = extreme).
    """
    seasonal = _load_fwi_seasonal_means()
    baseline = seasonal.get(month, 20.0)
    if baseline <= 0:
        return 0.0
    deviation = (fwi_value - baseline) / max(baseline, 1.0)
    return round(max(0.0, deviation), 3)


def compute_anomaly_score(
    frp_mw: float,
    fwi_value: float,
    severity: str,
    month: int = 4,
    n_nearby_fires: int = 1,
) -> Dict[str, float]:
    """
    Compute a real, data-derived anomaly score for a fire detection.

    Components:
      - frp_percentile: How extreme is this FRP vs. historical? (0-1)
      - fwi_deviation: How far above seasonal FWI baseline? (0+)
      - cluster_bonus: Multiple fires nearby boost anomaly (0-0.15)
      - final_score: Weighted combination (0-1)

    Returns dict with all components for transparency.
    """
    frp_pct = compute_frp_percentile(frp_mw)
    fwi_dev = compute_fwi_deviation(fwi_value, month)

    # Cluster bonus: multiple fires suggest real event, not noise
    cluster_bonus = min(0.15, (n_nearby_fires - 1) * 0.05)

    # Weighted combination
    # FRP percentile is the strongest signal (60%)
    # FWI deviation adds weather context (25%)
    # Cluster adds spatial context (15%)
    raw_score = (frp_pct * 0.60) + (min(1.0, fwi_dev / 2.0) * 0.25) + cluster_bonus

    # Clamp to 0-1
    final_score = round(min(1.0, max(0.0, raw_score)), 3)

    return {
        "anomaly_score": final_score,
        "frp_percentile": frp_pct,
        "fwi_deviation": round(fwi_dev, 3),
        "cluster_bonus": round(cluster_bonus, 3),
        "method": "statistical",
    }


if __name__ == "__main__":
    # Test with different scenarios
    tests = [
        {"frp_mw": 62.75, "fwi_value": 55.5, "severity": "CRITICAL", "month": 4},
        {"frp_mw": 5.0, "fwi_value": 20.0, "severity": "MODERATE", "month": 3},
        {"frp_mw": 15.0, "fwi_value": 45.0, "severity": "HIGH", "month": 5},
    ]
    for t in tests:
        result = compute_anomaly_score(**t)
        print(f"FRP={t['frp_mw']} MW, FWI={t['fwi_value']}: score={result['anomaly_score']}")
        print(f"  Components: {result}")
