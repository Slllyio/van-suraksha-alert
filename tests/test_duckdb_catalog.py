"""Smoke tests for src/utils/duckdb_catalog.py.

Verifies that:
  1. Module imports
  2. Catalog is non-empty + has the expected core views
  3. connect() registers at least one view
  4. Each registered view is queryable (SELECT 1 + COUNT(*) succeed)
  5. Cross-table JOIN works for the most-common case
  6. CSV-export path doesn't crash
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow `import src.utils.duckdb_catalog` when pytest is run from project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.duckdb_catalog import CATALOG, TableSpec, connect, describe, list_tables  # noqa: E402


# ----- Catalog structure -----

def test_catalog_is_non_empty():
    assert len(CATALOG) >= 10, "expected at least 10 cataloged tables"


def test_catalog_entries_are_table_specs():
    for spec in CATALOG:
        assert isinstance(spec, TableSpec)
        assert spec.format in {"parquet", "csv"}, f"unsupported format {spec.format!r} for {spec.name}"
        assert spec.name.replace("_", "").isalnum(), f"non-SQL-safe name: {spec.name}"
        assert spec.path.startswith(("data_lake/", "outputs/", "data/")), \
            f"unexpected path root for {spec.name}: {spec.path}"


def test_core_views_are_present():
    """Locks the API: dropping any of these breaks documented queries."""
    must_have = {
        "firms_consolidated", "firms_nrt",
        "fwi_daily", "beat_climatology",
        "val_per_division_day", "val_per_beat_day",
    }
    have = {s.name for s in CATALOG}
    missing = must_have - have
    assert not missing, f"core views missing from CATALOG: {missing}"


# ----- connect() runtime -----

@pytest.fixture(scope="module")
def con():
    c = connect()
    yield c
    c.close()


def test_connect_registers_at_least_one_view(con):
    n_ok, n_skip = con.execute(
        "SELECT n_registered, n_skipped FROM _catalog_meta"
    ).fetchone()
    assert n_ok >= 1, "no views registered (no backing files exist?)"


def test_every_existing_view_is_queryable(con):
    """For every view whose backing file exists, SELECT COUNT(*) must succeed."""
    failures = []
    for spec in list_tables():
        try:
            n = con.sql(f"SELECT COUNT(*) FROM {spec.name}").fetchone()[0]
            assert n >= 0
        except Exception as exc:
            failures.append((spec.name, type(exc).__name__, str(exc)[:120]))
    assert not failures, f"un-queryable views: {failures}"


def test_describe_returns_columns(con):
    """DESCRIBE on a known view returns at least one column row."""
    if not any(s.name == "val_per_division_day" for s in list_tables()):
        pytest.skip("val_per_division_day not present")
    rows = describe(con, "val_per_division_day")
    assert len(rows) >= 5, f"expected ≥5 columns, got {len(rows)}"
    col_names = [r[0] for r in rows]
    assert "date" in col_names
    assert "division" in col_names


# ----- Cross-table JOIN -----

def test_cross_table_join_runs(con):
    """JOIN val_per_division_day ↔ fwi_daily — the headline DuckDB use-case."""
    needed = {"val_per_division_day", "fwi_daily"}
    have = {s.name for s in list_tables()}
    if not needed.issubset(have):
        pytest.skip(f"missing one of {needed}")
    df = con.sql("""
        SELECT vdpd.date, vdpd.division, vdpd.n_fires_observed AS fires, fwi.ffmc
        FROM val_per_division_day vdpd
        LEFT JOIN fwi_daily fwi ON vdpd.date = fwi.date
        LIMIT 10
    """).df()
    assert len(df) > 0
    assert {"date", "division", "fires", "ffmc"}.issubset(df.columns)


# ----- CSV export -----

def test_csv_export_writes_file(con, tmp_path):
    out = tmp_path / "test_export.csv"
    con.execute(
        f"COPY (SELECT 1 AS a, 'x' AS b UNION ALL SELECT 2, 'y') "
        f"TO '{out.as_posix()}' (HEADER, DELIMITER ',')"
    )
    assert out.exists()
    text = out.read_text().strip().splitlines()
    assert text[0] == "a,b"
    assert len(text) == 3  # header + 2 data rows
