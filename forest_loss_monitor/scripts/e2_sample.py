"""AlphaEarth route, step 2: blind chips of candidates drawn across embedding change-score quantiles, plus plain random
forest pixels, on the calibration tiles. Year label for a candidate = its year of largest embedding change."""
import numpy as np
import pandas as pd
import rasterio

from calibrate_sample import sheets
from chips import make_chips
from common import *

SEED = 11
# quantile bands of the max change score among forest pixels of the tile
BANDS = [(0.999, 1.0), (0.995, 0.999), (0.98, 0.995), (0.9, 0.98), (0.0, 0.9)]
PER = 10


def main():
    d = OUT / "calibration_emb"
    d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    rows = []
    for s in t[t.cal != ""].itertuples():
        with rasterio.open(WORK / "emb_score" / f"{s.tile}.tif") as src:
            names = list(src.descriptions)
            c = src.read()
        with rasterio.open(WORK / "zone_beat.tif") as z:
            zone = z.read(1, window=((s.row, s.row + s.h), (s.col, s.col + s.w)))
        years = np.array([int(n[1:]) for n in names])
        top = c.max(0)
        yr = years[c.argmax(0)]
        f = zone > 0
        lims = np.quantile(top[f], [q for b in BANDS for q in b])
        for k, (lo, hi) in enumerate(BANDS):
            a, b = lims[2 * k], lims[2 * k + 1]
            ii = np.flatnonzero(f & (top >= a) & (top <= b))
            for p in rng.choice(ii, min(PER, len(ii)), replace=False):
                r, col = np.unravel_index(p, zone.shape)
                rows.append(dict(tile=s.tile, area=s.cal, band=f"{lo}-{hi}", x=s.x0 + (col + .5) * RES, y=s.y1 - (r + .5) * RES,
                                 map_year=int(yr[r, col]), score=int(top[r, col])))
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    df.insert(0, "sample_id", np.arange(1001, 1001 + len(df)))
    df.to_csv(d / "calib_key.csv", index=False)
    init()
    make_chips(df, d / "chips")
    sheets(df, d)


if __name__ == "__main__":
    main()
