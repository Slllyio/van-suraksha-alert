"""Tests for src/viz/lonboard_layers.py — Lonboard high-performance map layers."""

import numpy as np
import pytest
import geopandas as gpd
from shapely.geometry import Point, Polygon

from src.viz.lonboard_layers import (
    firms_scatter_layer,
    h3_heatmap_layer,
    boundary_layer,
    render_map,
)


@pytest.fixture
def firms_gdf():
    data = {
        "frp": [9.2, 25.0, 55.0, 120.0, 250.0],
    }
    return gpd.GeoDataFrame(
        data,
        geometry=[
            Point(77.26, 24.15), Point(77.30, 24.20),
            Point(77.10, 24.85), Point(77.15, 24.90),
            Point(76.80, 24.50),
        ],
        crs="EPSG:4326",
    )


@pytest.fixture
def h3_agg_gdf():
    """Pre-aggregated H3 hex data."""
    from src.utils.h3_index import aggregate_to_h3
    data = {"frp": [10.0, 50.0, 100.0]}
    gdf = gpd.GeoDataFrame(
        data,
        geometry=[Point(77.26, 24.15), Point(77.10, 24.85), Point(76.80, 24.50)],
        crs="EPSG:4326",
    )
    return aggregate_to_h3(gdf, resolution=7, agg_col="frp", agg_func="mean")


@pytest.fixture
def boundary_gdf():
    poly = Polygon([(76.45, 23.80), (77.85, 23.80), (77.85, 24.95), (76.45, 24.95)])
    return gpd.GeoDataFrame({"name": ["Guna"]}, geometry=[poly], crs="EPSG:4326")


class TestFirmsScatterLayer:
    def test_creates_layer(self, firms_gdf):
        layer = firms_scatter_layer(firms_gdf)
        assert layer.table.num_rows == 5

    def test_empty_gdf(self):
        empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        layer = firms_scatter_layer(empty)
        assert layer is None


class TestH3HeatmapLayer:
    def test_creates_layer(self, h3_agg_gdf):
        layer = h3_heatmap_layer(h3_agg_gdf)
        assert layer.table.num_rows == len(h3_agg_gdf)


class TestBoundaryLayer:
    def test_creates_layer(self, boundary_gdf):
        layer = boundary_layer(boundary_gdf)
        assert layer.table.num_rows == 1


class TestRenderMap:
    def test_creates_map(self, firms_gdf):
        layer = firms_scatter_layer(firms_gdf)
        m = render_map([layer])
        assert len(m.layers) == 1

    def test_multiple_layers(self, firms_gdf, h3_agg_gdf):
        l1 = firms_scatter_layer(firms_gdf)
        l2 = h3_heatmap_layer(h3_agg_gdf)
        m = render_map([l1, l2], center=(24.4, 77.15), zoom=10.0)
        assert len(m.layers) == 2
