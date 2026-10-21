"""Static inputs for a new season: season S uses the AlphaEarth embedding of year S-1, put through each division's own
PCA-16 (ae_pca.npz: fitted on 2017-2024, exactly as the live models). Everything else is copied from static_inputs.parquet.
Needs earthengine-api (project with Earth Engine access), numpy, pandas.

Usage:
  python make_static_season.py --season 2027 --models <pc_models> [--divisions A,B] [--project <ee project>]
      -> <pc_models>/static_inputs_2027.parquet       (needs the 2026 embedding to be published)
  python make_static_season.py --season 2026 --models <pc_models> --check
      -> rebuilds the 2026 ae00-ae15 from the 2025 embedding and compares them with static_inputs.parquet

Embedding per 500 m square: mean of the 64 bands over the square at 10 m in EPSG:32643 (as mp/scripts/mp_ee.py);
squares missing in a year are filled with that year's division mean before the PCA (as the pipeline)."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

NCOL, X0, Y1, S = 1829, 399000.0, 2996000.0, 500.0
BANDS = [f"A{k:02d}" for k in range(64)]


def embedding(ee, cells, year, batch=500):
    """mean embedding per square (rows in the order of `cells`), NaN where the year has no data."""
    img = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL").filterDate(f"{year}-01-01", f"{year + 1}-01-01"))
    if img.size().getInfo() == 0:
        raise SystemExit(f"AlphaEarth {year} is not published yet: season {year + 1} cannot be built")
    img = img.mosaic()
    proj = ee.Projection("EPSG:32643")
    rows, i = [], 0
    while i < len(cells):
        sub = cells[i:i + batch]
        feats = [ee.Feature(ee.Geometry.Rectangle([X0 + (c % NCOL) * S, Y1 - (c // NCOL + 1) * S,
                                                    X0 + (c % NCOL + 1) * S, Y1 - (c // NCOL) * S], proj, False),
                            {"cell": int(c)}) for c in sub]
        res = img.reduceRegions(collection=ee.FeatureCollection(feats), reducer=ee.Reducer.mean(), scale=10,
                                crs="EPSG:32643", tileScale=4).map(lambda f: ee.Feature(None, f.toDictionary()))
        try:
            rows += [f["properties"] for f in res.getInfo()["features"]]
            i += len(sub)
        except ee.EEException:
            if batch <= 25:
                raise
            batch //= 2
    return pd.DataFrame(rows).set_index("cell").reindex(cells)[BANDS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True); ap.add_argument("--models", required=True)
    ap.add_argument("--divisions", default=None); ap.add_argument("--project", default="van-suraksha-alert")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    import ee
    ee.Initialize(project=a.project)
    M = Path(a.models)
    static = pd.read_parquet(M / "static_inputs.parquet")
    pca = np.load(M / "ae_pca.npz")
    divs = a.divisions.split(",") if a.divisions else sorted(static.division.unique())
    parts, worst = [], 0.0
    for dv in divs:
        st = static[static.division == dv].copy()
        cells = st.cell.to_numpy()
        e = embedding(ee, cells, a.season - 1)
        X = e.fillna(e.mean()).to_numpy()
        ae = ((X - pca[f"{dv}__mean"]) @ pca[f"{dv}__components"].T).astype(np.float32)
        if a.check:
            d = float(np.nanmax(np.abs(ae - st[[f"ae{k:02d}" for k in range(16)]].to_numpy())))
            worst = max(worst, d); print(dv, "max abs diff vs static_inputs", d, flush=True)
        for k in range(16):
            st[f"ae{k:02d}"] = ae[:, k]
        parts.append(st)
        print(dv, len(st), flush=True)
    if a.check:
        print("worst", worst)
        return
    out = M / f"static_inputs_{a.season}.parquet"
    pd.concat(parts, ignore_index=True).to_parquet(out, index=False, compression="zstd")
    print("wrote", out)


if __name__ == "__main__":
    main()
