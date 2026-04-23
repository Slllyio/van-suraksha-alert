# DuckDB query recipes — JwalaNetra FIRE project

DuckDB lets us run SQL directly against the project's parquet + CSV files
without ETL. All long-lived files are registered as named views by
`src/utils/duckdb_catalog.py`. The CLI wrapper is `scripts/dq.py`.

This file is a **cookbook** of useful queries, not exhaustive — adapt them
to whatever you're investigating.

## Setup (one-time)

```bash
# duckdb is already in requirements.txt -- just verify
python -c "import duckdb; print(duckdb.__version__)"
# Expect: 1.4.4 or newer
```

## CLI basics

```bash
# 1. List all available views + row counts
python scripts/dq.py --list

# 2. Show schema of a view
python scripts/dq.py --describe val_per_division_day

# 3. Run a query (default cap 50 rows; widen with --limit N)
python scripts/dq.py --limit 100 "SELECT * FROM val_per_division ORDER BY recall DESC"

# 4. Save query result to CSV (no row cap; streams via DuckDB COPY)
python scripts/dq.py --csv tmp/dq/out.csv "SELECT * FROM val_per_beat_day WHERE division='Damoh'"

# 5. Run SQL from a file
python scripts/dq.py --file queries/my_analysis.sql
```

## Python API

```python
from src.utils.duckdb_catalog import connect, list_tables

con = connect()
df = con.sql("SELECT * FROM val_per_division ORDER BY recall LIMIT 5").df()
con.close()
```

## 12 useful queries

### 1. Worst-recall divisions in the season

```sql
SELECT division,
       SUM(n_fires_observed) AS fires,
       SUM(n_fires_caught)   AS caught,
       ROUND(SUM(n_fires_caught) * 1.0 / NULLIF(SUM(n_fires_observed), 0), 3) AS recall
FROM val_per_division_day
GROUP BY 1
HAVING SUM(n_fires_observed) >= 100
ORDER BY recall ASC
LIMIT 10
```

### 2. Days the model was overwhelmed (most uncovered fires)

```sql
SELECT date,
       SUM(n_fires_observed) AS fires,
       SUM(n_fires_caught)   AS caught,
       SUM(n_fires_observed - n_fires_caught) AS uncovered,
       SUM(n_alerts_total)   AS alerts_issued
FROM val_per_division_day
GROUP BY 1
ORDER BY uncovered DESC
LIMIT 10
```

### 3. Persistent blind-spot beats (≥3 fires + 0 alerts on same day)

```sql
SELECT division, beat,
       COUNT(DISTINCT date) AS days_silent,
       SUM(n_fires_observed) AS uncovered_fires,
       MAX(n_fires_observed) AS peak_day
FROM val_per_beat_day
WHERE n_fires_observed >= 3 AND n_alerts_total = 0
GROUP BY 1, 2
ORDER BY uncovered_fires DESC
LIMIT 25
```

### 4. JOIN: per-division recall vs same-day fire weather

```sql
SELECT vdpd.date, vdpd.division,
       vdpd.n_fires_observed AS fires,
       ROUND(vdpd.catch_rate, 3) AS recall,
       ROUND(fwi.ffmc, 1) AS ffmc,
       fwi.danger_class
FROM val_per_division_day vdpd
LEFT JOIN fwi_daily fwi ON vdpd.date = fwi.date
WHERE vdpd.n_fires_observed > 100
ORDER BY vdpd.date, vdpd.n_fires_observed DESC
```

### 5. Weekly trend of recall + alert volume

```sql
SELECT date_trunc('week', date) AS week,
       SUM(n_fires_observed) AS fires,
       SUM(n_fires_caught)   AS caught,
       ROUND(SUM(n_fires_caught) * 1.0 / NULLIF(SUM(n_fires_observed), 0), 3) AS week_recall,
       SUM(n_critical_organic) AS crit_organic,
       SUM(n_critical_floor)   AS crit_floor
FROM val_per_division_day
GROUP BY 1
ORDER BY 1
```

### 6. Today's NRT fires in a specific division (uses portal-fresh data)

```sql
SELECT acq_date, acq_time,
       ROUND(latitude, 3) AS lat,
       ROUND(longitude, 3) AS lon,
       confidence,
       ROUND(frp, 1) AS frp_mw
FROM firms_nrt
WHERE acq_date >= current_date - 2
ORDER BY acq_date DESC, frp DESC
LIMIT 50
```

### 7. Per-fire spatial offset distribution (caught vs missed)

```sql
SELECT
  CASE
    WHEN spatial_offset_km IS NULL THEN 'MISSED'
    WHEN spatial_offset_km < 2     THEN '0-2 km'
    WHEN spatial_offset_km < 4     THEN '2-4 km'
    WHEN spatial_offset_km < 8     THEN '4-8 km'
    ELSE '>8 km'
  END AS bucket,
  COUNT(*) AS n_events,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM val_per_fire
GROUP BY 1
ORDER BY MIN(COALESCE(spatial_offset_km, 999))
```

### 8. Climatology floor: top historical-burn beats this current week

```sql
WITH this_week AS (
  SELECT EXTRACT('week' FROM current_date)::INT AS w
)
SELECT bc.Division, bc.Beat,
       bc.total_fires AS five_yr_total,
       bc.mean_fires_per_year,
       ROUND(bc.percentile_in_week, 3) AS percentile,
       ROUND(bc.max_frp_seen, 1) AS peak_frp_5yr
FROM beat_climatology bc, this_week
WHERE bc.week_of_year = this_week.w
ORDER BY bc.total_fires DESC
LIMIT 20
```

### 9. Division × week-of-year heatmap (for Excel pivot)

```sql
SELECT division,
       EXTRACT('week' FROM date)::INT AS week,
       SUM(n_fires_observed) AS fires,
       ROUND(SUM(n_fires_caught) * 1.0 / NULLIF(SUM(n_fires_observed), 0), 3) AS recall
FROM val_per_division_day
GROUP BY 1, 2
ORDER BY 1, 2
-- pipe to: --csv tmp/heatmap.csv
-- then pivot in Excel: rows=division, cols=week, values=recall
```

### 10. Field-response feedback summary

```sql
SELECT verdict,
       COUNT(*) AS n,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM field_responses
GROUP BY 1
ORDER BY n DESC
```

### 11. Trust-tier precision over time (uses validation rolling parquet)

```sql
SELECT * FROM v17_validation_rolling
ORDER BY prediction_date DESC
LIMIT 30
```

### 12. Cross-year FIRMS frequency for a single beat (deep history)

```sql
SELECT EXTRACT('year' FROM acq_date)::INT AS year,
       COUNT(*) AS detections,
       ROUND(MAX(frp), 1) AS peak_frp_mw
FROM firms_consolidated
WHERE latitude BETWEEN 24.20 AND 24.30
  AND longitude BETWEEN 80.80 AND 80.85   -- adjust for the beat you care about
  AND confidence IN ('h','n','high','nominal')
GROUP BY 1
ORDER BY 1
```

## Common pitfalls

| Symptom | Fix |
|---|---|
| `cannot find module src.utils.duckdb_catalog` | Run from project root (`cd e:/FIRE`); `scripts/dq.py` adds ROOT to `sys.path` |
| `cp1252 encoding` crash on Windows | Already fixed in `dq.py` via `sys.stdout.reconfigure(utf-8)`. If you're using DuckDB elsewhere, do the same. |
| Stale data | Views are `:memory:`-backed against on-disk files. Re-run any time. No cache, no refresh needed. |
| `CREATE TABLE AS COPY ... TO 'project/path'` | DuckDB CAN write through arbitrary paths if you ask it to. Don't write SQL that does that against project paths unless you know what you're doing. There's no programmatic guard. |
| Big result truncation | Default cap is 50 rows. Use `--limit 1000` to widen, or `--csv path` to stream the full result with no cap. |

## When to use DuckDB vs pandas

| Use DuckDB when... | Use pandas when... |
|---|---|
| JOIN across 2+ files | Single-file analysis where the file fits in RAM |
| Running ad-hoc SQL from CLI / Excel | Building a script that needs imperative loops |
| File is bigger than RAM (e.g. firms_consolidated 1.35 M rows) | Final touches before plotting |
| You want grouped aggregations | You're chaining transformations interactively in Jupyter |

DuckDB and pandas play together — `con.sql(...).df()` returns a pandas DataFrame whenever you want to switch rails.
