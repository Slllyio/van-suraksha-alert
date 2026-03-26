"""Tests for scripts/generate_twin_data.py — 3D Digital Twin data pipeline."""

import json
import math
from pathlib import Path

import numpy as np
import pytest


# ===================================================================
# Task 2: DEM Heightmap tests
# ===================================================================


def test_heightmap_handles_nodata():
    """Nodata value -32768 must not corrupt normalization."""
    from scripts.generate_twin_data import _normalize_dem

    dem = np.array([[400, 500], [-32768, 450]], dtype=np.float32)
    result, dem_min, dem_max = _normalize_dem(dem, nodata=-32768)

    assert dem_min == 400.0
    assert dem_max == 500.0
    assert result[0, 0] == 0  # min maps to 0
    assert result[0, 1] == 65535  # max maps to 65535
    assert result[1, 0] == 0  # nodata fills to dem_min -> 0


def test_normalize_dem_flat():
    """Flat DEM (all same value) returns zeros without division error."""
    from scripts.generate_twin_data import _normalize_dem

    dem = np.full((4, 4), 450.0, dtype=np.float32)
    result, dem_min, dem_max = _normalize_dem(dem, nodata=-32768)

    assert dem_min == 450.0
    assert dem_max == 450.0
    assert np.all(result == 0)


def test_normalize_dem_all_nodata():
    """All-nodata DEM returns zeros with min=max=0 (edge case)."""
    from scripts.generate_twin_data import _normalize_dem

    dem = np.full((3, 3), -32768.0, dtype=np.float32)
    result, dem_min, dem_max = _normalize_dem(dem, nodata=-32768)

    assert result.dtype == np.uint16
    assert np.all(result == 0)
    assert dem_min == 0.0
    assert dem_max == 0.0


def test_generate_heightmap_creates_valid_png(tmp_path):
    """Heightmap should be a valid 16-bit grayscale PNG at requested size."""
    from scripts.generate_twin_data import generate_heightmap
    from PIL import Image

    out = tmp_path / "heightmap.png"
    meta = generate_heightmap(
        dem_path="data/rasters/dem_30m.tif",
        bounds_path="data/aoi/overlay_bounds.json",
        output_path=str(out),
        size=64,  # small for testing
    )

    assert out.exists()
    with Image.open(out) as img:
        assert img.size == (64, 64)
        assert img.mode == "I;16"
    assert "dem_min" in meta
    assert "dem_max" in meta
    assert meta["dem_min"] > 0  # no nodata leaked
    assert meta["dem_max"] < 1000  # sanity for Guna (340-579m)


# ===================================================================
# Task 3: Tree placement tests
# ===================================================================


def test_elevation_band_classification():
    """Elevation bands match Guna ecology: low < 400, mid 400-500, high > 500."""
    from scripts.generate_twin_data import _elevation_band

    assert _elevation_band(350) == "low"
    assert _elevation_band(399) == "low"
    assert _elevation_band(400) == "mid"
    assert _elevation_band(499) == "mid"
    assert _elevation_band(500) == "high"
    assert _elevation_band(600) == "high"


def test_pick_species_returns_valid():
    """All returned species are in the known set."""
    from scripts.generate_twin_data import _pick_species

    valid = {"teak", "tendu", "mahua", "bamboo", "shrub"}
    for _ in range(200):
        s = _pick_species(450, has_shrub=True)
        assert s in valid


def test_generate_trees_produces_valid_entries():
    """Tree list has correct structure and geographic bounds."""
    from scripts.generate_twin_data import generate_trees

    trees = generate_trees(max_trees=100)
    assert len(trees) > 0
    assert len(trees) <= 100
    for t in trees:
        assert "lon" in t and "lat" in t
        assert t["species"] in ("teak", "tendu", "mahua", "bamboo", "shrub")
        assert 0.3 < t["height"] < 2.0
        assert 76.5 < t["lon"] < 78.0
        assert 23.5 < t["lat"] < 25.5


def test_poisson_disk_minimum_distance():
    """Trees from nearby compartments should not be unreasonably close."""
    from scripts.generate_twin_data import generate_trees

    trees = generate_trees(max_trees=200)
    min_dist_deg = 0.0004
    for i, a in enumerate(trees):
        for b in trees[i + 1 : i + 10]:
            dist = math.sqrt(
                (a["lon"] - b["lon"]) ** 2 + (a["lat"] - b["lat"]) ** 2
            )
            if dist < min_dist_deg * 0.5:
                pytest.fail(f"Trees too close: {dist:.6f} deg")


# ===================================================================
# Task 4: Boundary simplification + config assembly tests
# ===================================================================


def test_generate_boundaries_simplifies_coords():
    """Boundaries should have valid beat/range/coords/lulc structure."""
    from scripts.generate_twin_data import generate_boundaries

    boundaries = generate_boundaries(tolerance=0.002)
    assert len(boundaries) > 0
    for b in boundaries:
        assert "beat" in b
        assert "range" in b
        assert "coords" in b
        assert len(b["coords"]) >= 3
        assert "lulc" in b
        for coord in b["coords"]:
            assert len(coord) == 2


def test_boundaries_have_reasonable_vertex_count():
    """Simplified boundaries should have fewer vertices than raw."""
    from scripts.generate_twin_data import generate_boundaries

    boundaries = generate_boundaries(tolerance=0.002)
    total_verts = sum(len(b["coords"]) for b in boundaries)
    # 747 compartments * ~average 20 verts each = ~15000 total
    # Raw would be much more; simplified should be under 50k
    assert total_verts < 50000, f"Too many vertices after simplification: {total_verts}"


def test_full_config_assembly(tmp_path):
    """End-to-end: generate_config produces valid JSON with all sections."""
    from scripts.generate_twin_data import generate_config

    out = tmp_path / "config.json"
    hm_out = tmp_path / "heightmap.png"
    config = generate_config(
        output_path=str(out),
        heightmap_output_path=str(hm_out),
        max_trees=50,
    )

    assert hm_out.exists()
    with open(out) as f:
        loaded = json.load(f)

    assert "terrain" in loaded
    assert "trees" in loaded
    assert "boundaries" in loaded
    assert loaded["terrain"]["bounds"]["west"] < loaded["terrain"]["bounds"]["east"]
    assert (
        loaded["terrain"]["elevation_range"][0]
        < loaded["terrain"]["elevation_range"][1]
    )
    assert len(loaded["trees"]) <= 50
    assert len(loaded["boundaries"]) > 0
