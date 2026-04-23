"""dq -- DuckDB Query CLI for the JwalaNetra FIRE project.

Thin wrapper around `src.utils.duckdb_catalog.connect()` that opens a
DuckDB connection with all project parquets + CSVs registered as named
views, then runs a SQL query.

Examples
--------
List all available views (and their backing files):
    python scripts/dq.py --list

Describe one view:
    python scripts/dq.py --describe val_per_division_day

Run a query (default: print as text table, max 50 rows):
    python scripts/dq.py "SELECT * FROM val_per_division ORDER BY recall DESC LIMIT 10"

Save query result to CSV:
    python scripts/dq.py --csv tmp/out.csv "SELECT * FROM val_per_beat_day WHERE division='Damoh'"

Increase row limit:
    python scripts/dq.py --limit 200 "SELECT * FROM firms_consolidated WHERE acq_date='2026-04-22'"

Run query from a .sql file:
    python scripts/dq.py --file queries/my_query.sql
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows console defaults to cp1252; DuckDB's pretty-printer emits box-drawing
# Unicode that crashes the encoder. Reconfigure stdout to UTF-8 if available.
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except (AttributeError, OSError):
    pass

# Allow running as `python scripts/dq.py` from the project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.duckdb_catalog import connect, list_tables, describe


def cmd_list() -> int:
    con = connect()
    n_ok, n_skip = con.execute("SELECT n_registered, n_skipped FROM _catalog_meta").fetchone()
    print(f"Registered views: {n_ok} (skipped {n_skip} -- backing file missing)")
    print()
    print(f"{'view':28s} {'rows':>10s}  description")
    print("-" * 100)
    for spec in list_tables():
        try:
            n = con.sql(f"SELECT COUNT(*) FROM {spec.name}").fetchone()[0]
            rows = f"{n:,}"
        except Exception as exc:
            rows = f"ERR ({type(exc).__name__})"
        print(f"{spec.name:28s} {rows:>10s}  {spec.description}")
    con.close()
    return 0


def cmd_describe(view: str) -> int:
    con = connect()
    try:
        rows = describe(con, view)
    except Exception as exc:
        print(f"ERROR: cannot DESCRIBE {view}: {exc}", file=sys.stderr)
        return 1
    print(f"DESCRIBE {view}")
    print(f"{'column':35s}  type           null  key  default extra")
    print("-" * 100)
    for r in rows:
        # DuckDB DESCRIBE returns (column_name, column_type, null, key, default, extra)
        cols = [str(x) if x is not None else "" for x in r]
        cols += [""] * (6 - len(cols))
        print(f"{cols[0]:35s}  {cols[1]:14s} {cols[2]:5s} {cols[3]:4s} {cols[4]:7s} {cols[5]}")
    con.close()
    return 0


def cmd_query(sql: str, limit: int, csv_out: str | None) -> int:
    con = connect()
    sql = sql.strip().rstrip(";")
    if csv_out:
        # Stream straight to CSV via DuckDB COPY -- no in-memory materialisation
        out_path = Path(csv_out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wrapped = f"COPY ({sql}) TO '{out_path.as_posix()}' (HEADER, DELIMITER ',')"
        try:
            con.execute(wrapped)
        except Exception as exc:
            print(f"ERROR: query failed: {exc}", file=sys.stderr)
            con.close()
            return 1
        # Quick row count for the user
        try:
            n = con.sql(f"SELECT COUNT(*) FROM ({sql}) _").fetchone()[0]
        except Exception:
            n = "?"
        print(f"Wrote {out_path} ({n} rows)")
        con.close()
        return 0

    # Print mode -- enforce the row cap
    try:
        wrapped = f"SELECT * FROM ({sql}) _ LIMIT {limit}"
        rel = con.sql(wrapped)
        # DuckDB has a built-in pretty printer
        rel.show(max_rows=limit, max_width=200)
        # Trailing line: how many rows total (un-limited)
        try:
            total = con.sql(f"SELECT COUNT(*) FROM ({sql}) _").fetchone()[0]
            shown = min(total, limit)
            if total > limit:
                print(f"\n[shown {shown} of {total} rows -- use --limit N to widen, "
                      f"or --csv path/to/out.csv to save all]")
            else:
                print(f"\n[{total} rows total]")
        except Exception:
            pass
    except Exception as exc:
        print(f"ERROR: query failed: {exc}", file=sys.stderr)
        con.close()
        return 1
    con.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dq", description="DuckDB query CLI for the FIRE project")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true", help="list registered views and row counts")
    g.add_argument("--describe", metavar="VIEW", help="show schema of a view")
    g.add_argument("--file", metavar="PATH", help="read SQL from file instead of cmdline")
    p.add_argument("--limit", type=int, default=50, help="cap printed rows (default 50)")
    p.add_argument("--csv", metavar="PATH", help="write result to CSV instead of printing")
    p.add_argument("sql", nargs="?", help="SQL query (or use --file)")
    args = p.parse_args(argv)

    if args.list:
        return cmd_list()
    if args.describe:
        return cmd_describe(args.describe)
    if args.file:
        sql_text = Path(args.file).read_text(encoding="utf-8")
        return cmd_query(sql_text, args.limit, args.csv)
    if args.sql:
        return cmd_query(args.sql, args.limit, args.csv)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
