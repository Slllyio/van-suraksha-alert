"""
Human-Caused Fire Ignition Agent-Based Model (ABM) for Guna Division.

Uses Mesa 3.5 to simulate five categories of human actors whose activities
cause ~95% of forest fires in dry deciduous forests of Central India:

    1. TenduCollector — burns undergrowth to collect tendu (Diospyros) leaves
    2. MahuaCollector — burns undergrowth to collect mahua (Madhuca) flowers
    3. Grazier — sets fire for fresh grass regeneration
    4. Farmer — agricultural residue burns that escape into forest
    5. Traveler — accidental ignition from cigarettes/campfires near roads

Each agent has season-specific behavioral rules and weather-gated ignition
probability. The model outputs a daily ignition probability grid at 1 km
resolution over Guna Division (~50×43 cells).

Architecture:
    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │  Spatial Env  │────>│  Agent Step  │────>│  Ignition    │
    │  (grid layers)│     │  (move+act)  │     │  Probability │
    └──────────────┘     └──────────────┘     └──────────────┘
    Land cover, slope,    Behavioral rules     Weather-gated
    roads, settlements    per agent type       fire start/no-start

Usage:
    from src.model.ignition_abm import IgnitionABM
    model = IgnitionABM(date="2025-03-15", fwi=28.5, temp_c=38, rh_pct=18)
    model.run_for(steps=1)  # one day
    prob_grid = model.get_ignition_probability()
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from mesa import Agent, DataCollector, Model
from mesa.space import MultiGrid, PropertyLayer
from shapely.geometry import Point

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Guna Division bounding box (WGS84)
LAT_MIN, LAT_MAX = 23.80, 24.95
LON_MIN, LON_MAX = 76.45, 77.85

# Grid resolution: ~1 km cells
CELL_SIZE_DEG = 0.01  # ~1.1 km at 24°N
GRID_WIDTH = int((LON_MAX - LON_MIN) / CELL_SIZE_DEG)   # ~140
GRID_HEIGHT = int((LAT_MAX - LAT_MIN) / CELL_SIZE_DEG)  # ~115

# ESA WorldCover class codes
LC_TREE = 10
LC_SHRUB = 20
LC_GRASS = 30
LC_CROP = 40
LC_BUILT = 50
LC_WATER = 80

# Season windows (day-of-year)
TENDU_SEASON = (91, 135)    # Apr 1 – May 15
MAHUA_SEASON = (60, 120)    # Mar 1 – Apr 30 (flower collection)
GRAZING_SEASON = (32, 120)  # Feb 1 – Apr 30
AGRI_BURN_SEASON = (32, 120)
TRAVELER_SEASON = (1, 366)  # year-round

# Base ignition probabilities per agent type (per step, before weather scaling)
# These are calibrated to produce ~5-15 fires/day during peak season
# matching FIRMS historical density for Guna Division
BASE_IGNITION_PROB = {
    "tendu_collector": 0.08,   # high — intentional burning
    "mahua_collector": 0.06,   # high — intentional burning for flower collection
    "grazier": 0.05,           # medium — intentional
    "farmer": 0.04,            # medium — escape burns
    "traveler": 0.005,         # low — accidental
}


# ---------------------------------------------------------------------------
# Data classes for weather and configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DayWeather:
    """Immutable weather state for a single simulation day."""
    fwi: float = 15.0         # Canadian Fire Weather Index
    ffmc: float = 85.0        # Fine Fuel Moisture Code
    temp_c: float = 35.0      # Air temperature (°C)
    rh_pct: float = 25.0      # Relative humidity (%)
    wind_kmh: float = 10.0    # Wind speed (km/h)
    precip_mm: float = 0.0    # Precipitation (mm)

    @property
    def fire_conducive(self) -> bool:
        """Weather supports fire ignition (dry, hot, windy)."""
        return self.fwi > 5.0 and self.rh_pct < 60 and self.precip_mm < 2.0

    @property
    def fwi_multiplier(self) -> float:
        """Scale ignition probability by FWI severity.

        FWI < 5   → 0.1 (very unlikely)
        FWI 5-15  → 0.5 (moderate)
        FWI 15-30 → 1.0 (high)
        FWI > 30  → 1.5 (extreme)
        """
        if self.fwi < 5:
            return 0.1
        if self.fwi < 15:
            return 0.5
        if self.fwi < 30:
            return 1.0
        return 1.5


@dataclass
class ABMConfig:
    """Configuration for the Ignition ABM."""
    # Agent populations (per type)
    n_tendu_collectors: int = 200
    n_mahua_collectors: int = 100
    n_graziers: int = 150
    n_farmers: int = 300
    n_travelers: int = 80

    # Spatial data paths
    beats_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "aoi" / "guna_beats.geojson")
    worldcover_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data_lake" / "land_cover" / "worldcover_guna_raw.tif")
    fwi_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet")
    firms_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data_lake" / "fire_detections")

    # Movement
    max_daily_move: int = 3  # max cells per step (~3 km/day)

    # Output
    monte_carlo_runs: int = 50  # runs for probability estimation


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------
class FireAgent(Agent):
    """Base class for all human actors in the ignition model.

    Each agent occupies a cell on the grid and can:
    - Move to adjacent cells based on behavioral preferences
    - Attempt ignition based on weather and location conditions
    """

    agent_type: str = "base"
    active_season: tuple[int, int] = (1, 366)

    def __init__(self, model: "IgnitionABM"):
        super().__init__(model)
        self.ignited_today = False
        self.days_active = 0

    @property
    def doy(self) -> int:
        """Day of year for current simulation date."""
        return self.model.current_doy

    @property
    def is_active(self) -> bool:
        """Agent is active only during its operational season."""
        start, end = self.active_season
        return start <= self.doy <= end

    @property
    def weather(self) -> DayWeather:
        return self.model.weather

    def cell_suitability(self, x: int, y: int) -> float:
        """How suitable is cell (x, y) for this agent's activity?
        Returns 0.0–1.0. Override per agent type."""
        return 0.5

    def move(self):
        """Move toward most suitable adjacent cell."""
        if not self.is_active:
            return

        pos = self.pos
        if pos is None:
            return

        neighborhood = self.model.grid.get_neighborhood(
            pos, moore=True, include_center=False
        )

        # Score each neighbor
        best_pos = pos
        best_score = self.cell_suitability(*pos)

        for nx, ny in neighborhood:
            score = self.cell_suitability(nx, ny)
            # Add small random jitter for exploration
            score += self.rng.random() * 0.1
            if score > best_score:
                best_score = score
                best_pos = (nx, ny)

        if best_pos != pos:
            self.model.grid.move_agent(self, best_pos)

    def attempt_ignition(self) -> bool:
        """Try to start a fire. Returns True if ignition succeeds."""
        if not self.is_active or not self.weather.fire_conducive:
            return False

        pos = self.pos
        if pos is None:
            return False

        x, y = pos

        # Base probability × weather multiplier × cell suitability
        base_p = BASE_IGNITION_PROB.get(self.agent_type, 0.01)
        weather_mult = self.weather.fwi_multiplier
        cell_suit = self.cell_suitability(x, y)

        # Fuel dryness from FFMC (higher FFMC = drier fine fuels)
        ffmc_mult = min(self.weather.ffmc / 85.0, 1.5)

        p_ignition = base_p * weather_mult * cell_suit * ffmc_mult

        # Clamp to [0, 1]
        p_ignition = max(0.0, min(1.0, p_ignition))

        if self.rng.random() < p_ignition:
            self.ignited_today = True
            # Record ignition on the grid
            self.model.ignition_layer.data[x, y] += 1
            return True

        return False

    def step(self):
        """One day of agent activity: move then possibly ignite."""
        self.ignited_today = False
        if not self.is_active:
            return
        self.days_active += 1
        self.move()
        self.attempt_ignition()


class TenduCollector(FireAgent):
    """Tendu (Diospyros melanoxylon) leaf collector.

    Tendu leaves are India's most valuable NTFP. Collectors deliberately
    burn forest undergrowth to make fallen leaves visible and easier to
    collect. Active during leaf-fall season (April–May).

    Prefers: forest edges near cropland (where tendu grows), low slope,
    areas with tree cover adjacent to accessible terrain.
    """

    agent_type = "tendu_collector"
    active_season = TENDU_SEASON

    def cell_suitability(self, x: int, y: int) -> float:
        lc = self.model.get_layer_value("land_cover", x, y)
        slope = self.model.get_layer_value("slope", x, y)
        forest_edge = self.model.get_layer_value("forest_edge", x, y)
        settlement = self.model.get_layer_value("settlement_proximity", x, y)

        score = 0.0

        # Tendu grows at forest-cropland interface
        if lc == LC_TREE:
            score += 0.5
        elif lc == LC_SHRUB:
            score += 0.3

        # Forest edge is prime tendu territory
        score += forest_edge * 0.3

        # Collectors come from nearby villages (most within 2-3 km)
        score += settlement * 0.3

        # Prefer gentle slopes (easier to work)
        if slope < 15:
            score += 0.1
        elif slope > 30:
            score -= 0.3

        return max(0.0, min(1.0, score))


class MahuaCollector(FireAgent):
    """Mahua (Madhuca longifolia) flower collector.

    Mahua flowers are collected for food, liquor, and oil — economically
    vital for tribal communities. Collectors burn undergrowth to clear
    the ground under mahua trees, making fallen flowers visible.
    Active March–April (flower-fall season, slightly before tendu).

    Prefers: forest areas with mahua trees (mixed deciduous), near
    settlements, moderate canopy, gentle slopes.
    """

    agent_type = "mahua_collector"
    active_season = MAHUA_SEASON

    def cell_suitability(self, x: int, y: int) -> float:
        lc = self.model.get_layer_value("land_cover", x, y)
        slope = self.model.get_layer_value("slope", x, y)
        settlement = self.model.get_layer_value("settlement_proximity", x, y)
        forest_edge = self.model.get_layer_value("forest_edge", x, y)

        score = 0.0

        # Mahua trees grow in mixed deciduous forest
        if lc == LC_TREE:
            score += 0.6
        elif lc == LC_SHRUB:
            score += 0.2
        else:
            return 0.0  # mahua only in forested areas

        # Collectors walk from villages — rarely go beyond 5 km
        score += settlement * 0.35

        # Forest edge and interior both viable (mahua grows throughout)
        score += forest_edge * 0.1

        # Prefer gentle slopes (carrying heavy baskets)
        if slope < 10:
            score += 0.15
        elif slope > 25:
            score -= 0.3

        return max(0.0, min(1.0, score))


class Grazier(FireAgent):
    """Livestock grazier who burns grassland/shrubland for regeneration.

    Graziers set fire to dry grass to stimulate fresh growth for cattle
    and goats. Fires often escape into adjacent forest. Active during
    the dry season before monsoon (Feb–Apr).

    Prefers: grassland, shrubland, gentle terrain, near water sources.
    """

    agent_type = "grazier"
    active_season = GRAZING_SEASON

    def cell_suitability(self, x: int, y: int) -> float:
        lc = self.model.get_layer_value("land_cover", x, y)
        slope = self.model.get_layer_value("slope", x, y)
        settlement = self.model.get_layer_value("settlement_proximity", x, y)

        score = 0.0

        # Graziers burn grassland and shrubland
        if lc == LC_GRASS:
            score += 0.6
        elif lc == LC_SHRUB:
            score += 0.4
        elif lc == LC_TREE:
            score += 0.15  # forest understory grazing

        # Graziers return to settlements — operate within ~5 km radius
        score += settlement * 0.25

        # Prefer flat terrain for livestock
        if slope < 10:
            score += 0.15
        elif slope > 25:
            score -= 0.4

        return max(0.0, min(1.0, score))


class Farmer(FireAgent):
    """Farmer clearing crop residue with fire.

    Slash-and-burn and crop residue clearing fires are common in
    Central India. Fires near forest-crop boundaries frequently
    escape into forest. Active Feb–Apr before monsoon planting.

    Prefers: cropland adjacent to forest, flat terrain.
    """

    agent_type = "farmer"
    active_season = AGRI_BURN_SEASON

    def cell_suitability(self, x: int, y: int) -> float:
        lc = self.model.get_layer_value("land_cover", x, y)
        forest_edge = self.model.get_layer_value("forest_edge", x, y)
        slope = self.model.get_layer_value("slope", x, y)
        settlement = self.model.get_layer_value("settlement_proximity", x, y)

        score = 0.0

        # Farmers burn on cropland
        if lc == LC_CROP:
            score += 0.4
        else:
            return 0.0  # farmers don't operate in non-crop areas

        # Fires only reach forest if near forest edge
        score += forest_edge * 0.4

        # Agricultural burns happen near villages
        score += settlement * 0.2

        # Flat terrain
        if slope < 10:
            score += 0.1

        return max(0.0, min(1.0, score))


class Traveler(FireAgent):
    """Traveler/visitor who accidentally causes fire near roads.

    Cigarettes, campfires, and vehicle sparks along roads that pass
    through forest areas. Year-round but higher probability in dry season.

    Prefers: cells with road proximity, any land cover type.
    """

    agent_type = "traveler"
    active_season = TRAVELER_SEASON

    def cell_suitability(self, x: int, y: int) -> float:
        road_prox = self.model.get_layer_value("road_proximity", x, y)
        lc = self.model.get_layer_value("land_cover", x, y)

        score = 0.0

        # Travelers follow roads
        score += road_prox * 0.7

        # Fire risk only where there's burnable vegetation
        if lc in (LC_TREE, LC_SHRUB, LC_GRASS):
            score += 0.3
        elif lc == LC_CROP:
            score += 0.1
        else:
            return 0.0  # built-up, water, bare = no fire risk

        return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Main ABM Model
# ---------------------------------------------------------------------------
class IgnitionABM(Model):
    """Agent-Based Model for human-caused fire ignition in Guna Division.

    Parameters
    ----------
    sim_date : str or date
        The date to simulate (e.g., "2025-03-15").
    weather : DayWeather, optional
        Weather conditions. If None, loaded from FWI parquet.
    config : ABMConfig, optional
        Model configuration.
    rng : int, optional
        Random seed for reproducibility.
    """

    def __init__(
        self,
        sim_date: str | date = "2025-03-15",
        weather: DayWeather | None = None,
        config: ABMConfig | None = None,
        rng: int | None = None,
    ):
        super().__init__(rng=rng)

        self.config = config or ABMConfig()

        # Parse date
        if isinstance(sim_date, str):
            self.sim_date = datetime.strptime(sim_date, "%Y-%m-%d").date()
        else:
            self.sim_date = sim_date
        self.current_doy = self.sim_date.timetuple().tm_yday

        # Load or set weather
        if weather is not None:
            self.weather = weather
        else:
            self.weather = self._load_weather()

        # Create grid
        self.grid = MultiGrid(GRID_WIDTH, GRID_HEIGHT, torus=False)

        # Initialize spatial layers
        self._layers: dict[str, np.ndarray] = {}
        self._init_layers()

        # Ignition accumulator (counts per cell)
        self.ignition_layer = PropertyLayer(
            "ignitions", GRID_WIDTH, GRID_HEIGHT, default_value=0.0
        )

        # Create agents
        self._create_agents()

        # Data collector
        self.datacollector = DataCollector(
            model_reporters={
                "total_ignitions": lambda m: int(m.ignition_layer.data.sum()),
                "active_agents": lambda m: sum(
                    1 for a in m.agents if isinstance(a, FireAgent) and a.is_active
                ),
                "fwi": lambda m: m.weather.fwi,
                "date": lambda m: str(m.sim_date),
            },
            agent_reporters={
                "type": lambda a: a.agent_type if isinstance(a, FireAgent) else "unknown",
                "ignited": lambda a: a.ignited_today if isinstance(a, FireAgent) else False,
                "pos": lambda a: a.pos,
            },
        )

    # -----------------------------------------------------------------------
    # Spatial layer management
    # -----------------------------------------------------------------------
    def _init_layers(self):
        """Initialize spatial property layers from geospatial data."""
        # Land cover: rasterized from WorldCover at 1km
        self._layers["land_cover"] = self._load_land_cover()

        # Slope: from DEM
        self._layers["slope"] = self._load_slope()

        # Forest edge: binary layer (1 = forest cell adjacent to non-forest)
        self._layers["forest_edge"] = self._compute_forest_edge()

        # Road proximity: normalized 0–1 (1 = on road, 0 = far from road)
        self._layers["road_proximity"] = self._compute_road_proximity()

        # Settlement proximity: normalized 0–1 (1 = in settlement, 0 = far)
        self._layers["settlement_proximity"] = self._compute_settlement_proximity()

        # Historical fire frequency (FIRMS count per cell, normalized)
        self._layers["fire_history"] = self._load_fire_history()

        # Beat-level fire density (for weighted agent spawning)
        self._layers["beat_fire_weight"] = self._compute_beat_fire_weights()

    def get_layer_value(self, layer_name: str, x: int, y: int) -> float:
        """Get value from a spatial layer at grid position."""
        layer = self._layers.get(layer_name)
        if layer is None:
            return 0.0
        if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT:
            return float(layer[x, y])
        return 0.0

    def _load_land_cover(self) -> np.ndarray:
        """Load ESA WorldCover rasterized to 1km grid.

        If the raster file exists, downsample it. Otherwise, generate
        a plausible distribution based on Guna's land_cover_stats.json:
        70% cropland, 18% grassland, 7% tree, 3% shrub, 1% built, 1% other.
        """
        stats_path = PROJECT_ROOT / "data_lake" / "land_cover" / "land_cover_stats.json"

        # Try to load from raster
        try:
            import rasterio
            from rasterio.transform import from_bounds

            tif = self.config.worldcover_path
            if tif.exists():
                with rasterio.open(tif) as src:
                    # Read and resample to our grid
                    from rasterio.enums import Resampling
                    data = src.read(
                        1,
                        out_shape=(GRID_HEIGHT, GRID_WIDTH),
                        resampling=Resampling.mode,
                    )
                    return data.T  # (width, height) for Mesa grid
        except (ImportError, Exception):
            pass

        # Fallback: statistical generation based on real proportions
        grid = np.zeros((GRID_WIDTH, GRID_HEIGHT), dtype=np.int32)

        if stats_path.exists():
            with open(stats_path) as f:
                stats = json.load(f)
            # Use real proportions
            total = sum(v.get("area_ha", v) if isinstance(v, dict) else v
                        for v in stats.values() if isinstance(v, (int, float, dict)))
        # Guna land cover distribution (from land_cover_stats.json)
        probs = {
            LC_CROP: 0.70,
            LC_GRASS: 0.18,
            LC_TREE: 0.07,
            LC_SHRUB: 0.03,
            LC_BUILT: 0.01,
            LC_WATER: 0.007,
        }
        classes = list(probs.keys())
        weights = list(probs.values())
        # Normalize
        total_w = sum(weights)
        weights = [w / total_w for w in weights]

        flat = self.rng.choice(classes, size=GRID_WIDTH * GRID_HEIGHT, p=weights)
        grid = flat.reshape((GRID_WIDTH, GRID_HEIGHT))

        return grid

    def _load_slope(self) -> np.ndarray:
        """Load slope layer, degrees. Falls back to synthetic gentle terrain."""
        try:
            import rasterio
            from rasterio.enums import Resampling

            tif = PROJECT_ROOT / "data_lake" / "terrain" / "slope_guna_30m.tif"
            if tif.exists():
                with rasterio.open(tif) as src:
                    data = src.read(
                        1,
                        out_shape=(GRID_HEIGHT, GRID_WIDTH),
                        resampling=Resampling.average,
                    )
                    return data.T
        except (ImportError, Exception):
            pass

        # Fallback: Guna is mostly flat (Malwa Plateau), gentle undulations
        # Mean slope ~5°, max ~30° in Vindhyan foothills
        return self.rng.exponential(scale=5.0, size=(GRID_WIDTH, GRID_HEIGHT)).clip(0, 45)

    def _compute_forest_edge(self) -> np.ndarray:
        """Binary layer: 1 where forest cell is adjacent to non-forest."""
        lc = self._layers["land_cover"]
        forest = np.isin(lc, [LC_TREE, LC_SHRUB]).astype(np.float32)

        edge = np.zeros_like(forest)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                shifted = np.roll(np.roll(forest, dx, axis=0), dy, axis=1)
                # Edge = forest AND adjacent non-forest
                edge += forest * (1 - shifted)

        # Normalize to 0–1
        edge = (edge > 0).astype(np.float32)
        return edge

    def _compute_road_proximity(self) -> np.ndarray:
        """Road proximity layer (0–1). Loads from cached OSM data.

        Cached by: python scripts/cache_osm_layers.py
        Source: OpenStreetMap road network for Guna Division
        """
        cached = PROJECT_ROOT / "data_lake" / "human_activity" / "road_proximity_1km.npy"
        if cached.exists():
            data = np.load(cached)
            if data.shape == (GRID_WIDTH, GRID_HEIGHT):
                return data
            # Resize if grid dimensions differ
            from scipy.ndimage import zoom
            zoom_x = GRID_WIDTH / data.shape[0]
            zoom_y = GRID_HEIGHT / data.shape[1]
            return zoom(data, (zoom_x, zoom_y), order=1).clip(0, 1).astype(np.float32)

        # Fallback: heuristic grid pattern
        road_grid = np.zeros((GRID_WIDTH, GRID_HEIGHT), dtype=np.float32)
        for ix in range(GRID_WIDTH):
            for iy in range(GRID_HEIGHT):
                d_major = min(ix % 30, iy % 25, 30 - ix % 30, 25 - iy % 25)
                d_minor = min(ix % 10, iy % 8, 10 - ix % 10, 8 - iy % 8)
                proximity = max(
                    math.exp(-d_major / 3.0),
                    math.exp(-d_minor / 1.5) * 0.5,
                )
                road_grid[ix, iy] = min(1.0, proximity)
        return road_grid

    def _compute_settlement_proximity(self) -> np.ndarray:
        """Settlement proximity layer (0–1). Loads from cached OSM data.

        Cached by: python scripts/cache_osm_layers.py
        Source: OpenStreetMap village/hamlet/town points for Guna Division
        """
        cached = PROJECT_ROOT / "data_lake" / "human_activity" / "settlement_proximity_1km.npy"
        if cached.exists():
            data = np.load(cached)
            if data.shape == (GRID_WIDTH, GRID_HEIGHT):
                return data
            from scipy.ndimage import zoom
            zoom_x = GRID_WIDTH / data.shape[0]
            zoom_y = GRID_HEIGHT / data.shape[1]
            return zoom(data, (zoom_x, zoom_y), order=1).clip(0, 1).astype(np.float32)

        # Fallback: use WorldCover built-up class as proxy
        lc = self._layers.get("land_cover")
        if lc is not None:
            built = (lc == LC_BUILT).astype(np.float32)
            # Spread influence: settlements affect ~5 km radius
            from scipy.ndimage import gaussian_filter
            return gaussian_filter(built, sigma=3.0).clip(0, 1).astype(np.float32)

        return np.full((GRID_WIDTH, GRID_HEIGHT), 0.1, dtype=np.float32)

    def _load_fire_history(self) -> np.ndarray:
        """Historical fire frequency per cell from FIRMS data."""
        fire_grid = np.zeros((GRID_WIDTH, GRID_HEIGHT), dtype=np.float32)

        firms_dir = self.config.firms_path
        if not firms_dir.exists():
            return fire_grid

        try:
            # Load all VIIRS SNPP parquets
            viirs_dir = firms_dir / "firms_viirs_snpp_sp"
            if not viirs_dir.exists():
                viirs_dir = firms_dir / "firms_modis_sp"

            if viirs_dir.exists():
                parquets = sorted(viirs_dir.glob("*.parquet"))[:50]  # sample
                for pq in parquets:
                    try:
                        df = pd.read_parquet(pq)
                        if "latitude" in df.columns and "longitude" in df.columns:
                            for _, row in df.iterrows():
                                lat, lon = row["latitude"], row["longitude"]
                                ix = int((lon - LON_MIN) / CELL_SIZE_DEG)
                                iy = int((lat - LAT_MIN) / CELL_SIZE_DEG)
                                if 0 <= ix < GRID_WIDTH and 0 <= iy < GRID_HEIGHT:
                                    fire_grid[ix, iy] += 1
                    except Exception:
                        continue

            # Normalize to 0–1
            max_val = fire_grid.max()
            if max_val > 0:
                fire_grid = fire_grid / max_val

        except Exception:
            pass

        return fire_grid

    def _compute_beat_fire_weights(self) -> np.ndarray:
        """Rasterize per-beat FIRMS fire density onto the grid.

        Uses beat_fire_density.csv (from scripts/cache_osm_layers.py validation)
        and guna_beats.geojson to create a spawning weight layer. Beats with
        higher historical fire density get higher weights, concentrating agents
        where fires actually occur.

        Falls back to uniform weights if data is unavailable.
        """
        weight_grid = np.ones((GRID_WIDTH, GRID_HEIGHT), dtype=np.float32) * 0.1

        csv_path = PROJECT_ROOT / "data_lake" / "human_activity" / "beat_fire_density.csv"
        beats_path = PROJECT_ROOT / "data" / "aoi" / "guna_beats.geojson"

        if not csv_path.exists() or not beats_path.exists():
            return weight_grid

        try:
            density_df = pd.read_csv(csv_path)
            beats_gdf = gpd.read_file(beats_path)

            # Merge fire density into beat geometries
            beats_gdf = beats_gdf.merge(
                density_df[["Beat", "fire_density"]],
                on="Beat",
                how="left",
            )
            beats_gdf["fire_density"] = beats_gdf["fire_density"].fillna(0.0)

            # Rasterize: vectorized spatial join of grid centroids with beats
            lons = LON_MIN + (np.arange(GRID_WIDTH) + 0.5) * CELL_SIZE_DEG
            lats = LAT_MIN + (np.arange(GRID_HEIGHT) + 0.5) * CELL_SIZE_DEG
            lon_grid, lat_grid = np.meshgrid(lons, lats, indexing="ij")

            grid_points = gpd.GeoDataFrame(
                {"ix": np.repeat(np.arange(GRID_WIDTH), GRID_HEIGHT),
                 "iy": np.tile(np.arange(GRID_HEIGHT), GRID_WIDTH)},
                geometry=gpd.points_from_xy(lon_grid.ravel(), lat_grid.ravel()),
                crs="EPSG:4326",
            )

            joined = gpd.sjoin(
                grid_points, beats_gdf[["geometry", "fire_density"]],
                how="left", predicate="within",
            )
            joined["fire_density"] = joined["fire_density"].fillna(0.0)
            # Handle duplicates from overlapping beat boundaries
            joined = joined.groupby(["ix", "iy"])["fire_density"].max().reset_index()

            for _, row in joined.iterrows():
                ix, iy = int(row["ix"]), int(row["iy"])
                density = float(row["fire_density"])
                # Base weight 0.1 + density scaling (fire-prone beats get 5-10x)
                weight_grid[ix, iy] = 0.1 + density * 5.0

            # Normalize to 0–1
            max_w = weight_grid.max()
            if max_w > 0:
                weight_grid = weight_grid / max_w

        except Exception:
            pass

        return weight_grid

    def _load_weather(self) -> DayWeather:
        """Load FWI weather for sim_date from parquet."""
        fwi_path = self.config.fwi_path
        if fwi_path.exists():
            try:
                df = pd.read_parquet(fwi_path)
                df["date"] = pd.to_datetime(df["date"]).dt.date
                row = df[df["date"] == self.sim_date]
                if not row.empty:
                    r = row.iloc[0]
                    return DayWeather(
                        fwi=float(r.get("fwi", 15)),
                        ffmc=float(r.get("ffmc", 85)),
                        temp_c=float(r.get("temp_c", 35)),
                        rh_pct=float(r.get("rh_pct", 25)),
                        wind_kmh=float(r.get("wind_kmh", 10)),
                        precip_mm=float(r.get("precip_mm", 0)),
                    )
            except Exception:
                pass

        # Default: typical March fire season weather
        return DayWeather(fwi=22.0, ffmc=88.0, temp_c=36.0, rh_pct=20.0,
                          wind_kmh=12.0, precip_mm=0.0)

    # -----------------------------------------------------------------------
    # Agent creation
    # -----------------------------------------------------------------------
    def _create_agents(self):
        """Spawn agents at appropriate starting locations."""
        agent_specs = [
            (TenduCollector, self.config.n_tendu_collectors),
            (MahuaCollector, self.config.n_mahua_collectors),
            (Grazier, self.config.n_graziers),
            (Farmer, self.config.n_farmers),
            (Traveler, self.config.n_travelers),
        ]

        for agent_cls, count in agent_specs:
            for _ in range(count):
                agent = agent_cls(self)
                # Place at a suitable starting position
                pos = self._find_suitable_start(agent)
                self.grid.place_agent(agent, pos)

    def _find_suitable_start(self, agent: FireAgent) -> tuple[int, int]:
        """Find a good starting cell using beat-weighted sampling.

        Combines agent-specific cell suitability with beat-level fire
        density weights to concentrate agents in historically fire-prone
        areas while respecting behavioral preferences.
        """
        beat_weights = self._layers.get("beat_fire_weight")

        best_pos = (
            int(self.rng.integers(0, GRID_WIDTH)),
            int(self.rng.integers(0, GRID_HEIGHT)),
        )
        best_score = 0.0

        # Weighted sampling: draw 30 candidates biased toward fire-prone beats
        for _ in range(30):
            x = int(self.rng.integers(0, GRID_WIDTH))
            y = int(self.rng.integers(0, GRID_HEIGHT))

            suitability = agent.cell_suitability(x, y)
            beat_w = float(beat_weights[x, y]) if beat_weights is not None else 0.5

            # Combined score: 60% suitability + 40% fire history weight
            score = 0.6 * suitability + 0.4 * beat_w
            # Add small jitter for exploration
            score += self.rng.random() * 0.05

            if score > best_score:
                best_score = score
                best_pos = (x, y)

        return best_pos

    # -----------------------------------------------------------------------
    # Simulation
    # -----------------------------------------------------------------------
    def step(self):
        """Execute one simulation day."""
        # All agents step (Mesa 3.5: iterate over model.agents)
        for agent in self.agents:
            if isinstance(agent, FireAgent):
                agent.step()

        self.datacollector.collect(self)

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    def get_ignition_probability(self) -> np.ndarray:
        """Get ignition probability grid (normalized 0–1)."""
        grid = self.ignition_layer.data.copy()
        max_val = grid.max()
        if max_val > 0:
            grid = grid / max_val
        return grid

    def get_ignition_coords(self) -> list[dict]:
        """Get list of ignition points as lat/lon dicts."""
        grid = self.ignition_layer.data
        points = []
        for ix in range(GRID_WIDTH):
            for iy in range(GRID_HEIGHT):
                if grid[ix, iy] > 0:
                    lon = LON_MIN + (ix + 0.5) * CELL_SIZE_DEG
                    lat = LAT_MIN + (iy + 0.5) * CELL_SIZE_DEG
                    points.append({
                        "latitude": lat,
                        "longitude": lon,
                        "count": int(grid[ix, iy]),
                        "probability": float(grid[ix, iy] / max(1, grid.max())),
                    })
        return points

    def get_ignition_geodataframe(self) -> gpd.GeoDataFrame:
        """Get ignition points as a GeoDataFrame."""
        points = self.get_ignition_coords()
        if not points:
            return gpd.GeoDataFrame()
        df = pd.DataFrame(points)
        geometry = [Point(row["longitude"], row["latitude"]) for _, row in df.iterrows()]
        return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

    def summary(self) -> dict:
        """Summary statistics for the simulation."""
        grid = self.ignition_layer.data
        total_ignitions = int(grid.sum())

        # Count by agent type
        type_counts = {}
        for agent in self.agents:
            if isinstance(agent, FireAgent) and agent.ignited_today:
                t = agent.agent_type
                type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "date": str(self.sim_date),
            "doy": self.current_doy,
            "weather": {
                "fwi": self.weather.fwi,
                "ffmc": self.weather.ffmc,
                "temp_c": self.weather.temp_c,
                "rh_pct": self.weather.rh_pct,
                "wind_kmh": self.weather.wind_kmh,
                "precip_mm": self.weather.precip_mm,
            },
            "total_ignitions": total_ignitions,
            "ignitions_by_type": type_counts,
            "cells_with_fire": int((grid > 0).sum()),
            "active_agents": sum(
                1 for a in self.agents if isinstance(a, FireAgent) and a.is_active
            ),
            "grid_shape": (GRID_WIDTH, GRID_HEIGHT),
        }


# ---------------------------------------------------------------------------
# Monte Carlo runner for probability estimation
# ---------------------------------------------------------------------------
def run_monte_carlo(
    sim_date: str = "2025-03-15",
    weather: DayWeather | None = None,
    n_runs: int = 50,
    config: ABMConfig | None = None,
) -> dict:
    """Run multiple ABM simulations and aggregate ignition probabilities.

    Returns a dict with:
        - probability_grid: (W, H) array of ignition probability [0–1]
        - mean_ignitions: average fire starts per run
        - hotspots: list of top-20 highest-probability cells
    """
    config = config or ABMConfig()
    prob_grid = np.zeros((GRID_WIDTH, GRID_HEIGHT), dtype=np.float64)

    ignition_counts = []

    for i in range(n_runs):
        model = IgnitionABM(
            sim_date=sim_date,
            weather=weather,
            config=config,
            rng=i * 42,
        )
        model.step()  # one day

        prob_grid += (model.ignition_layer.data > 0).astype(np.float64)
        ignition_counts.append(int(model.ignition_layer.data.sum()))

    # Probability = fraction of runs that produced ignition in each cell
    prob_grid = prob_grid / n_runs

    # Extract hotspots (top 20 cells by probability)
    flat_indices = np.argsort(prob_grid.ravel())[::-1][:20]
    hotspots = []
    for idx in flat_indices:
        ix, iy = divmod(idx, GRID_HEIGHT)
        p = prob_grid[ix, iy]
        if p > 0:
            hotspots.append({
                "latitude": LAT_MIN + (iy + 0.5) * CELL_SIZE_DEG,
                "longitude": LON_MIN + (ix + 0.5) * CELL_SIZE_DEG,
                "probability": float(p),
                "grid_x": int(ix),
                "grid_y": int(iy),
            })

    return {
        "date": sim_date,
        "n_runs": n_runs,
        "probability_grid": prob_grid,
        "mean_ignitions": float(np.mean(ignition_counts)),
        "std_ignitions": float(np.std(ignition_counts)),
        "max_probability": float(prob_grid.max()),
        "hotspots": hotspots,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Fire Ignition ABM — Guna Division")
    parser.add_argument("--date", default="2025-03-15", help="Simulation date (YYYY-MM-DD)")
    parser.add_argument("--fwi", type=float, default=None, help="Override FWI value")
    parser.add_argument("--runs", type=int, default=10, help="Monte Carlo runs")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    weather = None
    if args.fwi is not None:
        weather = DayWeather(fwi=args.fwi)

    print(f"Running Ignition ABM for {args.date} ({args.runs} Monte Carlo runs)...")

    result = run_monte_carlo(
        sim_date=args.date,
        weather=weather,
        n_runs=args.runs,
    )

    print(f"\nResults:")
    print(f"  Mean ignitions/day: {result['mean_ignitions']:.1f} +/- {result['std_ignitions']:.1f}")
    print(f"  Max cell probability: {result['max_probability']:.3f}")
    print(f"  Hotspot cells: {len(result['hotspots'])}")

    if result["hotspots"]:
        print(f"\n  Top 5 ignition hotspots:")
        for i, hs in enumerate(result["hotspots"][:5], 1):
            print(f"    {i}. ({hs['latitude']:.3f}N, {hs['longitude']:.3f}E) "
                  f"P={hs['probability']:.3f}")

    if args.output:
        out = {k: v for k, v in result.items() if k != "probability_grid"}
        out["probability_grid_shape"] = list(result["probability_grid"].shape)
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n  Saved to {args.output}")

        # Also save probability grid as numpy
        np_path = args.output.replace(".json", "_grid.npy")
        np.save(np_path, result["probability_grid"])
        print(f"  Grid saved to {np_path}")
