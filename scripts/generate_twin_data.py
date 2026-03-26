"""Generate static assets for the 3D Digital Twin tab.

Usage:
    python scripts/generate_twin_data.py

Outputs:
    dashboard/static/heightmap_guna.png  (1024x1024 16-bit DEM)
    dashboard/static/twin_config.json    (trees, boundaries, metadata)
"""

import json
import random
from pathlib import Path

import geopandas as gpd
import numpy as np
from PIL import Image
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Species ecology configuration
# ---------------------------------------------------------------------------
SPECIES_WEIGHTS = {
    "low": {"teak": 0.60, "tendu": 0.20, "mahua": 0.15, "bamboo": 0.05},
    "mid": {"teak": 0.40, "tendu": 0.25, "mahua": 0.20, "bamboo": 0.15},
    "high": {"teak": 0.20, "tendu": 0.20, "mahua": 0.30, "bamboo": 0.30},
}

SPECIES_COLORS = {
    "teak": "#2d5a27",
    "tendu": "#5a6e30",
    "mahua": "#4a7c3f",
    "bamboo": "#7ab356",
    "shrub": "#8b7d3c",
}


# ===========================================================================
# Task 2: DEM Heightmap Generation
# ===========================================================================


def _normalize_dem(
    dem: np.ndarray, nodata: float = -32768.0
) -> tuple[np.ndarray, float, float]:
    """Mask nodata, normalize to 0-65535 uint16.

    Returns:
        (normalized_array, dem_min, dem_max)
    """
    dem = dem.astype(np.float32)
    dem[dem == nodata] = np.nan

    valid = dem[~np.isnan(dem)]
    if valid.size == 0:
        return np.zeros(dem.shape, dtype=np.uint16), 0.0, 0.0

    dem_min = float(valid.min())
    dem_max = float(valid.max())

    dem_filled = np.nan_to_num(dem, nan=dem_min)

    if dem_max == dem_min:
        return np.zeros_like(dem_filled, dtype=np.uint16), dem_min, dem_max

    dem_norm = ((dem_filled - dem_min) / (dem_max - dem_min) * 65535).astype(
        np.uint16
    )
    return dem_norm, dem_min, dem_max


def generate_heightmap(
    dem_path: str = "data/rasters/dem_30m.tif",
    bounds_path: str = "data/aoi/overlay_bounds.json",
    output_path: str = "dashboard/static/heightmap_guna.png",
    size: int = 1024,
) -> dict:
    """Crop DEM to LULC bounds, normalize, downsample to size x size PNG."""
    import rasterio
    from rasterio.windows import from_bounds

    with open(bounds_path) as f:
        raw = json.load(f)["lulc"]

    # Normalize abbreviated keys (w/s/e/n) to full names
    if "w" in raw and "west" not in raw:
        bounds = {
            "west": raw["w"],
            "south": raw["s"],
            "east": raw["e"],
            "north": raw["n"],
        }
    else:
        bounds = raw

    with rasterio.open(dem_path) as src:
        pixel_size = abs(src.transform.a)
        assert pixel_size < 0.01, (
            f"Expected degree-based CRS, got pixel size {pixel_size}"
        )

        window = from_bounds(
            bounds["west"],
            bounds["south"],
            bounds["east"],
            bounds["north"],
            src.transform,
        )
        dem = src.read(1, window=window)

    nodata_val = -32768.0
    dem_norm, dem_min, dem_max = _normalize_dem(dem, nodata=nodata_val)

    img = Image.fromarray(dem_norm)
    img = img.resize((size, size), Image.BILINEAR)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)

    return {
        "dem_min": dem_min,
        "dem_max": dem_max,
        "bounds": bounds,
        "size": size,
    }


# ===========================================================================
# Task 3: Tree Placement with Poisson Disk Sampling
# ===========================================================================


def _elevation_band(elev: float) -> str:
    """Map elevation to ecological band for species weighting."""
    if elev < 400:
        return "low"
    if elev < 500:
        return "mid"
    return "high"


def _pick_species(elev: float, has_shrub: bool) -> str:
    """Pick a tree species based on elevation band and shrub presence."""
    if has_shrub and random.random() < 0.15:
        return "shrub"
    band = _elevation_band(elev)
    weights = SPECIES_WEIGHTS[band]
    return random.choices(list(weights.keys()), list(weights.values()))[0]


def _poisson_disk_sample(
    polygon, min_dist: float, max_points: int
) -> list[tuple[float, float]]:
    """Sample points within *polygon* with minimum separation *min_dist*.

    Uses rejection sampling with a Poisson-disk constraint.
    """
    from shapely.prepared import prep

    bounds = polygon.bounds
    prepared = prep(polygon)
    points: list[tuple[float, float]] = []
    attempts = 0
    max_attempts = max_points * 30

    while len(points) < max_points and attempts < max_attempts:
        attempts += 1
        x = random.uniform(bounds[0], bounds[2])
        y = random.uniform(bounds[1], bounds[3])
        pt = Point(x, y)
        if not prepared.contains(pt):
            continue
        too_close = False
        for px, py in points:
            if (x - px) ** 2 + (y - py) ** 2 < min_dist**2:
                too_close = True
                break
        if not too_close:
            points.append((x, y))
    return points


def generate_trees(
    geojson_path: str = "data/aoi/gunafinal.geojson",
    lulc_path: str = "data/aoi/compartment_lulc.json",
    terrain_path: str = "data/aoi/compartment_terrain.json",
    max_trees: int = 5000,
    min_dist_deg: float = 0.0005,
) -> list[dict]:
    """Place trees across compartments using Poisson-disk sampling.

    Trees are distributed proportionally to each compartment's tree cover
    percentage, with species chosen by elevation band.
    """
    gdf = gpd.read_file(geojson_path)

    with open(lulc_path) as f:
        lulc_data = json.load(f)
    with open(terrain_path) as f:
        terrain_data = json.load(f)

    tree_pcts: list[float] = []
    for idx in range(len(gdf)):
        lulc = lulc_data.get(str(idx), {})
        tree_pcts.append(lulc.get("tree", 0))

    total_pct = sum(p for p in tree_pcts if p > 15)
    if total_pct == 0:
        return []

    all_trees: list[dict] = []
    for idx, row in gdf.iterrows():
        pct = tree_pcts[idx]
        if pct <= 15:
            continue

        n_trees = max(1, int((pct / total_pct) * max_trees))
        if len(all_trees) + n_trees > max_trees:
            n_trees = max_trees - len(all_trees)
        if n_trees <= 0:
            break

        geom = row.geometry
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)

        points = _poisson_disk_sample(geom, min_dist_deg, n_trees)

        terrain = terrain_data.get(str(idx), {})
        elev = terrain.get("elev", 450)
        lulc = lulc_data.get(str(idx), {})
        has_shrub = lulc.get("shrub", 0) > 10

        for lon, lat in points:
            species = _pick_species(elev, has_shrub)
            all_trees.append(
                {
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                    "species": species,
                    "height": round(random.uniform(0.5, 1.5), 2),
                }
            )

    return all_trees[:max_trees]


# ===========================================================================
# Task 4: Boundary Simplification + Config Assembly
# ===========================================================================


def generate_boundaries(
    geojson_path: str = "data/aoi/gunafinal.geojson",
    lulc_path: str = "data/aoi/compartment_lulc.json",
    tolerance: float = 0.002,
) -> list[dict]:
    """Simplify compartment polygons and attach LULC metadata.

    Returns a list of boundary dicts with beat/range names, simplified
    coordinate rings, and land-use fractions.
    """
    gdf = gpd.read_file(geojson_path)

    with open(lulc_path) as f:
        lulc_data = json.load(f)

    boundaries: list[dict] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)

        simplified = geom.simplify(tolerance, preserve_topology=True)
        coords = [
            [round(c[0], 5), round(c[1], 5)] for c in simplified.exterior.coords
        ]

        lulc = lulc_data.get(str(idx), {})
        beat_name = row.get("BEAT", f"Compartment-{idx}")
        range_name = row.get("RANGE", "Unknown")

        boundaries.append(
            {
                "beat": str(beat_name),
                "range": str(range_name),
                "coords": coords,
                "lulc": {
                    "tree": round(lulc.get("tree", 0), 1),
                    "shrub": round(lulc.get("shrub", 0), 1),
                    "grass": round(lulc.get("grass", 0), 1),
                },
            }
        )
    return boundaries


def generate_config(
    output_path: str = "dashboard/static/twin_config.json",
    heightmap_output_path: str = "dashboard/static/heightmap_guna.png",
    max_trees: int = 5000,
) -> dict:
    """Orchestrate full twin-data generation: heightmap + trees + boundaries.

    Writes a compact JSON config and the heightmap PNG.
    """
    heightmap_meta = generate_heightmap(output_path=heightmap_output_path)
    trees = generate_trees(max_trees=max_trees)
    boundaries = generate_boundaries()

    config = {
        "terrain": {
            "heightmap": "heightmap_guna.png",
            "bounds": heightmap_meta["bounds"],
            "elevation_range": [heightmap_meta["dem_min"], heightmap_meta["dem_max"]],
            "vertical_exaggeration": 2.5,
        },
        "trees": trees,
        "boundaries": boundaries,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(config, f, separators=(",", ":"))

    return config


# ===========================================================================
# CLI entry point
# ===========================================================================

if __name__ == "__main__":
    print("Generating twin data...")
    config = generate_config()
    print(f"  Heightmap: dashboard/static/heightmap_guna.png")
    print(f"  Config: dashboard/static/twin_config.json")
    print(f"  Trees: {len(config['trees'])}")
    print(f"  Boundaries: {len(config['boundaries'])}")
    print(f"  Elevation: {config['terrain']['elevation_range']}")
    print("Done.")
