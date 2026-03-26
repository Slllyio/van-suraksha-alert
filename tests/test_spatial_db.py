"""Tests for src/utils/spatial_db.py — DuckDB spatial analytics."""

import pytest
import pandas as pd

from src.utils.spatial_db import SpatialDB


@pytest.fixture
def db():
    sdb = SpatialDB()
    yield sdb
    sdb.close()


class TestSpatialDB:
    def test_basic_query(self, db):
        df = db.query("SELECT 1 + 1 AS result")
        assert df["result"].iloc[0] == 2

    def test_spatial_point_in_polygon(self, db):
        df = db.query("""
            SELECT ST_Contains(
                ST_GeomFromText('POLYGON((76 23, 78 23, 78 25, 76 25, 76 23))'),
                ST_Point(77.26, 24.15)
            ) AS inside
        """)
        assert bool(df["inside"].iloc[0]) is True

    def test_spatial_point_outside_polygon(self, db):
        df = db.query("""
            SELECT ST_Contains(
                ST_GeomFromText('POLYGON((76 23, 78 23, 78 25, 76 25, 76 23))'),
                ST_Point(80.0, 28.0)
            ) AS inside
        """)
        assert bool(df["inside"].iloc[0]) is False

    def test_register_parquet(self, db, tmp_path):
        # Create a temp parquet
        df = pd.DataFrame({"lat": [24.15], "lon": [77.26], "frp": [9.2]})
        pq_path = tmp_path / "test.parquet"
        df.to_parquet(pq_path)

        db.register_parquet("test_fires", str(pq_path))
        result = db.query("SELECT COUNT(*) AS n FROM test_fires")
        assert result["n"].iloc[0] == 1

    def test_context_manager(self):
        with SpatialDB() as db:
            df = db.query("SELECT 42 AS answer")
            assert df["answer"].iloc[0] == 42

    def test_distance_calculation(self, db):
        df = db.query("""
            SELECT ST_Distance(
                ST_Point(77.26, 24.15),
                ST_Point(77.30, 24.20)
            ) AS dist
        """)
        assert df["dist"].iloc[0] > 0

    def test_geojson_register(self, db, tmp_path):
        # Create minimal GeoJSON
        import json
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [77.26, 24.15]},
                "properties": {"name": "test"}
            }]
        }
        gj_path = tmp_path / "test.geojson"
        gj_path.write_text(json.dumps(geojson))

        db.register_geojson("test_points", str(gj_path))
        result = db.query("SELECT COUNT(*) AS n FROM test_points")
        assert result["n"].iloc[0] == 1
