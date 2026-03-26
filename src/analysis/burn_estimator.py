"""
Burn Scar Extent Estimator
==========================
Estimates the probable burn scar area from a confirmed fire detection and its
spread prediction (Phase 1 output from SpreadPredictor).

Calibration is derived from historical FIRMS-to-burn-scar linkages stored in
``data_lake/burn_scars/fire_links.csv``.  For each spatially-confirmed, medium-
or high-confidence linkage the ratio of observed burn area to a physics-proxy
area (derived from FRP) is computed; the median of these ratios becomes the
calibration factor applied to the 24-hour spread polygon area.

Usage::

    from src.analysis.burn_estimator import BurnEstimator

    estimator = BurnEstimator()
    result = estimator.estimate(
        fire_detection={"fire_lat": 24.35, "fire_lon": 77.15, "frp_mw": 35.0},
        spread_result=spread_predictor_output,
        fwi=22.5,
    )
    # result["probable_burn_area_ha"]  → float
    # result["severity_class"]         → "SIGNIFICANT"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

_FIRE_LINKS_PATH = ROOT / "data_lake" / "burn_scars" / "fire_links.csv"

# Confidence tiers that are reliable enough to derive calibration from
_CALIBRATION_CONFIDENCE_LEVELS = {"MEDIUM", "MEDIUM-HIGH", "HIGH"}

# Default calibration ratio when no fire_links data is available
_DEFAULT_CALIBRATION_RATIO = 0.6

# FWI thresholds (Van Wagner 1987 / CIFFC classification)
_FWI_EXTREME_THRESHOLD = 38.0
_FWI_LOW_THRESHOLD = 5.0

# FRP-to-proxy-area conversion constant (empirical: 1 MW ≈ 2.5 ha active fire)
_FRP_TO_AREA_HA_PER_MW = 2.5


def _classify_severity(area_ha: float) -> str:
    """Return severity class string based on burn area in hectares.

    Boundaries are inclusive at the lower end of each class:
    - MINOR: < 5 ha
    - MODERATE: 5–50 ha
    - SIGNIFICANT: 50–500 ha
    - MAJOR: >= 500 ha
    """
    if area_ha >= 500.0:
        return "MAJOR"
    if area_ha >= 50.0:
        return "SIGNIFICANT"
    if area_ha >= 5.0:
        return "MODERATE"
    return "MINOR"


class BurnEstimator:
    """Estimates probable burn scar extent from fire detection and spread prediction.

    The estimator loads historical FIRMS-to-burn-scar linkages at construction
    time, derives a calibration ratio from spatially confirmed, medium-or-higher
    confidence records, then applies that ratio (with FWI and land-cover
    adjustments) to the 24-hour spread polygon area to produce a probable burn
    scar estimate.

    Parameters
    ----------
    fire_links_path:
        Override path to ``fire_links.csv``.  Defaults to the canonical
        ``data_lake/burn_scars/fire_links.csv`` location.
    """

    def __init__(self, fire_links_path: Path | None = None) -> None:
        path = fire_links_path or _FIRE_LINKS_PATH
        self._calibration_ratio, self._calibration_source, self._spatial_hit_ratio = (
            self._load_calibration(path)
        )
        log.info(
            "BurnEstimator ready — calibration_ratio=%.3f source=%s spatial_hit_ratio=%.2f",
            self._calibration_ratio,
            self._calibration_source,
            self._spatial_hit_ratio,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_calibration(
        path: Path,
    ) -> tuple[float, str, float]:
        """Load fire_links.csv and derive calibration parameters.

        Returns
        -------
        calibration_ratio : float
            Median ratio of observed burn area to FRP-proxy area for reliable rows.
        calibration_source : str
            Human-readable label for provenance.
        spatial_hit_ratio : float
            Fraction of reliable rows where spatial_hit is True; used to set
            output confidence tier.
        """
        if not path.exists():
            log.warning("fire_links.csv not found at %s — using default calibration", path)
            return _DEFAULT_CALIBRATION_RATIO, "default", 0.0

        try:
            df = pd.read_csv(path)
        except Exception as exc:
            log.warning("Failed to read fire_links.csv (%s) — using default calibration", exc)
            return _DEFAULT_CALIBRATION_RATIO, "default", 0.0

        required_cols = {"burn_area_ha", "fire_frp_mw", "spatial_hit", "confidence"}
        if not required_cols.issubset(df.columns):
            log.warning(
                "fire_links.csv missing columns %s — using default calibration",
                required_cols - set(df.columns),
            )
            return _DEFAULT_CALIBRATION_RATIO, "default", 0.0

        # Keep only spatially confirmed, reliable-confidence rows with valid FRP
        mask = (
            df["spatial_hit"].astype(str).str.strip().str.lower().isin({"true", "1"})
            & df["confidence"].isin(_CALIBRATION_CONFIDENCE_LEVELS)
            & df["fire_frp_mw"].notna()
            & (df["fire_frp_mw"] > 0)
            & df["burn_area_ha"].notna()
            & (df["burn_area_ha"] > 0)
        )
        reliable = df[mask].copy()

        if reliable.empty:
            log.warning(
                "No reliable calibration rows in fire_links.csv — using default calibration"
            )
            return _DEFAULT_CALIBRATION_RATIO, "default", 0.0

        proxy_area = reliable["fire_frp_mw"] * _FRP_TO_AREA_HA_PER_MW
        ratios = reliable["burn_area_ha"] / proxy_area
        calibration_ratio = float(np.median(ratios))

        # Clamp to [0.05, 5.0] to guard against outlier rows
        calibration_ratio = float(np.clip(calibration_ratio, 0.05, 5.0))

        n_rows = len(reliable)
        spatial_hit_ratio = float(
            df[df["confidence"].isin(_CALIBRATION_CONFIDENCE_LEVELS)]["spatial_hit"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin({"true", "1"})
            .mean()
        )

        source = f"fire_links ({n_rows} rows)"
        log.info(
            "Calibration loaded: n=%d ratio=%.3f spatial_hit_ratio=%.2f",
            n_rows,
            calibration_ratio,
            spatial_hit_ratio,
        )
        return calibration_ratio, source, spatial_hit_ratio

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate(
        self,
        fire_detection: dict[str, Any],
        spread_result: dict[str, Any],
        fwi: float,
    ) -> dict[str, Any]:
        """Estimate the probable burn scar extent.

        Parameters
        ----------
        fire_detection:
            Dict containing at minimum ``fire_lat``, ``fire_lon``, ``frp_mw``.
            May optionally contain ``land_cover`` (``"agricultural"`` reduces
            the estimate by 30 %).
        spread_result:
            Output from :class:`~src.analysis.spread_predictor.SpreadPredictor`.
            Must contain ``spread_24h`` with an ``area_ha`` key.
        fwi:
            Current Fire Weather Index (dimensionless).

        Returns
        -------
        dict with keys:
            probable_burn_area_ha, confidence, calibration_source,
            severity_class, spread_24h_area_ha, calibration_ratio,
            fwi_adjustment.
        """
        spread_24h = spread_result.get("spread_24h", {})
        spread_24h_area_ha: float = float(spread_24h.get("area_ha", 0.0))

        if spread_24h_area_ha <= 0.0:
            log.warning(
                "spread_24h area_ha is %.2f — defaulting to FRP-proxy estimate",
                spread_24h_area_ha,
            )
            frp_mw = float(fire_detection.get("frp_mw", 1.0))
            spread_24h_area_ha = max(frp_mw * _FRP_TO_AREA_HA_PER_MW, 1.0)

        # Step 1 — apply calibration ratio to 24 h spread area
        probable_area = spread_24h_area_ha * self._calibration_ratio

        # Step 2 — FWI adjustment
        if fwi >= _FWI_EXTREME_THRESHOLD:
            fwi_adjustment = 1.2
        elif fwi < _FWI_LOW_THRESHOLD:
            fwi_adjustment = 0.5
        else:
            fwi_adjustment = 1.0

        probable_area *= fwi_adjustment

        # Step 3 — land cover adjustment (agricultural stubble burns smaller)
        land_cover = str(fire_detection.get("land_cover", "")).lower()
        if "agri" in land_cover:
            probable_area *= 0.7

        probable_area = max(probable_area, 0.01)

        # Step 4 — output confidence tier
        if self._calibration_source == "default":
            confidence = "LOW"
        elif self._spatial_hit_ratio > 0.5:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"

        return {
            "probable_burn_area_ha": round(probable_area, 2),
            "confidence": confidence,
            "calibration_source": self._calibration_source,
            "severity_class": _classify_severity(probable_area),
            "spread_24h_area_ha": round(spread_24h_area_ha, 2),
            "calibration_ratio": round(self._calibration_ratio, 4),
            "fwi_adjustment": fwi_adjustment,
        }
