"""
Lonboard High-Performance Map Layers
=====================================
30-40x faster than PyDeck for large GeoDataFrames.
Uses GeoArrow binary pipeline — no JSON serialization overhead.

For Streamlit integration, Lonboard renders via ipywidgets.
For standalone use, renders in Jupyter or exports to HTML.

Usage::

    from src.viz.lonboard_layers import (
        firms_scatter_layer,
        h3_heatmap_layer,
        boundary_layer,
        render_map,
    )

    # FIRMS detections as color-coded scatter
    layer = firms_scatter_layer(firms_gdf)

    # H3 fire risk heatmap
    h3_layer = h3_heatmap_layer(h3_agg_gdf, value_col="fire_count")

    # Render all layers
    m = render_map([layer, h3_layer], center=(24.4, 77.1))
"""

from __future__ import annotations

import logging
from typing import Sequence

import geopandas as gpd
import numpy as np

log = logging.getLogger(__name__)


def firms_scatter_layer(
    gdf: gpd.GeoDataFrame,
    radius_col: str = "frp",
    radius_scale: float = 50.0,
    min_radius: float = 3.0,
    max_radius: float = 30.0,
) -> "lonboard.ScatterplotLayer":
    """
    Create a scatterplot layer for FIRMS fire detections.

    Colors by FRP intensity: low=yellow, moderate=orange, high=red, extreme=darkred.
    Radius scales with FRP.
    """
    from lonboard import ScatterplotLayer

    if gdf.empty:
        return ScatterplotLayer.from_geopandas(gdf)

    # Color by FRP category
    colors = _frp_to_rgba(gdf.get(radius_col, gdf.get("frp")))

    # Radius from FRP
    if radius_col in gdf.columns:
        radii = np.clip(gdf[radius_col].fillna(1).values * (radius_scale / 50.0), min_radius, max_radius)
    else:
        radii = np.full(len(gdf), 5.0)

    return ScatterplotLayer.from_geopandas(
        gdf,
        get_fill_color=colors,
        get_radius=radii,
        radius_min_pixels=2,
        opacity=0.8,
    )


def h3_heatmap_layer(
    gdf: gpd.GeoDataFrame,
    value_col: str = "value",
    colormap: str = "YlOrRd",
) -> "lonboard.SolidPolygonLayer":
    """
    Create a filled polygon layer for H3 hexagons with value-based coloring.

    Best used with output from `aggregate_to_h3()`.
    """
    from lonboard import SolidPolygonLayer

    if gdf.empty:
        return SolidPolygonLayer.from_geopandas(gdf)

    colors = _value_to_rgba(gdf[value_col].values, colormap)

    return SolidPolygonLayer.from_geopandas(
        gdf,
        get_fill_color=colors,
        opacity=0.6,
        extruded=False,
    )


def boundary_layer(
    gdf: gpd.GeoDataFrame,
    color: tuple[int, int, int, int] = (50, 130, 200, 180),
    line_width: float = 2.0,
) -> "lonboard.PathLayer":
    """Create an outline layer for forest range/beat boundaries."""
    from lonboard import PathLayer

    return PathLayer.from_geopandas(
        gdf,
        get_color=color,
        width_min_pixels=line_width,
    )


def render_map(
    layers: Sequence,
    center: tuple[float, float] = (24.4, 77.15),
    zoom: float = 9.0,
) -> "lonboard.Map":
    """
    Render a Lonboard map with the given layers.

    Returns a Lonboard Map widget (displays in Jupyter, can export to HTML).
    """
    from lonboard import Map

    m = Map(layers=list(layers))
    m.set_view_state(
        latitude=center[0],
        longitude=center[1],
        zoom=zoom,
    )
    return m


# ── Color helpers ──────────────────────────────────────────────────────────


def _frp_to_rgba(frp_series) -> np.ndarray:
    """Map FRP values to RGBA colors (yellow → red → darkred)."""
    if frp_series is None:
        return np.array([[255, 200, 0, 200]])

    frp = np.array(frp_series, dtype=float)
    frp = np.nan_to_num(frp, nan=1.0)

    colors = np.zeros((len(frp), 4), dtype=np.uint8)
    colors[:, 3] = 200  # alpha

    # low: yellow
    mask = frp < 10
    colors[mask] = [255, 235, 59, 200]

    # moderate: orange
    mask = (frp >= 10) & (frp < 50)
    colors[mask] = [255, 152, 0, 220]

    # high: red
    mask = (frp >= 50) & (frp < 200)
    colors[mask] = [244, 67, 54, 240]

    # extreme: dark red
    mask = frp >= 200
    colors[mask] = [183, 28, 28, 255]

    return colors


def _value_to_rgba(values: np.ndarray, colormap: str = "YlOrRd") -> np.ndarray:
    """Map numeric values to RGBA using matplotlib colormap."""
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap(colormap)
    vmin, vmax = np.nanmin(values), np.nanmax(values)

    if vmax == vmin:
        norm = np.full_like(values, 0.5)
    else:
        norm = (values - vmin) / (vmax - vmin)

    rgba = (cmap(norm) * 255).astype(np.uint8)
    rgba[:, 3] = 180  # semi-transparent
    return rgba
