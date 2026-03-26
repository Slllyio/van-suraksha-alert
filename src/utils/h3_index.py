"""
H3 Hexagonal Spatial Indexing
=============================
Adds Uber H3 hex indices to GeoDataFrames for fast spatial aggregation,
join operations, and cross-validation blocking.

Resolution guide (Guna Division context):
  - res 5  (~253 km²) : division-level aggregation
  - res 7  (~5.16 km²) : range-level (~matches forest range boundaries)
  - res 9  (~0.105 km²) : beat-level (~matches forest beat boundaries)
  - res 10 (~0.015 km²) : FIRMS pixel-level grouping

Usage::

    from src.utils.h3_index import add_h3_index, aggregate_to_h3

    # Add H3 columns to a FIRMS GeoDataFrame
    gdf = add_h3_index(firms_gdf, resolutions=[7, 9])

    # Aggregate fire counts per hex
    hex_gdf = aggregate_to_h3(firms_gdf, resolution=7, agg_col="frp", agg_func="mean")
"""

from __future__ import annotations

import logging
from typing import Sequence

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

log = logging.getLogger(__name__)

# Default resolutions matching Guna Division admin hierarchy
RES_RANGE = 7   # ~5.16 km² — forest range level
RES_BEAT = 9    # ~0.105 km² — forest beat level


def add_h3_index(
    gdf: gpd.GeoDataFrame,
    resolutions: Sequence[int] = (RES_RANGE, RES_BEAT),
) -> gpd.GeoDataFrame:
    """
    Add H3 hex index columns to a GeoDataFrame with point geometries.

    Parameters
    ----------
    gdf : GeoDataFrame with point geometry in EPSG:4326.
    resolutions : H3 resolutions to compute (default: 7 and 9).

    Returns
    -------
    New GeoDataFrame with ``h3_res{N}`` columns added.
    """
    if gdf.empty:
        for res in resolutions:
            gdf[f"h3_res{res}"] = pd.Series(dtype="str")
        return gdf

    # Ensure WGS-84
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    result = gdf.copy()

    lats = result.geometry.y.values
    lons = result.geometry.x.values

    for res in resolutions:
        col = f"h3_res{res}"
        result[col] = [
            h3.latlng_to_cell(lat, lng, res)
            for lat, lng in zip(lats, lons)
        ]
        log.debug("Added %s — %d unique hexes", col, result[col].nunique())

    return result


def aggregate_to_h3(
    gdf: gpd.GeoDataFrame,
    resolution: int = RES_RANGE,
    agg_col: str | None = None,
    agg_func: str = "count",
) -> gpd.GeoDataFrame:
    """
    Aggregate point data into H3 hexagons with geometry for mapping.

    Parameters
    ----------
    gdf : GeoDataFrame with point geometry in EPSG:4326.
    resolution : H3 resolution for aggregation.
    agg_col : Column to aggregate. If None, counts points per hex.
    agg_func : Aggregation function ("count", "sum", "mean", "max").

    Returns
    -------
    GeoDataFrame with hex polygons and aggregated values.
    """
    h3_col = f"h3_res{resolution}"

    if h3_col not in gdf.columns:
        gdf = add_h3_index(gdf, resolutions=[resolution])

    if agg_col and agg_func != "count":
        agg_df = gdf.groupby(h3_col)[agg_col].agg(agg_func).reset_index()
        agg_df.columns = [h3_col, "value"]
    else:
        agg_df = gdf.groupby(h3_col).size().reset_index(name="value")

    # Convert H3 cells to polygon geometries
    agg_df["geometry"] = agg_df[h3_col].apply(_h3_to_polygon)

    return gpd.GeoDataFrame(agg_df, geometry="geometry", crs="EPSG:4326")


def h3_block_groups(
    gdf: gpd.GeoDataFrame,
    resolution: int = 6,
) -> np.ndarray:
    """
    Generate spatial block group labels for cross-validation.

    Assigns each row an H3 hex ID at the given resolution, suitable for
    use with sklearn's GroupKFold to prevent spatial leakage.

    Parameters
    ----------
    gdf : GeoDataFrame with point geometry.
    resolution : H3 resolution for blocking. Lower = larger blocks = more
                 separation. Recommended: 5-6 for Guna Division.

    Returns
    -------
    Array of integer group labels (one per row).
    """
    col = f"h3_res{resolution}"
    indexed = add_h3_index(gdf, resolutions=[resolution])
    # Map hex strings to integer group IDs
    unique_hexes = indexed[col].unique()
    hex_to_int = {h: i for i, h in enumerate(unique_hexes)}
    return indexed[col].map(hex_to_int).values


def _h3_to_polygon(h3_cell: str) -> Polygon:
    """Convert an H3 cell ID to a Shapely polygon."""
    boundary = h3.cell_to_boundary(h3_cell)
    # h3 returns (lat, lng) tuples; Shapely needs (lng, lat)
    coords = [(lng, lat) for lat, lng in boundary]
    coords.append(coords[0])  # close ring
    return Polygon(coords)
