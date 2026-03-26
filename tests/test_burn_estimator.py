"""
tests/test_burn_estimator.py
============================
Unit tests for BurnEstimator.

Coverage
--------
1. Calibration loading from real fire_links.csv
2. Calibration fallback when file is missing
3. Calibration fallback when file has wrong columns
4. estimate() with normal FWI
5. estimate() with extreme FWI (>= 38) — multiplier 1.2
6. estimate() with low FWI (< 5) — multiplier 0.5
7. estimate() with agricultural land cover — reduction 0.3
8. estimate() falls back to FRP-proxy when spread_24h area_ha is 0
9. Severity class boundaries: MINOR / MODERATE / SIGNIFICANT / MAJOR
10. Calibration ratio clamping guards against extreme outliers
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from src.analysis.burn_estimator import BurnEstimator, _classify_severity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_CSV = """\
scene_date,tile,burn_area_px,burn_area_ha,burn_pct,fire_date,fire_time_utc,fire_time_ist,\
fire_lat,fire_lon,fire_frp_mw,viirs_confidence,daynight,spatial_hit,dist_to_burn_m,\
days_gap,n_firms_in_window,n_spatial_hits,confidence
2017-02-16,T43QFG,607763,54698.7,28.25,2017-01-30,20:53,02:23,24.19821,76.78249,\
0.71,n,N,True,0.0,17.0,3,1,MEDIUM-HIGH
2017-03-01,T43QFG,14385,1294.6,0.67,2017-01-30,20:53,02:23,24.19821,76.78249,\
0.71,n,N,False,4124.0,30.0,4,0,LOW
2017-03-08,T43QFG,618623,55676.1,28.76,2017-01-30,20:53,02:23,24.19821,76.78249,\
0.71,n,N,True,0.0,37.0,5,1,MEDIUM
2017-04-17,T43QFG,445742,40116.8,20.72,2017-03-21,07:47,13:17,24.19665,76.75802,\
29.22,l,D,True,0.0,27.0,9,2,MEDIUM-HIGH
"""

_GOOD_SPREAD: dict[str, Any] = {
    "fire_lat": 24.35,
    "fire_lon": 77.15,
    "spread_6h": {"polygon": {}, "area_ha": 21.0, "max_ros_m_min": 5.07},
    "spread_12h": {"polygon": {}, "area_ha": 57.7, "max_ros_m_min": 5.07},
    "spread_24h": {"polygon": {}, "area_ha": 204.6, "max_ros_m_min": 5.07},
    "byram_intensity_kw_m": 1500.0,
    "flame_length_m": 2.24,
    "mode": "physics",
}

_GOOD_DETECTION: dict[str, Any] = {
    "fire_lat": 24.35,
    "fire_lon": 77.15,
    "frp_mw": 35.0,
}


@pytest.fixture()
def tmp_fire_links(tmp_path: Path) -> Path:
    """Write _MINIMAL_CSV to a temporary file and return its path."""
    p = tmp_path / "fire_links.csv"
    p.write_text(_MINIMAL_CSV)
    return p


# ---------------------------------------------------------------------------
# Tests — calibration loading
# ---------------------------------------------------------------------------


def test_calibration_loads_from_csv(tmp_fire_links: Path) -> None:
    """Calibration ratio should be derived from reliable rows only."""
    est = BurnEstimator(fire_links_path=tmp_fire_links)
    # Three reliable rows (spatial_hit=True, confidence MEDIUM/MEDIUM-HIGH):
    # FRP-proxy areas: 0.71*2.5=1.775, 0.71*2.5=1.775, 29.22*2.5=73.05
    # Ratios: 54698.7/1.775, 55676.1/1.775, 40116.8/73.05
    # → median of [30816.7, 31366.0, 549.2] ≈ 30816.7
    # Clamped to max 5.0 → calibration_ratio == 5.0
    assert est._calibration_ratio == 5.0
    assert "fire_links" in est._calibration_source
    assert "3 rows" in est._calibration_source


def test_calibration_fallback_missing_file() -> None:
    """Missing file should silently fall back to default ratio."""
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    assert est._calibration_ratio == pytest.approx(0.6)
    assert est._calibration_source == "default"


def test_calibration_fallback_wrong_columns(tmp_path: Path) -> None:
    """CSV with wrong columns should fall back to default ratio."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("col_a,col_b\n1,2\n")
    est = BurnEstimator(fire_links_path=bad_csv)
    assert est._calibration_ratio == pytest.approx(0.6)
    assert est._calibration_source == "default"


def test_calibration_fallback_no_reliable_rows(tmp_path: Path) -> None:
    """CSV with only LOW-confidence rows should fall back to default ratio."""
    csv_text = (
        "scene_date,tile,burn_area_px,burn_area_ha,burn_pct,fire_date,fire_time_utc,"
        "fire_time_ist,fire_lat,fire_lon,fire_frp_mw,viirs_confidence,daynight,"
        "spatial_hit,dist_to_burn_m,days_gap,n_firms_in_window,n_spatial_hits,confidence\n"
        "2017-03-01,T43QFG,14385,1294.6,0.67,2017-01-30,20:53,02:23,24.19,76.78,"
        "0.71,n,N,True,0.0,30.0,4,0,LOW\n"
    )
    p = tmp_path / "low_only.csv"
    p.write_text(csv_text)
    est = BurnEstimator(fire_links_path=p)
    assert est._calibration_ratio == pytest.approx(0.6)
    assert est._calibration_source == "default"


# ---------------------------------------------------------------------------
# Tests — estimate() logic
# ---------------------------------------------------------------------------


def test_estimate_normal_fwi() -> None:
    """Normal FWI (5–37) should apply no FWI multiplier."""
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=22.0)

    expected_area = 204.6 * 0.6 * 1.0
    assert result["probable_burn_area_ha"] == pytest.approx(expected_area, rel=1e-3)
    assert result["fwi_adjustment"] == pytest.approx(1.0)
    assert result["spread_24h_area_ha"] == pytest.approx(204.6)
    assert result["calibration_ratio"] == pytest.approx(0.6)


def test_estimate_extreme_fwi() -> None:
    """FWI >= 38 should apply a 1.2 multiplier."""
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=40.0)

    expected_area = 204.6 * 0.6 * 1.2
    assert result["probable_burn_area_ha"] == pytest.approx(expected_area, rel=1e-3)
    assert result["fwi_adjustment"] == pytest.approx(1.2)


def test_estimate_low_fwi() -> None:
    """FWI < 5 should apply a 0.5 multiplier."""
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=3.0)

    expected_area = 204.6 * 0.6 * 0.5
    assert result["probable_burn_area_ha"] == pytest.approx(expected_area, rel=1e-3)
    assert result["fwi_adjustment"] == pytest.approx(0.5)


def test_estimate_agricultural_land_cover() -> None:
    """Agricultural land cover should reduce estimate by 30 %."""
    detection = {**_GOOD_DETECTION, "land_cover": "agricultural"}
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(detection, _GOOD_SPREAD, fwi=22.0)

    expected_area = 204.6 * 0.6 * 1.0 * 0.7
    assert result["probable_burn_area_ha"] == pytest.approx(expected_area, rel=1e-3)


def test_estimate_non_agricultural_cover_unaffected() -> None:
    """Forest land cover should not trigger the agricultural reduction."""
    detection = {**_GOOD_DETECTION, "land_cover": "forest"}
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result_forest = est.estimate(detection, _GOOD_SPREAD, fwi=22.0)
    result_plain = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=22.0)

    assert result_forest["probable_burn_area_ha"] == result_plain["probable_burn_area_ha"]


def test_estimate_fallback_to_frp_proxy_when_no_spread_area() -> None:
    """When spread_24h area_ha is 0, FRP proxy should be used instead."""
    spread_no_area = {
        **_GOOD_SPREAD,
        "spread_24h": {"polygon": {}, "area_ha": 0.0, "max_ros_m_min": 5.07},
    }
    detection = {**_GOOD_DETECTION, "frp_mw": 20.0}
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(detection, spread_no_area, fwi=22.0)

    # FRP proxy: 20.0 * 2.5 = 50.0 ha; * 0.6 calibration = 30.0
    assert result["probable_burn_area_ha"] == pytest.approx(30.0, rel=1e-3)
    assert result["spread_24h_area_ha"] == pytest.approx(50.0)


def test_estimate_confidence_low_when_no_calibration() -> None:
    """No calibration data → confidence must be LOW."""
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=22.0)
    assert result["confidence"] == "LOW"


def test_estimate_confidence_high_when_spatial_hit_ratio_above_half(
    tmp_fire_links: Path,
) -> None:
    """spatial_hit_ratio > 0.5 from calibration data → confidence HIGH."""
    est = BurnEstimator(fire_links_path=tmp_fire_links)
    result = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=22.0)
    # 3 out of 4 medium/medium-high/high rows are spatial_hit → ratio 0.75 > 0.5
    assert result["confidence"] == "HIGH"


def test_estimate_result_keys_present() -> None:
    """Output dict must contain all required keys."""
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=22.0)

    required_keys = {
        "probable_burn_area_ha",
        "confidence",
        "calibration_source",
        "severity_class",
        "spread_24h_area_ha",
        "calibration_ratio",
        "fwi_adjustment",
    }
    assert required_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# Tests — _classify_severity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "area_ha, expected",
    [
        (0.5, "MINOR"),
        (4.99, "MINOR"),
        (5.0, "MODERATE"),
        (49.99, "MODERATE"),
        (50.0, "SIGNIFICANT"),
        (499.99, "SIGNIFICANT"),
        (500.0, "MAJOR"),
        (10000.0, "MAJOR"),
    ],
)
def test_classify_severity_boundaries(area_ha: float, expected: str) -> None:
    assert _classify_severity(area_ha) == expected


def test_estimate_severity_class_consistent_with_area() -> None:
    """Severity class in output must match _classify_severity(probable_burn_area_ha)."""
    est = BurnEstimator(fire_links_path=Path("/nonexistent/fire_links.csv"))
    result = est.estimate(_GOOD_DETECTION, _GOOD_SPREAD, fwi=22.0)
    assert result["severity_class"] == _classify_severity(result["probable_burn_area_ha"])
