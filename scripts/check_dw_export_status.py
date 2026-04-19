"""Quick GEE status checker for the DW export tasks."""
from __future__ import annotations

import sys
from collections import Counter

import ee


def main() -> int:
    ee.Initialize(project="van-suraksha-alert")
    ops = ee.data.listOperations()
    dw_ops = [op for op in ops
              if "dw_features" in str(op.get("metadata", {}).get("description", ""))]
    states = Counter(op.get("metadata", {}).get("state", "?") for op in dw_ops)
    print(f"Total dw_features tasks: {len(dw_ops)}")
    for state, count in sorted(states.items(), key=lambda x: -x[1]):
        print(f"  {state}: {count}")
    # By year
    from collections import defaultdict
    by_year = defaultdict(lambda: Counter())
    for op in dw_ops:
        desc = op.get("metadata", {}).get("description", "")
        state = op.get("metadata", {}).get("state", "?")
        # filename pattern dw_features_YYYY_cNN
        parts = desc.split("_")
        year = parts[2] if len(parts) > 2 else "?"
        by_year[year][state] += 1
    print()
    for year in sorted(by_year):
        cnts = by_year[year]
        print(f"  {year}: ", " | ".join(f"{s}={c}" for s, c in cnts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
