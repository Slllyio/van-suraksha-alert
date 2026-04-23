"""DuckDB analytical catalog for the JwalaNetra FIRE project.

DuckDB is the right tool for ad-hoc analytical queries across our parquet
+ CSV outputs because:
  - Reads parquet/CSV directly (no ETL into a database)
  - Vectorised execution beats pandas on group-bys + joins on big files
  - Same SQL works in DBeaver, Excel-via-DBI, Jupyter, CLI
  - Single-file engine, no server to run

This module registers every long-lived parquet / CSV in the project as a
named DuckDB VIEW, so a SQL query can JOIN across them without users
having to remember filesystem paths.

Usage
-----

    from src.utils.duckdb_catalog import connect

    con = connect()                          # all views registered
    df = con.sql("SELECT * FROM val_per_division ORDER BY recall LIMIT 5").df()

    # JOIN across files:
    con.sql('''
      SELECT vdpd.date, vdpd.division, vdpd.n_fires_observed,
             fwi.ffmc, fwi.danger_class
      FROM val_per_division_day vdpd
      LEFT JOIN fwi_daily fwi ON vdpd.date = fwi.date
      WHERE vdpd.n_fires_observed > 50
      ORDER BY vdpd.date, vdpd.division
    ''').show()

Safety
------
* Views are READ-ONLY against the underlying files (DuckDB cannot write
  through a view).
* The only way to mutate disk state is `COPY (...) TO 'path'` or a
  `CREATE TABLE ... AS` followed by export. Don't write SQL that does
  that against project paths unless you know what you're doing.
* The connection is `:memory:` — no persistent state. Re-open to refresh
  views against newly-written files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TableSpec:
    """One registered DuckDB view backed by a file on disk."""
    name: str
    path: str       # relative to ROOT
    format: str     # 'parquet' | 'csv'
    description: str


# Order matters only for `--list` output.
CATALOG: tuple[TableSpec, ...] = (
    # ---------- FIRMS fire detections ----------
    TableSpec("firms_consolidated",
              "data_lake/fire_detections/firms_mp_viirs/firms_mp_consolidated.parquet",
              "parquet",
              "VIIRS+MODIS detections 2014-present, MP statewide (1.35 M rows)"),
    TableSpec("firms_nrt",
              "data_lake/fire_detections/firms_mp_viirs/nrt_7d.parquet",
              "parquet",
              "NASA FIRMS NRT last ~10 days (auto-refreshed every 6 h by portal)"),
    TableSpec("firms_dbscan_ignition",
              "data_lake/fire_detections/firms_dbscan_ignition.parquet",
              "parquet",
              "DBSCAN-clustered ignition events (used in v17 training)"),
    TableSpec("ba_clusters_mp",
              "data_lake/fire_detections/ba_clusters_mp.parquet",
              "parquet",
              "Andela 2019 burnt-area flood-fill clusters (MCD64 + FireCCI51)"),

    # ---------- Weather + climatology ----------
    TableSpec("fwi_daily",
              "data_lake/fire_weather/fwi_daily.parquet",
              "parquet",
              "Canadian Fire Weather Index daily, MP statewide aggregate"),
    TableSpec("beat_climatology",
              "data_lake/fire_weather/beat_fire_climatology.parquet",
              "parquet",
              "Per-beat × per-week 5-year fire history; drives climatology floor"),
    TableSpec("soil_daily",
              "data_lake/fire_weather/soil_daily.parquet",
              "parquet",
              "Soil temperature + moisture daily (Open-Meteo Archive)"),

    # ---------- Operational alert logs ----------
    TableSpec("v17_validation_rolling",
              "data_lake/alerts/v17_validation_rolling.parquet",
              "parquet",
              "Rolling daily validation: recall@5%, precision, lead-time"),
    TableSpec("v17_drift_log",
              "data_lake/alerts/v17_drift_log.parquet",
              "parquet",
              "Cell-level prediction-drift log (rank stability)"),
    TableSpec("v17_feature_drift",
              "data_lake/alerts/v17_feature_drift_log.parquet",
              "parquet",
              "Feature-distribution drift vs training set"),
    TableSpec("field_responses",
              "data_lake/alerts/field_responses.parquet",
              "parquet",
              "Forest-officer feedback per alert: TRUE / FALSE / UNVERIFIED"),

    # ---------- 2026 season validation outputs ----------
    TableSpec("val_per_day",
              "outputs/validation_reports/2026_per_day.csv",
              "csv",
              "2026 season day-summary (28 rows)"),
    TableSpec("val_per_division",
              "outputs/validation_reports/2026_per_division.csv",
              "csv",
              "2026 season per-division summary (87 rows)"),
    TableSpec("val_per_division_day",
              "outputs/validation_reports/2026_per_division_per_day.csv",
              "csv",
              "2026 (date × division) grid (5,742 rows) — most useful for daily ops review"),
    TableSpec("val_per_beat_day",
              "outputs/validation_reports/2026_per_beat_per_day.csv",
              "csv",
              "2026 (date × division × beat) granular matrix (104,391 rows)"),
    TableSpec("val_per_fire",
              "outputs/validation_reports/2026_per_fire.csv",
              "csv",
              "2026 per-FIRMS-event records (4,715 rows): caught/missed + offsets"),
    TableSpec("val_per_trust_tier",
              "outputs/validation_reports/2026_per_trust_tier.csv",
              "csv",
              "2026 per-trust-tier rollup (4 rows): HIGH / MEDIUM / COLD_START / DIVISION_FLOOR"),
    TableSpec("val_recall_pivot",
              "outputs/validation_reports/2026_daily_division_pivot_recall.csv",
              "csv",
              "2026 (date rows × division cols) recall pivot — Excel/heatmap-ready"),
)


def _normalize_path(path: Path) -> str:
    """Return a forward-slashed absolute path that DuckDB accepts on Windows."""
    return str(path.resolve()).replace("\\", "/")


def list_tables(only_existing: bool = True) -> list[TableSpec]:
    """Return the catalog. By default, only entries whose backing file exists."""
    if not only_existing:
        return list(CATALOG)
    return [s for s in CATALOG if (ROOT / s.path).exists()]


def connect(extra: Iterable[TableSpec] = ()) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with all CATALOG views registered.

    Parameters
    ----------
    extra : iterable of TableSpec
        Additional ad-hoc views to register on top of the standard catalog
        (e.g. `TableSpec('my_csv', 'tmp/my.csv', 'csv', '...')`).

    Returns
    -------
    duckdb.DuckDBPyConnection
        Ready-to-query connection. Caller is responsible for `con.close()`
        (or use as context manager).

    Notes
    -----
    Re-opening the connection is the way to refresh views against
    newly-written files. The catalog itself is read-only.
    """
    con = duckdb.connect(":memory:")
    n_ok = 0
    n_skip = 0
    for spec in (*CATALOG, *extra):
        path = ROOT / spec.path
        if not path.exists():
            n_skip += 1
            continue
        path_str = _normalize_path(path)
        if spec.format == "parquet":
            sql = f"CREATE OR REPLACE VIEW {spec.name} AS SELECT * FROM read_parquet('{path_str}')"
        elif spec.format == "csv":
            # Explicit quote+escape handle beat names like "Ghoghal_F,V," that
            # contain literal commas inside quoted fields. Default read_csv_auto
            # was failing to parse these.
            sql = (
                f"CREATE OR REPLACE VIEW {spec.name} AS "
                f"SELECT * FROM read_csv('{path_str}', header=true, "
                f"auto_detect=true, quote='\"', escape='\"', "
                f"sample_size=-1, ignore_errors=false)"
            )
        else:
            n_skip += 1
            continue
        try:
            con.execute(sql)
            n_ok += 1
        except Exception as exc:
            # Don't kill the whole connection if one file is corrupt.
            con.execute(
                f"CREATE OR REPLACE VIEW {spec.name} AS "
                f"SELECT 'register-failed: {type(exc).__name__}'::VARCHAR AS error"
            )
            n_skip += 1
    # Stash the registration tally on the connection for `--list` to surface
    con.execute(
        "CREATE OR REPLACE TEMP TABLE _catalog_meta AS "
        f"SELECT {n_ok}::INTEGER AS n_registered, {n_skip}::INTEGER AS n_skipped"
    )
    return con


def describe(con: duckdb.DuckDBPyConnection, name: str) -> list[tuple]:
    """Return the column schema of a registered view as (name, type, ...) tuples."""
    return con.sql(f"DESCRIBE {name}").fetchall()
