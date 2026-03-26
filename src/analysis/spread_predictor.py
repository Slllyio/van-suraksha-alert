"""
Fire Spread Predictor
=====================
Bridges the FirePhysicsEngine and Muhurta2DSimulator into a single callable
that accepts a FIRMS fire detection + weather observation and returns predicted
spread polygons at 6 h, 12 h, and 24 h horizons.

Two modes:
  physics  — Rothermel topographic adjustment + WRF-Fire level-set PDE directly
             (no neural weights required, default for NRT operations).
  cnn      — Full Muhurta-2D PIML loop (requires trained ROS U-Net weights).

Usage::

    predictor = SpreadPredictor()
    result = predictor.predict(
        fire_detection={"fire_lat": 24.1, "fire_lon": 77.2, "frp_mw": 35.0},
        weather={"wind_kmh": 20.0, "temp_c": 38.0, "rh_pct": 25.0, "fwi": 18.0},
    )
    # result["spread_6h"]["polygon"]  → GeoJSON geometry dict
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

import src.utils.proj_fix  # noqa: F401  (PROJ/GDAL env fix must precede rasterio)

from src.analysis.fire_dynamics import FireEventTracker
from src.analysis.fire_physics import FirePhysicsEngine

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

_SLOPE_PATH = ROOT / "data_lake" / "terrain" / "slope_guna_30m.tif"
_ASPECT_PATH = ROOT / "data_lake" / "terrain" / "aspect_guna_30m.tif"
_FOREST_MASK_PATH = ROOT / "data_lake" / "land_cover" / "forest_mask_guna_30m.tif"

_GRID_SIZE = 128           # pixels (30 m res → 3.84 km window)
_DX = _DY = 30.0           # metres per pixel
_DT_MINUTES = 5.0          # physics-mode time step (minutes)
_INITIAL_RADIUS_PX = 3     # seed fire radius (pixels)
_DEFAULT_WIND_DIR_DEG = 225.0   # SW — dominant during MP fire season
_SPREAD_HORIZONS_MIN = [360, 720, 1440]  # 6 h, 12 h, 24 h
_SIMPLIFY_TOL_DEG = 0.001  # shapely simplification tolerance (°)


class SpreadPredictor:
    """
    Predicts wildfire spread at 6/12/24-hour horizons for a single FIRMS detection.

    Parameters
    ----------
    model_path : str | Path | None
        Path to trained ROS U-Net weights (.pth).  When ``None`` the predictor
        falls back to physics-only mode regardless of ``prefer_cnn``.
    device : str
        PyTorch device string ("cpu", "cuda", "directml").
    prefer_cnn : bool
        Use CNN mode when weights are available.  Defaults to ``False``
        (physics mode is faster and sufficient for NRT operations).
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        device: str = "cpu",
        prefer_cnn: bool = False,
    ) -> None:
        self._physics = FirePhysicsEngine()
        self._model_path = Path(model_path) if model_path else None
        self._device = device
        self._prefer_cnn = prefer_cnn
        self._simulator = None  # lazy: only imported/created when needed

    def predict(
        self,
        fire_detection: dict[str, Any],
        weather: dict[str, Any],
    ) -> dict[str, Any]:
        """Predict fire spread at 6/12/24-hour horizons for one FIRMS detection.

        fire_detection keys: ``fire_lat``, ``fire_lon``, ``frp_mw``.
        weather keys: ``wind_kmh``, ``temp_c``, ``rh_pct``, ``fwi``
        (optional: ``wind_dir_deg``, defaults to 225° SW).

        Returns dict with spread_6h / spread_12h / spread_24h sub-dicts each
        containing ``polygon`` (GeoJSON), ``area_ha``, ``max_ros_m_min``, plus
        ``byram_intensity_kw_m``, ``flame_length_m``, and ``mode``.
        """
        lat: float = float(fire_detection["fire_lat"])
        lon: float = float(fire_detection["fire_lon"])
        frp_mw: float = float(fire_detection.get("frp_mw", 1.0))

        # FRP → base ROS proxy (m/min)
        ros_m_min: float = max(frp_mw * 0.2, 1.0)

        terrain_dict, affine_transform = self._load_terrain_window(lat, lon)
        sim_weather = self._weather_to_sim_dict(weather)
        initial_phi = self._initial_phi()

        # Scalar intensity metrics (at ignition, before topo adjustment)
        ros_m_s_scalar = ros_m_min / 60.0
        intensity_arr = self._physics.calculate_byram_intensity(
            np.array([ros_m_s_scalar])
        )
        flame_len_arr = self._physics.calculate_flame_length(intensity_arr)

        use_cnn = self._prefer_cnn and self._model_path is not None
        mode = "cnn" if use_cnn else "physics"

        spread_results: dict[str, Any] = {}
        for horizon_min in _SPREAD_HORIZONS_MIN:
            if use_cnn:
                final_phi, max_ros = self._run_cnn_mode(
                    initial_phi.copy(), terrain_dict, sim_weather, ros_m_min,
                    horizon_min,
                )
            else:
                final_phi, max_ros = self._run_physics_mode(
                    initial_phi.copy(), terrain_dict, sim_weather, ros_m_min,
                    horizon_min,
                )

            polygon_geojson = self._phi_to_geojson(final_phi, affine_transform)
            area_ha = self._area_ha(final_phi)
            key = f"spread_{horizon_min // 60}h"
            spread_results[key] = {
                "polygon": polygon_geojson,
                "area_ha": round(area_ha, 2),
                "max_ros_m_min": round(max_ros, 3),
            }

        return {
            "fire_lat": lat,
            "fire_lon": lon,
            **spread_results,
            "byram_intensity_kw_m": round(float(intensity_arr[0]), 2),
            "flame_length_m": round(float(flame_len_arr[0]), 2),
            "mode": mode,
        }

    def _load_terrain_window(
        self, lat: float, lon: float, grid_size: int = _GRID_SIZE
    ) -> tuple[dict[str, np.ndarray], Any]:
        """Extract a (grid_size × grid_size) terrain window centred on (lat, lon).

        Returns terrain_dict with ``slope``, ``aspect``, optionally
        ``non_burnable`` (float32, shape grid_size²) and an ``affine.Affine``
        pixel-to-WGS84 transform.  Falls back to flat terrain on any error.
        """
        half = grid_size // 2

        # Fallback: analytic affine transform from lat/lon + 30 m pixel size
        pixel_deg_lon = _DX / (111_320.0 * math.cos(math.radians(lat)))
        pixel_deg_lat = _DY / 111_320.0
        from affine import Affine  # always present (rasterio dependency)

        fallback_transform = Affine(
            pixel_deg_lon, 0.0, lon - half * pixel_deg_lon,
            0.0, -pixel_deg_lat, lat + half * pixel_deg_lat,
        )
        flat_terrain = {
            "slope": np.zeros((grid_size, grid_size), dtype=np.float32),
            "aspect": np.zeros((grid_size, grid_size), dtype=np.float32),
        }

        try:
            import rasterio  # noqa: PLC0415
            from rasterio.windows import Window  # noqa: PLC0415

            def _read_window(path: Path) -> tuple[np.ndarray, Any] | None:
                if not path.exists():
                    return None
                with rasterio.open(path) as ds:
                    row, col = ds.index(lon, lat)
                    # Clamp window to valid raster extent
                    col0 = max(0, min(col - half, ds.width - grid_size))
                    row0 = max(0, min(row - half, ds.height - grid_size))
                    win = Window(col0, row0, grid_size, grid_size)
                    data = ds.read(1, window=win).astype(np.float32)
                    return data, ds.window_transform(win)

            slope_result = _read_window(_SLOPE_PATH)
            aspect_result = _read_window(_ASPECT_PATH)

            if slope_result is None or aspect_result is None:
                log.warning(
                    "Terrain rasters not found at fire location (%.4f, %.4f) — "
                    "using flat terrain fallback.",
                    lat, lon,
                )
                return flat_terrain, fallback_transform

            slope_data, raster_transform = slope_result
            aspect_data, _ = aspect_result
            terrain_dict: dict[str, np.ndarray] = {
                "slope": slope_data,
                "aspect": aspect_data,
            }

            # Non-burnable mask: non-forest pixels block spread
            forest_result = _read_window(_FOREST_MASK_PATH)
            if forest_result is not None:
                forest_mask, _ = forest_result
                terrain_dict["non_burnable"] = (forest_mask == 0).astype(np.float32)

            return terrain_dict, raster_transform

        except Exception as exc:
            log.warning(
                "Terrain loading failed for (%.4f, %.4f): %s — using flat fallback.",
                lat, lon, exc,
            )
            return flat_terrain, fallback_transform

    @staticmethod
    def _initial_phi(
        grid_size: int = _GRID_SIZE, radius_px: int = _INITIAL_RADIUS_PX
    ) -> np.ndarray:
        """Signed-distance-function seeded with a small circular fire at grid centre.
        Pixels with phi <= 0 are burned.
        """
        cy, cx = grid_size // 2, grid_size // 2
        jj, ii = np.ogrid[:grid_size, :grid_size]
        phi = np.sqrt((ii - cx) ** 2 + (jj - cy) ** 2).astype(np.float32) - radius_px
        return phi

    @staticmethod
    def _weather_to_sim_dict(
        weather: dict[str, Any], grid_size: int = _GRID_SIZE
    ) -> dict[str, Any]:
        """Convert weather observation to simulator dict (wind_u/v, fuel_anomaly).

        Wind: meteorological convention wind_u = -speed*sin(dir), wind_v = -speed*cos(dir).
        Fuel anomaly: (rh_pct - 40) / 20 — negative values indicate dry/fire-prone conditions.
        """
        wind_kmh = float(weather.get("wind_kmh", 10.0))
        wind_dir_deg = float(weather.get("wind_dir_deg", _DEFAULT_WIND_DIR_DEG))
        wind_m_s = wind_kmh / 3.6
        dir_rad = math.radians(wind_dir_deg)
        wind_u = -wind_m_s * math.sin(dir_rad)
        wind_v = -wind_m_s * math.cos(dir_rad)

        rh_pct = float(weather.get("rh_pct", 40.0))
        # temp_c and fwi accepted in the input dict but not used in fuel anomaly proxy
        fuel_anomaly_scalar = (rh_pct - 40.0) / 20.0
        fuel_anomaly = np.full(
            (grid_size, grid_size), fuel_anomaly_scalar, dtype=np.float32
        )

        return {
            "wind_u": wind_u,
            "wind_v": wind_v,
            "fuel_anomaly": fuel_anomaly,
        }

    def _run_physics_mode(
        self,
        phi: np.ndarray,
        terrain_dict: dict[str, np.ndarray],
        sim_weather: dict[str, Any],
        ros_m_min: float,
        sim_time_minutes: int,
    ) -> tuple[np.ndarray, float]:
        """Rothermel topographic adjustment + WRF-Fire level-set PDE loop.

        Uses a CFL-adaptive timestep (dt = 0.5 * dx / max_ros_m_s) to keep the
        explicit Godunov scheme stable across the full FRP range.

        Returns (final_phi, peak_ros_m_min).  No neural network required.
        """
        slope = terrain_dict.get("slope", np.zeros_like(phi))
        aspect = terrain_dict.get("aspect", np.zeros_like(phi))
        non_burnable = terrain_dict.get("non_burnable")
        base_ros = np.full_like(phi, ros_m_min, dtype=np.float32)  # m/min

        elapsed_s: float = 0.0
        target_s: float = float(sim_time_minutes) * 60.0
        peak_ros: float = ros_m_min
        step = 0

        while elapsed_s < target_s:
            dy_phi, dx_phi = np.gradient(phi, _DY, _DX)
            spread_dir = np.arctan2(dy_phi, dx_phi)

            ros_topo = self._physics.calculate_topographic_ros(
                base_ros, slope, aspect, spread_dir
            )  # m/min

            if non_burnable is not None:
                # Reduce (not zero) ROS in non-forest: grass/shrub/crop can still
                # carry fire at ~10% of forest rate (important since forest mask
                # covers only ~8% of the Guna landscape).
                ros_topo = np.where(non_burnable == 1, ros_topo * 0.1, ros_topo)

            peak_ros = max(peak_ros, float(ros_topo.max()))

            # CFL-adaptive dt: dt = 0.5 * dx / max_ros_m_s (clamp 1 s – 300 s)
            max_ros_m_s = max(float(ros_topo.max()) / 60.0, 1e-6)
            dt_s = float(np.clip(0.5 * _DX / max_ros_m_s, 1.0, 300.0))
            # Do not overshoot target time
            dt_s = min(dt_s, target_s - elapsed_s)

            phi = FireEventTracker.level_set_advance(
                phi=phi, R_f=ros_topo / 60.0, dt=dt_s, dx=_DX, dy=_DY
            )
            # Guard against NaN/Inf from extreme gradient values near boundaries
            phi = np.where(np.isfinite(phi), phi, np.float32(1e6))

            elapsed_s += dt_s
            step += 1
            if step % 500 == 0:
                log.debug(
                    "Physics elapsed %.1f / %.1f min — burned: %d px",
                    elapsed_s / 60.0, sim_time_minutes, int((phi <= 0).sum()),
                )

        return phi, peak_ros

    def _run_cnn_mode(
        self,
        phi: np.ndarray,
        terrain_dict: dict[str, np.ndarray],
        sim_weather: dict[str, Any],
        ros_m_min: float,
        sim_time_minutes: int,
    ) -> tuple[np.ndarray, float]:
        """CNN-assisted solver via Muhurta2DSimulator.

        Returns (final_phi, max_ros_m_min).  Falls back to physics mode
        automatically if the simulator cannot be initialised or raises.
        """
        if self._simulator is None:
            try:
                from src.analysis.simulator import Muhurta2DSimulator  # noqa: PLC0415

                self._simulator = Muhurta2DSimulator(
                    model_path=str(self._model_path) if self._model_path else None,
                    device=self._device,
                )
            except Exception as exc:
                log.warning(
                    "Could not initialise Muhurta2DSimulator (%s) — "
                    "falling back to physics mode.",
                    exc,
                )
                return self._run_physics_mode(
                    phi, terrain_dict, sim_weather, ros_m_min, sim_time_minutes
                )

        try:
            final_phi, ros_field = self._simulator.simulate_spread(
                initial_phi=phi,
                terrain_dict=terrain_dict,
                weather_dict=sim_weather,
                sim_time_minutes=sim_time_minutes,
                dt_minutes=1.0,
                dx=_DX,
                dy=_DY,
            )
            return final_phi, float(ros_field.max()) * 60.0
        except Exception as exc:
            log.warning("CNN simulation failed (%s) — falling back to physics.", exc)
            return self._run_physics_mode(
                phi, terrain_dict, sim_weather, ros_m_min, sim_time_minutes
            )

    @staticmethod
    def _phi_to_geojson(
        phi: np.ndarray,
        transform: Any,
        simplify_tol: float = _SIMPLIFY_TOL_DEG,
    ) -> dict[str, Any]:
        """Convert burned mask (phi <= 0) to a simplified GeoJSON geometry in WGS-84.

        Uses rasterio.features.shapes for vectorisation then shapely for union
        and simplification.  Returns ``{"type": "Polygon", "coordinates": []}``
        if no pixels are burned or vectorisation fails.
        """
        burned_mask = (phi <= 0).astype(np.uint8)
        if burned_mask.sum() == 0:
            return {"type": "Polygon", "coordinates": []}

        try:
            import rasterio.features  # noqa: PLC0415
            from shapely.geometry import mapping, shape  # noqa: PLC0415
            from shapely.ops import unary_union  # noqa: PLC0415

            polys = [
                shape(geom)
                for geom, val in rasterio.features.shapes(
                    burned_mask, transform=transform
                )
                if val == 1
            ]
            if not polys:
                return {"type": "Polygon", "coordinates": []}

            merged = unary_union(polys)
            simplified = merged.simplify(simplify_tol, preserve_topology=True)
            return dict(mapping(simplified))

        except Exception as exc:
            log.warning("Polygon conversion failed: %s — returning empty geometry.", exc)
            return {"type": "Polygon", "coordinates": []}

    @staticmethod
    def _area_ha(phi: np.ndarray) -> float:
        """Burned area in hectares (each 30 m pixel = 0.09 ha)."""
        burned_pixels = int((phi <= 0).sum())
        return burned_pixels * 0.09  # 30 m × 30 m / 10_000 m²/ha
