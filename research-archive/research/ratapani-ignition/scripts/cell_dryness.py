"""Within-beat weather proxies at 500 m.

1. insolation.npy  (cells x 172 days): clear-sky noon solar index on the cell's slope/aspect for each day
   of year (Jan 1 .. Jun 20), relative to a flat surface. Sun-facing slopes dry faster.
2. s2_cells.parquet: per season, clear date and cell, the mean NDMI, NBR and NDVI of the cell's eligible
   pixels from the Sentinel-2 / Landsat observations used for the labels (fuel moisture proxies).
Usage: python cell_dryness.py <ign_dir> <obsroot> <out_dir>
"""
import os, sys, glob, datetime as dt
import numpy as np, pandas as pd

sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts")
import fetch, detect

LAT = np.radians(22.95)


def insolation(cells):
    doys = np.arange(1, 173)
    decl = np.radians(23.44) * np.sin(2 * np.pi * (284 + doys) / 365)
    zen = np.abs(LAT - decl)                        # solar zenith at noon
    slope = np.radians(cells.slope.values)[:, None]
    # mean aspect from northness/eastness; sun is due south at noon (declination < latitude all season)
    asp = np.arctan2(cells.eastness.values, cells.northness.values)[:, None]
    cosi = np.cos(slope) * np.cos(zen)[None] + np.sin(slope) * np.sin(zen)[None] * np.cos(np.pi - asp)
    return np.clip(cosi, 0, None) / np.cos(zen)[None]


def s2_cells(ign_dir, obsroot):
    cell = np.load(os.path.join(ign_dir, "cell_px.npy"))
    lc = np.load(fetch.WORLDCOVER)
    ok0 = (cell >= 0) & np.isin(lc, detect.LANDCOVER_OK)
    n = cell.max() + 1
    rows = []
    for ydir in sorted(glob.glob(os.path.join(obsroot, "[12]*"))):
        y = int(os.path.basename(ydir))
        for f in sorted(glob.glob(os.path.join(ydir, "*.npz"))):
            z = np.load(f); v = z["valid"] & ok0
            r = {k: z[k].astype(np.float32) / 1e4 for k in ("red", "nir", "swir1", "swir2")}
            if f.endswith("_s2.npz"):
                for k in detect.S2_TO_LS: r[k] *= detect.S2_TO_LS[k]
            cnt = np.bincount(cell[v], minlength=n)
            def m(a): return np.bincount(cell[v], weights=a[v], minlength=n) / np.maximum(cnt, 1)
            with np.errstate(all="ignore"):
                ndmi = m((r["nir"] - r["swir1"]) / (r["nir"] + r["swir1"] + 1e-6))
                nbr = m((r["nir"] - r["swir2"]) / (r["nir"] + r["swir2"] + 1e-6))
                ndvi = m((r["nir"] - r["red"]) / (r["nir"] + r["red"] + 1e-6))
            keep = cnt >= 100   # at least 4 ha of the cell seen clear
            rows.append(pd.DataFrame(dict(season=y, date=os.path.basename(f)[:10], cell_id=np.where(keep)[0],
                                          ndmi=ndmi[keep], nbr=nbr[keep], ndvi=ndvi[keep])))
        print(y, flush=True)
    df = pd.concat(rows); df["date"] = pd.to_datetime(df.date)
    return df.sort_values(["season", "cell_id", "date"]).drop_duplicates(["season", "cell_id", "date"], keep="last")


def main(ign_dir, obsroot, out_dir):
    cells = pd.read_csv(os.path.join(ign_dir, "cells_static.csv"))
    ins = insolation(cells)
    np.save(os.path.join(out_dir, "insolation.npy"), ins.astype(np.float32))
    pd.Series(cells.cell_id.values).to_csv(os.path.join(out_dir, "insolation_cells.csv"), index=False, header=["cell_id"])
    print("insolation range", ins.min().round(2), ins.max().round(2))
    df = s2_cells(ign_dir, obsroot)
    df.to_parquet(os.path.join(out_dir, "s2_cells.parquet"), index=False)
    print(len(df), df.groupby("season").size().to_dict())


if __name__ == "__main__":
    main(*sys.argv[1:4])
