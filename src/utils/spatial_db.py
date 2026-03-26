"""
DuckDB Spatial Analytics
========================
In-process analytical database for fast ad-hoc spatial queries over
Parquet/GeoParquet/CSV files in the data lake — no external server needed.

Advantages over pandas:
  - 10-100x faster for aggregation on large Parquet datasets
  - SQL interface for complex spatial joins and window functions
  - Reads Parquet files directly without loading into memory
  - Spatial extension supports ST_* functions (point-in-polygon, distance, etc.)

Usage::

    from src.utils.spatial_db import SpatialDB

    db = SpatialDB()

    # Query FIRMS parquet files directly
    df = db.query('''
        SELECT h3_res7, COUNT(*) as fire_count, AVG(frp) as mean_frp
        FROM read_parquet('data_lake/fire_detections/firms_viirs/2025/*/*/**.parquet')
        WHERE confidence IN ('nominal', 'high')
        GROUP BY h3_res7
        ORDER BY fire_count DESC
    ''')

    # Spatial join: fires within a boundary polygon
    gdf = db.spatial_query('''
        SELECT f.*, b.range_name
        FROM fires f, boundaries b
        WHERE ST_Within(ST_Point(f.longitude, f.latitude), b.geom)
    ''')
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

log = logging.getLogger(__name__)

DATA_LAKE = Path("E:/FIRE/data_lake")
DATA_DIR = Path("E:/FIRE/data")


class SpatialDB:
    """Lightweight DuckDB wrapper with spatial extension for fire analytics."""

    def __init__(self, db_path: str = ":memory:"):
        self.con = duckdb.connect(db_path)
        self._init_extensions()

    def _init_extensions(self) -> None:
        """Load spatial extension for ST_* functions."""
        try:
            self.con.install_extension("spatial")
            self.con.load_extension("spatial")
        except Exception:
            log.warning("DuckDB spatial extension not available — spatial queries disabled")

    def query(self, sql: str) -> pd.DataFrame:
        """Execute SQL and return a pandas DataFrame."""
        return self.con.sql(sql).df()

    def spatial_query(self, sql: str) -> "geopandas.GeoDataFrame":
        """Execute SQL with geometry columns and return a GeoDataFrame."""
        import geopandas as gpd
        from shapely import wkb

        df = self.con.sql(sql).df()
        # Convert WKB geometry columns to shapely
        for col in df.columns:
            if df[col].dtype == object and len(df) > 0:
                sample = df[col].iloc[0]
                if isinstance(sample, bytes) and len(sample) > 4:
                    try:
                        wkb.loads(sample)
                        df[col] = df[col].apply(lambda b: wkb.loads(b) if b else None)
                        return gpd.GeoDataFrame(df, geometry=col, crs="EPSG:4326")
                    except Exception:
                        pass
        return gpd.GeoDataFrame(df)

    def register_parquet(self, name: str, path: str) -> None:
        """Register a Parquet file/glob as a named table."""
        self.con.sql(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
        count = self.con.sql(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        log.info("Registered '%s' → %d rows", name, count)

    def register_geojson(self, name: str, path: str) -> None:
        """Register a GeoJSON file as a named table."""
        self.con.sql(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM ST_Read('{path}')")
        log.info("Registered GeoJSON '%s'", name)

    def firms_annual_stats(self, year: int) -> pd.DataFrame:
        """Quick annual FIRMS fire statistics by H3 hex."""
        glob = f"{DATA_LAKE}/fire_detections/firms_viirs/{year}/*/*/**.parquet"
        return self.query(f"""
            SELECT
                h3_res7,
                COUNT(*)           AS fire_count,
                AVG(frp)           AS mean_frp,
                MAX(frp)           AS max_frp,
                MIN(acq_date)      AS first_fire,
                MAX(acq_date)      AS last_fire,
                COUNT(DISTINCT acq_date) AS active_days
            FROM read_parquet('{glob}')
            GROUP BY h3_res7
            ORDER BY fire_count DESC
        """)

    def weather_fire_correlation(self, weather_parquet: Optional[str] = None) -> pd.DataFrame:
        """Join FIRMS detections with NASA POWER weather data."""
        wp = weather_parquet or f"{DATA_LAKE}/fire_weather/nasa_power_2013_2026.parquet"
        return self.query(f"""
            WITH fires AS (
                SELECT acq_date, COUNT(*) as n_fires, AVG(frp) as mean_frp
                FROM read_parquet('{DATA_LAKE}/fire_detections/firms_viirs/*/*/*/*.parquet')
                GROUP BY acq_date
            )
            SELECT w.*, f.n_fires, f.mean_frp
            FROM read_parquet('{wp}') w
            LEFT JOIN fires f ON CAST(w.date AS DATE) = CAST(f.acq_date AS DATE)
            ORDER BY w.date
        """)

    def close(self) -> None:
        """Close the DuckDB connection."""
        self.con.close()

    def __enter__(self) -> "SpatialDB":
        return self

    def __exit__(self, *args) -> None:
        self.close()
