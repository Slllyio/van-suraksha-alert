"""Find and delete corrupted Earth Engine CSVs (empty, mixed column counts, duplicated keys) in MP division folders
whose feature tables are incomplete, so mp_ee.py / mp_features.py regenerate them. Prints what it removes."""
import csv, sys
from pathlib import Path
import pandas as pd

MP = Path(r"E:\FIRE\mp")
divs = [p.parent.name for p in MP.glob("*/grid_500m.geojson")
        if len(list((p.parent / "feats").glob("season_*.parquet"))) < 11]
print("incomplete divisions:", len(divs), divs)


def bad(f: Path) -> str:
    try:
        if f.stat().st_size == 0:
            return "empty"
        with open(f, newline="") as fh:
            widths = {len(r) for r in csv.reader(fh)}
        if len(widths) != 1:
            return f"mixed widths {sorted(widths)[:4]}"
        x = pd.read_csv(f)
        if len(x) == 0:
            return "no rows"
        key = [c for c in ("date", "time", "cell_id") if c in x.columns]
        if key and x.duplicated(key).any():
            return f"duplicate {key}"
    except Exception as e:
        return f"unreadable: {type(e).__name__}"
    return ""


removed = 0
for d in divs:
    ee = MP / d / "ee"
    for f in list(ee.glob("*.csv")) + list((ee / "_parts").glob("*.csv")):
        why = bad(f)
        if why:
            print(f"  {d}: remove {f.relative_to(MP)} ({why})")
            f.unlink(); removed += 1
    # a final file built from bad parts is suspect too: drop finals whose parts were removed
    for final in ("modis_ndvi_ndmi", "modis_lst", "era5land_daily"):
        if not list((ee / "_parts").glob(f"{final}_*.csv")) and (ee / f"{final}.csv").exists() and bad(ee / f"{final}.csv"):
            (ee / f"{final}.csv").unlink(); removed += 1
    for p in (MP / d / "feats").glob("season_*.parquet"):
        pass  # complete seasons are kept; mp_features skips them
print("removed", removed, "files")
(MP / "repair_divisions.txt").write_text("\n".join(divs))
