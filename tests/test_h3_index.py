"""Tests for src/utils/h3_index.py — H3 hexagonal spatial indexing."""

import numpy as np
import pytest
import geopandas as gpd
from shapely.geometry import Point

from src.utils.h3_index import (
    add_h3_index,
    aggregate_to_h3,
    h3_block_groups,
    RES_RANGE,
    RES_BEAT,
)


@pytest.fixture
def sample_gdf():
    """5 FIRMS-like detections across Guna Division."""
    data = {
        "latitude": [24.15, 24.20, 24.85, 24.90, 24.50],
        "longitude": [77.26, 77.30, 77.10, 77.15, 76.80],
        "frp": [9.2, 25.0, 55.0, 120.0, 5.0],
    }
    return gpd.GeoDataFrame(
        data,
        geometry=[Point(lon, lat) for lon, lat in zip(data["longitude"], data["latitude"])],
        crs="EPSG:4326",
    )


@pytest.fixture
def empty_gdf():
    return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


class TestAddH3Index:
    def test_adds_default_columns(self, sample_gdf):
        result = add_h3_index(sample_gdf)
        assert f"h3_res{RES_RANGE}" in result.columns
        assert f"h3_res{RES_BEAT}" in result.columns

    def test_custom_resolutions(self, sample_gdf):
        result = add_h3_index(sample_gdf, resolutions=[5, 10])
        assert "h3_res5" in result.columns
        assert "h3_res10" in result.columns
        assert f"h3_res{RES_RANGE}" not in result.columns

    def test_h3_values_are_strings(self, sample_gdf):
        result = add_h3_index(sample_gdf, resolutions=[7])
        assert result["h3_res7"].dtype == object
        assert all(isinstance(v, str) for v in result["h3_res7"])

    def test_unique_hexes_per_resolution(self, sample_gdf):
        result = add_h3_index(sample_gdf, resolutions=[7, 9])
        # Higher resolution = more unique hexes (or equal)
        assert result["h3_res9"].nunique() >= result["h3_res7"].nunique()

    def test_does_not_mutate_input(self, sample_gdf):
        original_cols = list(sample_gdf.columns)
        add_h3_index(sample_gdf)
        assert list(sample_gdf.columns) == original_cols

    def test_empty_gdf(self, empty_gdf):
        result = add_h3_index(empty_gdf)
        assert f"h3_res{RES_RANGE}" in result.columns
        assert len(result) == 0


class TestAggregateToH3:
    def test_count_aggregation(self, sample_gdf):
        result = aggregate_to_h3(sample_gdf, resolution=7)
        assert "value" in result.columns
        assert "geometry" in result.columns
        assert result["value"].sum() == len(sample_gdf)

    def test_mean_aggregation(self, sample_gdf):
        result = aggregate_to_h3(sample_gdf, resolution=7, agg_col="frp", agg_func="mean")
        assert "value" in result.columns
        # Each point in its own hex, so mean = original value
        assert len(result) == 5

    def test_returns_geodataframe(self, sample_gdf):
        result = aggregate_to_h3(sample_gdf, resolution=7)
        assert isinstance(result, gpd.GeoDataFrame)
        assert result.crs is not None

    def test_hex_polygons_valid(self, sample_gdf):
        result = aggregate_to_h3(sample_gdf, resolution=7)
        for geom in result.geometry:
            assert geom.is_valid
            assert geom.geom_type == "Polygon"


class TestH3BlockGroups:
    def test_returns_array(self, sample_gdf):
        groups = h3_block_groups(sample_gdf, resolution=6)
        assert isinstance(groups, np.ndarray)
        assert len(groups) == len(sample_gdf)

    def test_groups_are_integers(self, sample_gdf):
        groups = h3_block_groups(sample_gdf, resolution=6)
        assert groups.dtype in (np.int64, np.int32, int)

    def test_nearby_points_same_group(self):
        """Two points very close together should share the same H3 hex."""
        data = {
            "latitude": [24.150, 24.151],
            "longitude": [77.260, 77.261],
        }
        gdf = gpd.GeoDataFrame(
            data,
            geometry=[Point(77.260, 24.150), Point(77.261, 24.151)],
            crs="EPSG:4326",
        )
        groups = h3_block_groups(gdf, resolution=6)
        assert groups[0] == groups[1]

    def test_distant_points_different_groups(self, sample_gdf):
        groups = h3_block_groups(sample_gdf, resolution=9)
        # Points are spread across Guna Division — should have multiple groups
        assert len(set(groups)) > 1
