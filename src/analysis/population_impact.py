"""
Population Smoke Impact Estimator
==================================
Estimates PM2.5 smoke plume exposure on nearby settlements for an active fire
event using the Gaussian plume model from ``src.analysis.smoke_dispersion``.

Part of the Van Suraksha Phase 5 integration.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

# PM2.5 exposure thresholds (ug/m3) — US EPA AQI breakpoints
_PM25_GOOD = 35.0
_PM25_MODERATE = 100.0
_PM25_UNHEALTHY = 250.0

# Footprint contour threshold and spatial constants
_FOOTPRINT_THRESHOLD_UG_M3 = _PM25_GOOD
_MAX_RANGE_M = 50_000.0        # 50 km search radius
_FOOTPRINT_STEP_M = 100.0      # downwind sampling interval
_DEFAULT_POPULATION = 500      # crude estimate per beat centroid

_HEALTH_ADVISORIES: dict[str, str] = {
    "Good": "Air quality acceptable; no restrictions.",
    "Moderate": "Sensitive groups should reduce prolonged outdoor activity.",
    "Unhealthy": "Avoid outdoor activity; keep windows closed.",
    "Hazardous": "Emergency: stay indoors, use masks, evacuate if possible.",
}


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _fire_to_wind_coords(
    fire_lat: float,
    fire_lon: float,
    point_lat: float,
    point_lon: float,
    wind_dir_deg: float,
) -> tuple[float, float]:
    """Convert a lat/lon point to (downwind, crosswind) metres relative to fire.

    Args:
        fire_lat: Fire latitude (degrees N).
        fire_lon: Fire longitude (degrees E).
        point_lat: Settlement latitude (degrees N).
        point_lon: Settlement longitude (degrees E).
        wind_dir_deg: Meteorological wind direction (0 = N, 90 = E, clockwise).

    Returns:
        ``(x_downwind, y_crosswind)`` in metres.
    """
    fire_lat_rad = math.radians(fire_lat)
    dx = (point_lon - fire_lon) * 111_320.0 * math.cos(fire_lat_rad)
    dy = (point_lat - fire_lat) * 111_320.0
    wind_rad = math.radians(wind_dir_deg)
    x_downwind = dx * math.sin(wind_rad) + dy * math.cos(wind_rad)
    y_crosswind = dx * math.cos(wind_rad) - dy * math.sin(wind_rad)
    return x_downwind, y_crosswind


def _wind_to_geo_coords(
    fire_lat: float,
    fire_lon: float,
    x_downwind: float,
    y_crosswind: float,
    wind_dir_deg: float,
) -> tuple[float, float]:
    """Inverse of :func:`_fire_to_wind_coords` — back to lat/lon.

    Args:
        fire_lat: Fire latitude (degrees N).
        fire_lon: Fire longitude (degrees E).
        x_downwind: Downwind distance (metres).
        y_crosswind: Crosswind distance (metres).
        wind_dir_deg: Meteorological wind direction.

    Returns:
        ``(lat, lon)`` in degrees.
    """
    wind_rad = math.radians(wind_dir_deg)
    dx = x_downwind * math.sin(wind_rad) + y_crosswind * math.cos(wind_rad)
    dy = x_downwind * math.cos(wind_rad) - y_crosswind * math.sin(wind_rad)
    fire_lat_rad = math.radians(fire_lat)
    lat = fire_lat + dy / 111_320.0
    lon = fire_lon + dx / (111_320.0 * math.cos(fire_lat_rad))
    return lat, lon


# ---------------------------------------------------------------------------
# Settlement loader
# ---------------------------------------------------------------------------

def _load_settlements_from_file(path: Path) -> list[dict[str, Any]]:
    """Load settlements from a JSON file.

    Expected format: list of ``{name, lat, lon, population_est}`` dicts.
    """
    with path.open() as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"settlements.json must be a JSON array, got {type(data)}")
    required = {"name", "lat", "lon", "population_est"}
    for i, rec in enumerate(data):
        missing = required - rec.keys()
        if missing:
            raise ValueError(f"Settlement record {i} missing keys: {missing}")
    return data


def _load_settlements_from_beats(geojson_path: Path) -> list[dict[str, Any]]:
    """Derive one settlement per beat from beat polygon centroids.

    Uses the mean coordinate of all vertices for each unique (BEAT, RANGE) pair.
    Population is set to :data:`_DEFAULT_POPULATION` for every centroid.

    Args:
        geojson_path: Path to ``gunafinal.geojson`` (747 features, 139 beats).

    Returns:
        List of settlement dicts.
    """
    with geojson_path.open() as fh:
        gj = json.load(fh)

    beat_coords: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)

    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        beat = str(props.get("BEAT", "UNKNOWN")).strip()
        rng = str(props.get("RANGE", "UNKNOWN")).strip()
        geom = feat.get("geometry", {})
        geom_type = geom.get("type", "")

        rings: list[list[list[float]]] = []
        if geom_type == "Polygon":
            rings = geom.get("coordinates", [])
        elif geom_type == "MultiPolygon":
            for poly in geom.get("coordinates", []):
                rings.extend(poly)

        for ring in rings:
            for coord in ring:
                beat_coords[(beat, rng)].append((coord[1], coord[0]))  # (lat, lon)

    settlements: list[dict[str, Any]] = []
    for (beat, rng), coords in sorted(beat_coords.items()):
        mean_lat = sum(c[0] for c in coords) / len(coords)
        mean_lon = sum(c[1] for c in coords) / len(coords)
        settlements.append(
            {
                "name": f"{beat} ({rng})",
                "lat": round(mean_lat, 6),
                "lon": round(mean_lon, 6),
                "population_est": _DEFAULT_POPULATION,
            }
        )

    logger.info("Derived %d settlement centroids from beat GeoJSON.", len(settlements))
    return settlements


# ---------------------------------------------------------------------------
# Main estimator
# ---------------------------------------------------------------------------

class SmokeImpactEstimator:
    """Estimates PM2.5 smoke exposure on nearby settlements for a fire event.

    On construction the estimator loads settlement locations.  If
    ``data/aoi/settlements.json`` exists it is used directly; otherwise beat
    centroids from ``data/aoi/gunafinal.geojson`` are used as proxy villages
    (population_est = 500 per beat).

    Example::

        estimator = SmokeImpactEstimator()
        result = estimator.estimate_impact(
            fire_lat=24.35, fire_lon=77.12,
            frp_mw=120.0,
            wind_speed_ms=5.0,
            wind_dir_deg=225.0,
        )
        print(result["total_population_exposed"])
    """

    def __init__(self) -> None:
        self._settlements: list[dict[str, Any]] = self._load_settlements()

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _load_settlements(self) -> list[dict[str, Any]]:
        explicit = ROOT / "data" / "aoi" / "settlements.json"
        if explicit.exists():
            try:
                settlements = _load_settlements_from_file(explicit)
                logger.info("Loaded %d settlements from %s.", len(settlements), explicit)
                return settlements
            except Exception as exc:
                logger.warning("Could not parse %s (%s); falling back to beats.", explicit, exc)

        beats_geojson = ROOT / "data" / "aoi" / "gunafinal.geojson"
        if not beats_geojson.exists():
            raise FileNotFoundError(
                f"No settlements file found and beat GeoJSON missing: {beats_geojson}"
            )
        return _load_settlements_from_beats(beats_geojson)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_impact(
        self,
        fire_lat: float,
        fire_lon: float,
        frp_mw: float,
        wind_speed_ms: float,
        wind_dir_deg: float,
        stability_class: str = "D",
    ) -> dict[str, Any]:
        """Estimate smoke impact on settlements downwind of a fire.

        Args:
            fire_lat: Fire latitude (degrees N).
            fire_lon: Fire longitude (degrees E).
            frp_mw: Fire Radiative Power (MW).
            wind_speed_ms: Wind speed at 10 m height (m/s).
            wind_dir_deg: Meteorological wind direction (0 = N, 90 = E, clockwise).
            stability_class: Pasquill-Gifford stability class (A–F, default D).

        Returns:
            Impact summary dict — see module docstring for schema.
        """
        from src.analysis.smoke_dispersion import (  # lazy import
            estimate_emission_rate_from_frp,
            gaussian_plume_concentration,
        )

        Q = estimate_emission_rate_from_frp(frp_mw)
        H = 50.0 + frp_mw * 0.5  # effective plume height (m)

        affected: list[dict[str, Any]] = []
        for settlement in self._settlements:
            s_lat = settlement["lat"]
            s_lon = settlement["lon"]

            dist_m = math.sqrt(
                ((s_lat - fire_lat) * 111_320.0) ** 2
                + ((s_lon - fire_lon) * 111_320.0 * math.cos(math.radians(fire_lat))) ** 2
            )
            if dist_m > _MAX_RANGE_M:
                continue

            x_dw, y_cw = _fire_to_wind_coords(fire_lat, fire_lon, s_lat, s_lon, wind_dir_deg)
            if x_dw <= 0.0:
                continue  # upwind — no exposure

            pm25 = gaussian_plume_concentration(
                x=x_dw, y=y_cw, z=2.0,
                Q=Q, u=wind_speed_ms, H=H,
                stability_class=stability_class,
            )
            if pm25 < 10.0:
                continue

            exposure_class = self._classify_exposure(pm25)
            affected.append(
                {
                    "name": settlement["name"],
                    "lat": s_lat,
                    "lon": s_lon,
                    "distance_km": round(dist_m / 1_000.0, 2),
                    "pm25_ug_m3": round(pm25, 2),
                    "exposure_class": exposure_class,
                    "health_advisory": _HEALTH_ADVISORIES[exposure_class],
                    "population_est": settlement["population_est"],
                }
            )

        affected.sort(key=lambda r: r["pm25_ug_m3"], reverse=True)

        max_pm25 = max((r["pm25_ug_m3"] for r in affected), default=0.0)
        total_pop = sum(r["population_est"] for r in affected)
        plume_reach_km = self._compute_plume_reach(
            Q=Q, wind_speed_ms=wind_speed_ms, H=H, stability_class=stability_class
        )
        footprint = self._build_footprint_polygon(
            fire_lat=fire_lat, fire_lon=fire_lon,
            Q=Q, wind_speed_ms=wind_speed_ms, H=H,
            stability_class=stability_class,
            wind_dir_deg=wind_dir_deg,
            reach_m=plume_reach_km * 1_000.0,
        )

        logger.info(
            "Fire (%.4fN, %.4fE) FRP=%.1f MW: %d settlements affected, "
            "pop=%d, max_PM2.5=%.1f ug/m3, reach=%.1f km.",
            fire_lat, fire_lon, frp_mw, len(affected), total_pop, max_pm25, plume_reach_km,
        )

        return {
            "fire_lat": fire_lat,
            "fire_lon": fire_lon,
            "emission_rate_ug_s": round(Q, 2),
            "plume_height_m": round(H, 1),
            "plume_footprint": footprint,
            "affected_settlements": affected,
            "total_population_exposed": total_pop,
            "max_pm25_ug_m3": round(max_pm25, 2),
            "plume_reach_km": round(plume_reach_km, 2),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_exposure(pm25: float) -> str:
        if pm25 < _PM25_GOOD:
            return "Good"
        if pm25 < _PM25_MODERATE:
            return "Moderate"
        if pm25 < _PM25_UNHEALTHY:
            return "Unhealthy"
        return "Hazardous"

    @staticmethod
    def _compute_plume_reach(
        Q: float,
        wind_speed_ms: float,
        H: float,
        stability_class: str,
    ) -> float:
        """Return max downwind distance (km) where centreline PM2.5 > threshold."""
        from src.analysis.smoke_dispersion import gaussian_plume_concentration  # lazy

        reach_m = 0.0
        x = _FOOTPRINT_STEP_M
        while x <= _MAX_RANGE_M:
            conc = gaussian_plume_concentration(
                x=x, y=0.0, z=2.0, Q=Q, u=wind_speed_ms, H=H,
                stability_class=stability_class,
            )
            if conc >= _FOOTPRINT_THRESHOLD_UG_M3:
                reach_m = x
            elif reach_m > 0.0:
                break  # concentrations monotonically decrease past peak
            x += _FOOTPRINT_STEP_M
        return reach_m / 1_000.0

    @staticmethod
    def _crosswind_half_width(
        x: float,
        Q: float,
        wind_speed_ms: float,
        H: float,
        stability_class: str,
    ) -> float:
        """Binary-search for y where PM2.5 drops to footprint threshold at distance x.

        Returns crosswind half-width in metres (0 if centreline is below threshold).
        """
        from src.analysis.smoke_dispersion import gaussian_plume_concentration  # lazy

        centreline = gaussian_plume_concentration(
            x=x, y=0.0, z=2.0, Q=Q, u=wind_speed_ms, H=H,
            stability_class=stability_class,
        )
        if centreline < _FOOTPRINT_THRESHOLD_UG_M3:
            return 0.0

        lo, hi = 0.0, x  # half-width cannot exceed downwind distance
        for _ in range(40):  # 40 bisection iterations ~ 1e-12 relative error
            mid = (lo + hi) / 2.0
            conc = gaussian_plume_concentration(
                x=x, y=mid, z=2.0, Q=Q, u=wind_speed_ms, H=H,
                stability_class=stability_class,
            )
            if conc > _FOOTPRINT_THRESHOLD_UG_M3:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    def _build_footprint_polygon(
        self,
        fire_lat: float,
        fire_lon: float,
        Q: float,
        wind_speed_ms: float,
        H: float,
        stability_class: str,
        wind_dir_deg: float,
        reach_m: float,
    ) -> dict[str, Any]:
        """Build a GeoJSON Polygon tracing the PM2.5 > 35 ug/m3 plume boundary.

        Samples the crosswind half-width every 100 m downwind, constructs the
        left and right boundary arcs, and closes the polygon at the fire origin.
        """
        right_edge: list[tuple[float, float]] = []  # (lat, lon)
        left_edge: list[tuple[float, float]] = []

        if reach_m < _FOOTPRINT_STEP_M:
            # Degenerate — return a point polygon at the fire location
            return {
                "type": "Polygon",
                "coordinates": [[[fire_lon, fire_lat]] * 4],
            }

        x = _FOOTPRINT_STEP_M
        while x <= reach_m + _FOOTPRINT_STEP_M:
            hw = self._crosswind_half_width(x, Q, wind_speed_ms, H, stability_class)
            lat_r, lon_r = _wind_to_geo_coords(fire_lat, fire_lon, x, hw, wind_dir_deg)
            lat_l, lon_l = _wind_to_geo_coords(fire_lat, fire_lon, x, -hw, wind_dir_deg)
            right_edge.append((lat_r, lon_r))
            left_edge.append((lat_l, lon_l))
            x += _FOOTPRINT_STEP_M

        # Build ring: right edge forward, left edge reversed, close at origin
        ring: list[list[float]] = [[fire_lon, fire_lat]]
        for lat, lon in right_edge:
            ring.append([lon, lat])
        for lat, lon in reversed(left_edge):
            ring.append([lon, lat])
        ring.append([fire_lon, fire_lat])  # close

        return {"type": "Polygon", "coordinates": [ring]}
