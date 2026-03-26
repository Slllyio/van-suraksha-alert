"""Generate static assets for the 3D Digital Twin tab.

Usage:
    python scripts/generate_twin_data.py

Outputs:
    dashboard/static/heightmap_guna.png  (2048x2048 16-bit DEM)
    dashboard/static/twin_config.json    (trees, boundaries, metadata)
"""

import json
import math
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

LULC_COLORS = {
    "tree":  np.array([26, 77, 30], dtype=np.uint8),
    "shrub": np.array([107, 123, 66], dtype=np.uint8),
    "grass": np.array([139, 157, 94], dtype=np.uint8),
    "crop":  np.array([196, 204, 106], dtype=np.uint8),
    "bare":  np.array([196, 169, 112], dtype=np.uint8),
    "built": np.array([139, 139, 139], dtype=np.uint8),
    "water": np.array([61, 107, 168], dtype=np.uint8),
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
    size: int = 2048,
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
        if pixel_size >= 0.01:
            raise ValueError(
                f"DEM appears to be in a projected CRS (pixel_size={pixel_size:.4f}). "
                "Expected a geographic CRS with degree units."
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
    img = img.resize((size, size), Image.Resampling.BILINEAR)

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

    Uses grid-accelerated rejection sampling for O(1) neighbor lookups
    instead of O(n) brute force. Handles 40K+ points efficiently.
    """
    from shapely.prepared import prep

    bounds = polygon.bounds
    prepared = prep(polygon)
    cell = min_dist / math.sqrt(2)
    bx0, by0 = bounds[0], bounds[1]

    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    points: list[tuple[float, float]] = []
    attempts = 0
    max_attempts = max_points * 40
    min_dist_sq = min_dist ** 2

    while len(points) < max_points and attempts < max_attempts:
        attempts += 1
        x = random.uniform(bounds[0], bounds[2])
        y = random.uniform(bounds[1], bounds[3])
        if not prepared.contains(Point(x, y)):
            continue

        gx = int((x - bx0) / cell)
        gy = int((y - by0) / cell)
        too_close = False
        for dx in range(-2, 3):
            if too_close:
                break
            for dy in range(-2, 3):
                for px, py in grid.get((gx + dx, gy + dy), ()):
                    if (x - px) ** 2 + (y - py) ** 2 < min_dist_sq:
                        too_close = True
                        break
                if too_close:
                    break

        if not too_close:
            points.append((x, y))
            grid.setdefault((gx, gy), []).append((x, y))

    return points


def generate_trees(
    geojson_path: str = "data/aoi/gunafinal.geojson",
    lulc_path: str = "data/aoi/compartment_lulc.json",
    terrain_path: str = "data/aoi/compartment_terrain.json",
    max_trees: int = 40000,
    min_dist_deg: float = 0.0002,
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
    for pos in range(len(gdf)):
        lulc = lulc_data.get(str(pos), {})
        tree_pcts.append(lulc.get("tree", 0))

    total_pct = sum(p for p in tree_pcts if p > 15)
    if total_pct == 0:
        return []

    all_trees: list[dict] = []
    for pos, (_df_idx, row) in enumerate(gdf.iterrows()):
        pct = tree_pcts[pos]
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

        terrain = terrain_data.get(str(pos), {})
        elev = terrain.get("elev", 450)
        lulc = lulc_data.get(str(pos), {})
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


def generate_shrubs(
    geojson_path: str = "data/aoi/gunafinal.geojson",
    lulc_path: str = "data/aoi/compartment_lulc.json",
    terrain_path: str = "data/aoi/compartment_terrain.json",
    max_shrubs: int = 15000,
    min_dist_deg: float = 0.0003,
) -> list[dict]:
    """Place shrub instances in compartments with significant shrub cover."""
    gdf = gpd.read_file(geojson_path)

    with open(lulc_path) as f:
        lulc_data = json.load(f)
    with open(terrain_path) as f:
        terrain_data = json.load(f)

    shrub_pcts: list[float] = []
    for pos in range(len(gdf)):
        lulc = lulc_data.get(str(pos), {})
        shrub_pcts.append(lulc.get("shrub", 0))

    total_pct = sum(p for p in shrub_pcts if p > 10)
    if total_pct == 0:
        return []

    all_shrubs: list[dict] = []
    for pos, (_df_idx, row) in enumerate(gdf.iterrows()):
        pct = shrub_pcts[pos]
        if pct <= 10:
            continue

        n_shrubs = max(1, int((pct / total_pct) * max_shrubs))
        if len(all_shrubs) + n_shrubs > max_shrubs:
            n_shrubs = max_shrubs - len(all_shrubs)
        if n_shrubs <= 0:
            break

        geom = row.geometry
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)

        points = _poisson_disk_sample(geom, min_dist_deg, n_shrubs)

        for lon, lat in points:
            all_shrubs.append(
                {
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                    "height": round(random.uniform(0.3, 0.8), 2),
                }
            )

    return all_shrubs[:max_shrubs]


# ===========================================================================
# Task 4: Boundary Simplification + Config Assembly
# ===========================================================================


def generate_boundaries(
    geojson_path: str = "data/aoi/gunafinal.geojson",
    lulc_path: str = "data/aoi/compartment_lulc.json",
    tolerance: float = 0.0005,
) -> list[dict]:
    """Simplify compartment polygons and attach LULC metadata.

    Returns a list of boundary dicts with beat/range names, simplified
    coordinate rings, and land-use fractions.
    """
    gdf = gpd.read_file(geojson_path)

    with open(lulc_path) as f:
        lulc_data = json.load(f)

    boundaries: list[dict] = []
    for pos, (_df_idx, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)

        simplified = geom.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty or simplified.geom_type != "Polygon":
            continue
        coords = [
            [round(c[0], 6), round(c[1], 6)] for c in simplified.exterior.coords
        ]

        lulc = lulc_data.get(str(pos), {})
        beat_name = row.get("BEAT", f"Compartment-{pos}")
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


def generate_lulc_texture(
    geojson_path: str = "data/aoi/gunafinal.geojson",
    lulc_path: str = "data/aoi/compartment_lulc.json",
    bounds_path: str = "data/aoi/overlay_bounds.json",
    output_path: str = "dashboard/static/lulc_classified.png",
    size: int = 2048,
) -> None:
    """Rasterize compartment LULC data into a classification color texture.

    Each pixel is colored by blending LULC class colors weighted by
    the compartment's land-use percentages. Adds per-pixel brightness
    noise (±12%) for natural variation.
    """
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds as transform_from_bounds

    gdf = gpd.read_file(geojson_path)

    with open(lulc_path) as f:
        lulc_data = json.load(f)
    with open(bounds_path) as f:
        raw = json.load(f)["lulc"]
    if "w" in raw and "west" not in raw:
        bounds = {"west": raw["w"], "south": raw["s"], "east": raw["e"], "north": raw["n"]}
    else:
        bounds = raw

    transform = transform_from_bounds(
        bounds["west"], bounds["south"], bounds["east"], bounds["north"],
        size, size,
    )

    # Rasterize compartment IDs (1-indexed, 0 = background)
    shapes = [
        (geom, idx + 1)
        for idx, geom in enumerate(gdf.geometry)
        if geom is not None and not geom.is_empty
    ]
    id_raster = rasterize(
        shapes, out_shape=(size, size), transform=transform, fill=0, dtype=np.int32,
    )

    # Build color lookup table from LULC percentages
    n = len(gdf)
    color_lut = np.zeros((n + 1, 3), dtype=np.float32)
    color_lut[0] = [30, 30, 30]  # background (outside all compartments)

    for pos in range(n):
        lulc = lulc_data.get(str(pos), {})
        blended = np.zeros(3, dtype=np.float32)
        total_w = 0.0
        for cls, base_color in LULC_COLORS.items():
            pct = lulc.get(cls, 0)
            if pct > 0:
                blended += base_color.astype(np.float32) * pct
                total_w += pct
        if total_w > 0:
            blended /= total_w
        else:
            blended[:] = LULC_COLORS["grass"].astype(np.float32)
        color_lut[pos + 1] = blended

    # Map IDs to colors
    rgb = np.zeros((size, size, 3), dtype=np.float32)
    for c in range(3):
        rgb[:, :, c] = color_lut[id_raster, c]

    # Add per-pixel brightness noise (±12%) for natural variation
    rng = np.random.default_rng(42)
    noise = rng.uniform(0.88, 1.12, (size, size, 1)).astype(np.float32)
    rgb = np.clip(rgb * noise, 0, 255).astype(np.uint8)

    img = Image.fromarray(rgb)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def generate_boundary_mask(
    geojson_path: str = "data/aoi/gunafinal.geojson",
    bounds_path: str = "data/aoi/overlay_bounds.json",
    output_path: str = "dashboard/static/mask_guna.png",
    size: int = 2048,
) -> None:
    """Rasterize GeoJSON boundary into a binary mask PNG.

    White (255) inside the division boundary, black (0) outside.
    Used by the terrain shader to discard fragments outside the AOI.
    """
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds as transform_from_bounds

    gdf = gpd.read_file(geojson_path)

    with open(bounds_path) as f:
        raw = json.load(f)["lulc"]
    if "w" in raw and "west" not in raw:
        bounds = {"west": raw["w"], "south": raw["s"], "east": raw["e"], "north": raw["n"]}
    else:
        bounds = raw

    transform = transform_from_bounds(
        bounds["west"], bounds["south"], bounds["east"], bounds["north"],
        size, size,
    )

    shapes = [(geom, 255) for geom in gdf.geometry if geom is not None]
    mask = rasterize(shapes, out_shape=(size, size), transform=transform, fill=0, dtype=np.uint8)

    img = Image.fromarray(mask, mode="L")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def generate_config(
    output_path: str = "dashboard/static/twin_config.json",
    heightmap_output_path: str = "dashboard/static/heightmap_guna.png",
    mask_output_path: str = "dashboard/static/mask_guna.png",
    lulc_output_path: str = "dashboard/static/lulc_classified.png",
    max_trees: int = 80000,
    max_shrubs: int = 15000,
) -> dict:
    """Orchestrate full twin-data generation: heightmap + LULC + mask + trees + shrubs + boundaries."""
    heightmap_meta = generate_heightmap(output_path=heightmap_output_path)
    generate_lulc_texture(output_path=lulc_output_path, size=heightmap_meta["size"])
    generate_boundary_mask(output_path=mask_output_path, size=heightmap_meta["size"])
    trees = generate_trees(max_trees=max_trees)
    shrubs = generate_shrubs(max_shrubs=max_shrubs)
    boundaries = generate_boundaries()

    config = {
        "terrain": {
            "heightmap": Path(heightmap_output_path).name,
            "lulc": Path(lulc_output_path).name,
            "mask": Path(mask_output_path).name,
            "bounds": heightmap_meta["bounds"],
            "elevation_range": [heightmap_meta["dem_min"], heightmap_meta["dem_max"]],
            "vertical_exaggeration": 2.5,
        },
        "trees": trees,
        "shrubs": shrubs,
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
    print(f"  LULC texture: dashboard/static/lulc_classified.png")
    print(f"  Mask: dashboard/static/mask_guna.png")
    print(f"  Config: dashboard/static/twin_config.json")
    print(f"  Trees: {len(config['trees'])}")
    print(f"  Shrubs: {len(config['shrubs'])}")
    print(f"  Boundaries: {len(config['boundaries'])}")
    print(f"  Elevation: {config['terrain']['elevation_range']}")
    print("Done.")
