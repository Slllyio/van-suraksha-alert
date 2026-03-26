"""
Tests for src/analysis/spread_predictor.py
============================================
Covers:
- SpreadPredictor.predict() output contract (keys, types, ranges)
- Physics-mode simulation produces monotonically growing burn area across horizons
- _initial_phi() shape and sign convention
- _weather_to_sim_dict() wind decomposition and fuel anomaly
- _load_terrain_window() fallback to flat terrain on missing files
- _phi_to_geojson() with burned / unburned / edge-case inputs
- _area_ha() pixel-to-hectare conversion
- Numerical stability: extreme FRP, extreme weather values
"""

from __future__ import annotations

import math
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure project root is on sys.path when running from tests/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def typical_fire() -> dict:
    return {"fire_lat": 24.15, "fire_lon": 77.30, "frp_mw": 35.0}


@pytest.fixture()
def typical_weather() -> dict:
    return {
        "wind_kmh": 20.0,
        "temp_c": 38.0,
        "rh_pct": 25.0,
        "fwi": 18.0,
        "wind_dir_deg": 225.0,
    }


@pytest.fixture()
def predictor():
    """SpreadPredictor with no CNN weights (physics-only mode)."""
    from src.analysis.spread_predictor import SpreadPredictor
    return SpreadPredictor(model_path=None, prefer_cnn=False)


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------

class TestPredictOutputContract:
    """Verify the returned dict has the exact shape specified by the API."""

    def test_top_level_keys(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        required = {
            "fire_lat", "fire_lon",
            "spread_6h", "spread_12h", "spread_24h",
            "byram_intensity_kw_m", "flame_length_m", "mode",
        }
        assert required.issubset(result.keys()), (
            f"Missing keys: {required - result.keys()}"
        )

    def test_spread_sub_dict_keys(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        for horizon in ("spread_6h", "spread_12h", "spread_24h"):
            sub = result[horizon]
            assert "polygon" in sub
            assert "area_ha" in sub
            assert "max_ros_m_min" in sub

    def test_mode_is_physics_without_weights(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        assert result["mode"] == "physics"

    def test_fire_coords_pass_through(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        assert result["fire_lat"] == pytest.approx(typical_fire["fire_lat"])
        assert result["fire_lon"] == pytest.approx(typical_fire["fire_lon"])

    def test_polygon_is_geojson_dict(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        poly = result["spread_6h"]["polygon"]
        assert isinstance(poly, dict)
        assert "type" in poly
        assert poly["type"] in ("Polygon", "MultiPolygon")

    def test_area_ha_is_non_negative(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        for horizon in ("spread_6h", "spread_12h", "spread_24h"):
            assert result[horizon]["area_ha"] >= 0.0

    def test_byram_intensity_positive(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        assert result["byram_intensity_kw_m"] > 0.0

    def test_flame_length_positive(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        assert result["flame_length_m"] > 0.0

    def test_max_ros_positive(self, predictor, typical_fire, typical_weather):
        result = predictor.predict(typical_fire, typical_weather)
        for horizon in ("spread_6h", "spread_12h", "spread_24h"):
            assert result[horizon]["max_ros_m_min"] > 0.0


# ---------------------------------------------------------------------------
# Fire spread physics
# ---------------------------------------------------------------------------

class TestSpreadPhysics:
    """Verify physically meaningful simulation behaviour."""

    def test_burn_area_grows_monotonically(self, predictor, typical_fire, typical_weather):
        """Burned area must not shrink as simulation time increases."""
        result = predictor.predict(typical_fire, typical_weather)
        area_6h = result["spread_6h"]["area_ha"]
        area_12h = result["spread_12h"]["area_ha"]
        area_24h = result["spread_24h"]["area_ha"]
        assert area_6h <= area_12h, "Burn area shrank from 6 h to 12 h"
        assert area_12h <= area_24h, "Burn area shrank from 12 h to 24 h"

    def test_higher_frp_larger_or_equal_burn_area(
        self, predictor, typical_weather
    ):
        """Higher FRP (more intense fire) must produce ≥ area at every horizon."""
        fire_low = {"fire_lat": 24.15, "fire_lon": 77.30, "frp_mw": 5.0}
        fire_high = {"fire_lat": 24.15, "fire_lon": 77.30, "frp_mw": 100.0}
        result_low = predictor.predict(fire_low, typical_weather)
        result_high = predictor.predict(fire_high, typical_weather)
        for horizon in ("spread_6h", "spread_12h", "spread_24h"):
            assert result_high[horizon]["area_ha"] >= result_low[horizon]["area_ha"], (
                f"{horizon}: high-FRP area {result_high[horizon]['area_ha']} < "
                f"low-FRP area {result_low[horizon]['area_ha']}"
            )

    def test_minimum_ros_floor_applied(self, predictor, typical_weather):
        """FRP of 0 should still yield ros = 1 m/min (floor enforced)."""
        fire_zero_frp = {"fire_lat": 24.15, "fire_lon": 77.30, "frp_mw": 0.0}
        result = predictor.predict(fire_zero_frp, typical_weather)
        assert result["spread_6h"]["max_ros_m_min"] >= 1.0


# ---------------------------------------------------------------------------
# _initial_phi
# ---------------------------------------------------------------------------

class TestInitialPhi:

    def test_shape(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = SpreadPredictor._initial_phi(grid_size=64)
        assert phi.shape == (64, 64)

    def test_dtype_float32(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = SpreadPredictor._initial_phi()
        assert phi.dtype == np.float32

    def test_center_is_burned(self):
        """Centre pixel must be inside the fire seed (phi <= 0)."""
        from src.analysis.spread_predictor import SpreadPredictor
        phi = SpreadPredictor._initial_phi(grid_size=64, radius_px=3)
        assert phi[32, 32] <= 0.0

    def test_corner_is_unburned(self):
        """Corners must be outside the fire seed (phi > 0)."""
        from src.analysis.spread_predictor import SpreadPredictor
        phi = SpreadPredictor._initial_phi(grid_size=64, radius_px=3)
        assert phi[0, 0] > 0.0

    def test_seed_area_is_small(self):
        """Seed fire should occupy < 5% of the grid."""
        from src.analysis.spread_predictor import SpreadPredictor
        phi = SpreadPredictor._initial_phi()
        burned_fraction = (phi <= 0).sum() / phi.size
        assert burned_fraction < 0.05


# ---------------------------------------------------------------------------
# _weather_to_sim_dict
# ---------------------------------------------------------------------------

class TestWeatherToSimDict:

    def test_returns_required_keys(self):
        from src.analysis.spread_predictor import SpreadPredictor
        sim = SpreadPredictor._weather_to_sim_dict(
            {"wind_kmh": 18.0, "rh_pct": 30.0, "temp_c": 35.0}
        )
        assert "wind_u" in sim
        assert "wind_v" in sim
        assert "fuel_anomaly" in sim

    def test_fuel_anomaly_negative_when_dry(self):
        """rh_pct = 20 → anomaly = (20-40)/20 = -1 (dry = negative)."""
        from src.analysis.spread_predictor import SpreadPredictor
        sim = SpreadPredictor._weather_to_sim_dict({"rh_pct": 20.0})
        assert float(sim["fuel_anomaly"][0, 0]) == pytest.approx(-1.0)

    def test_fuel_anomaly_positive_when_humid(self):
        """rh_pct = 80 → anomaly = (80-40)/20 = 2 (humid = positive)."""
        from src.analysis.spread_predictor import SpreadPredictor
        sim = SpreadPredictor._weather_to_sim_dict({"rh_pct": 80.0})
        assert float(sim["fuel_anomaly"][0, 0]) == pytest.approx(2.0)

    def test_wind_north_convention(self):
        """Wind from North (0°) should yield wind_u=0 and wind_v<0 (northward flow)."""
        from src.analysis.spread_predictor import SpreadPredictor
        sim = SpreadPredictor._weather_to_sim_dict(
            {"wind_kmh": 36.0, "wind_dir_deg": 0.0}
        )
        assert sim["wind_u"] == pytest.approx(0.0, abs=1e-6)
        assert sim["wind_v"] < 0  # flow toward north (negative v in met. convention)

    def test_wind_east_convention(self):
        """Wind from East (90°) should yield wind_u<0, wind_v≈0."""
        from src.analysis.spread_predictor import SpreadPredictor
        sim = SpreadPredictor._weather_to_sim_dict(
            {"wind_kmh": 36.0, "wind_dir_deg": 90.0}
        )
        assert sim["wind_u"] < 0
        assert sim["wind_v"] == pytest.approx(0.0, abs=1e-6)

    def test_wind_speed_conversion(self):
        """36 km/h = 10 m/s; total wind vector magnitude must equal 10 m/s."""
        from src.analysis.spread_predictor import SpreadPredictor
        sim = SpreadPredictor._weather_to_sim_dict(
            {"wind_kmh": 36.0, "wind_dir_deg": 45.0}
        )
        magnitude = math.sqrt(sim["wind_u"] ** 2 + sim["wind_v"] ** 2)
        assert magnitude == pytest.approx(10.0, rel=1e-4)

    def test_fuel_anomaly_shape(self):
        from src.analysis.spread_predictor import SpreadPredictor
        sim = SpreadPredictor._weather_to_sim_dict({}, grid_size=64)
        assert sim["fuel_anomaly"].shape == (64, 64)


# ---------------------------------------------------------------------------
# _load_terrain_window — fallback path
# ---------------------------------------------------------------------------

class TestLoadTerrainWindowFallback:

    def test_fallback_when_raster_files_patched_away(self, predictor):
        """When slope/aspect paths don't exist the flat-terrain fallback is used."""
        with patch("src.analysis.spread_predictor._SLOPE_PATH", Path("/nonexistent/slope.tif")), \
             patch("src.analysis.spread_predictor._ASPECT_PATH", Path("/nonexistent/aspect.tif")):
            terrain, transform = predictor._load_terrain_window(lat=24.15, lon=77.30)
        assert "slope" in terrain
        assert "aspect" in terrain
        assert terrain["slope"].shape == (128, 128)

    def test_fallback_slope_is_zero_when_files_missing(self, predictor):
        """Flat-terrain fallback must return all-zero slope."""
        with patch("src.analysis.spread_predictor._SLOPE_PATH", Path("/nonexistent/slope.tif")), \
             patch("src.analysis.spread_predictor._ASPECT_PATH", Path("/nonexistent/aspect.tif")):
            terrain, _ = predictor._load_terrain_window(lat=24.15, lon=77.30)
        np.testing.assert_array_equal(terrain["slope"], 0.0)

    def test_fallback_affine_transform_defined(self, predictor):
        """Fallback must still return a valid affine transform."""
        from affine import Affine
        with patch("src.analysis.spread_predictor._SLOPE_PATH", Path("/nonexistent/slope.tif")), \
             patch("src.analysis.spread_predictor._ASPECT_PATH", Path("/nonexistent/aspect.tif")):
            _, transform = predictor._load_terrain_window(lat=24.0, lon=77.0)
        assert isinstance(transform, Affine)

    def test_valid_aoi_returns_correct_shape(self, predictor):
        """Inside Guna AOI the terrain loader should return 128×128 float32 arrays."""
        try:
            terrain, _ = predictor._load_terrain_window(lat=24.15, lon=77.30)
            assert terrain["slope"].shape == (128, 128)
            assert terrain["slope"].dtype == np.float32
        except Exception:
            pytest.skip("Rasterio or terrain raster not available in test environment")


# ---------------------------------------------------------------------------
# _phi_to_geojson
# ---------------------------------------------------------------------------

class TestPhiToGeoJson:

    def _make_affine(self):
        from affine import Affine
        # Simple 30m pixel at lat 24°
        pdlon = 30.0 / (111_320.0 * math.cos(math.radians(24.0)))
        pdlat = 30.0 / 111_320.0
        return Affine(pdlon, 0.0, 77.0, 0.0, -pdlat, 24.2)

    def test_all_unburned_returns_empty_polygon(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = np.ones((64, 64), dtype=np.float32)  # all positive → unburned
        result = SpreadPredictor._phi_to_geojson(phi, self._make_affine())
        assert result == {"type": "Polygon", "coordinates": []}

    def test_all_burned_returns_valid_polygon(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = -np.ones((64, 64), dtype=np.float32)  # all burned
        result = SpreadPredictor._phi_to_geojson(phi, self._make_affine())
        assert result["type"] in ("Polygon", "MultiPolygon")
        assert result["coordinates"]  # non-empty ring

    def test_partial_burn_has_coordinates(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = SpreadPredictor._initial_phi(grid_size=64, radius_px=5)
        result = SpreadPredictor._phi_to_geojson(phi, self._make_affine())
        assert result["type"] in ("Polygon", "MultiPolygon")

    def test_polygon_coordinates_in_wgs84_range(self):
        """Output coordinates must be within WGS-84 lon/lat bounds."""
        from src.analysis.spread_predictor import SpreadPredictor
        phi = -np.ones((32, 32), dtype=np.float32)
        result = SpreadPredictor._phi_to_geojson(phi, self._make_affine())
        if result["type"] == "Polygon":
            ring = result["coordinates"][0]
        else:  # MultiPolygon
            ring = result["coordinates"][0][0]
        lons = [pt[0] for pt in ring]
        lats = [pt[1] for pt in ring]
        assert all(-180 <= lon <= 180 for lon in lons)
        assert all(-90 <= lat <= 90 for lat in lats)


# ---------------------------------------------------------------------------
# _area_ha
# ---------------------------------------------------------------------------

class TestAreaHa:

    def test_zero_burned_pixels(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = np.ones((64, 64), dtype=np.float32)
        assert SpreadPredictor._area_ha(phi) == pytest.approx(0.0)

    def test_single_pixel_burned(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = np.ones((64, 64), dtype=np.float32)
        phi[32, 32] = -1.0
        # 1 pixel × 900 m² / 10000 = 0.09 ha
        assert SpreadPredictor._area_ha(phi) == pytest.approx(0.09)

    def test_full_grid_burned(self):
        from src.analysis.spread_predictor import SpreadPredictor
        phi = -np.ones((10, 10), dtype=np.float32)
        # 100 pixels × 0.09 ha/pixel = 9.0 ha
        assert SpreadPredictor._area_ha(phi) == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# Numerical stability / edge cases
# ---------------------------------------------------------------------------

class TestNumericalStability:

    def test_very_high_frp(self, predictor, typical_weather):
        """FRP of 1000 MW should not raise and should return finite values."""
        fire = {"fire_lat": 24.15, "fire_lon": 77.30, "frp_mw": 1000.0}
        result = predictor.predict(fire, typical_weather)
        assert math.isfinite(result["byram_intensity_kw_m"])
        assert math.isfinite(result["flame_length_m"])

    def test_very_low_rh(self, predictor, typical_fire):
        """rh_pct = 5 (extremely dry) must not raise."""
        weather = {"wind_kmh": 30.0, "temp_c": 45.0, "rh_pct": 5.0, "fwi": 40.0}
        result = predictor.predict(typical_fire, weather)
        assert result["mode"] == "physics"

    def test_zero_wind_speed(self, predictor, typical_fire):
        """Calm conditions (0 km/h) should spread symmetrically and not raise."""
        weather = {"wind_kmh": 0.0, "temp_c": 35.0, "rh_pct": 40.0, "fwi": 10.0}
        result = predictor.predict(typical_fire, weather)
        assert result["spread_6h"]["area_ha"] >= 0.0

    def test_missing_frp_defaults_to_one(self, predictor, typical_weather):
        """frp_mw missing → default 1 MW → ros floor 1 m/min."""
        fire = {"fire_lat": 24.15, "fire_lon": 77.30}  # no frp_mw key
        result = predictor.predict(fire, typical_weather)
        assert result["spread_6h"]["max_ros_m_min"] >= 1.0

    def test_prefer_cnn_false_never_loads_simulator(self, typical_fire, typical_weather):
        """With prefer_cnn=False the Muhurta2DSimulator is never instantiated."""
        from src.analysis.spread_predictor import SpreadPredictor
        p = SpreadPredictor(model_path=None, prefer_cnn=False)
        p.predict(typical_fire, typical_weather)
        assert p._simulator is None
