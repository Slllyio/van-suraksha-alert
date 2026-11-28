"""Extra blind chips from zones the calibration tiles missed (teak, plantation, mixed), drawn across model-score quantiles."""
import numpy as np
import pandas as pd
import rasterio

from calibrate_sample import sheets
from chips import make_chips
from common import *

SEED = 23
BANDS = [(0.999, 1.0), (0.995, 0.999), (0.98, 0.995), (0.9, 0.98), (0.0, 0.9)]
PER = 5
TILES = "r05c04,r05c02,r05c05,r01c04,r04c07,r02c06".split(",")


def main():
    d = OUT / "calibration_extra"
    d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    rows = []
    for tile in TILES:
        s = t.loc[tile]
        with rasterio.open(WORK / "emb_v1" / f"{tile}.tif") as src:
            names = list(src.descriptions)
            zb = [i for i, n in enumerate(names) if n.startswith("z")]
            c = src.read([i + 1 for i in zb])
        years = np.array([int(names[i][1:]) for i in zb])
        with rasterio.open(WORK / "zone_beat.tif") as z:
            zone = z.read(1, window=((s.row, s.row + s.h), (s.col, s.col + s.w)))
        top, yr = c.max(0), years[c.argmax(0)]
        f = zone > 0
        lims = np.quantile(top[f], [q for b in BANDS for q in b])
        for k, (lo, hi) in enumerate(BANDS):
            ii = np.flatnonzero(f & (top >= lims[2 * k]) & (top <= lims[2 * k + 1]))
            for p in rng.choice(ii, min(PER, len(ii)), replace=False):
                r, col = np.unravel_index(p, zone.shape)
                rows.append(dict(tile=tile, area=tile, band=f"{lo}-{hi}", x=s.x0 + (col + .5) * RES, y=s.y1 - (r + .5) * RES,
                                 map_year=int(yr[r, col]), z=int(top[r, col])))
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    df.insert(0, "sample_id", np.arange(2001, 2001 + len(df)))
    df.to_csv(d / "calib_key.csv", index=False)
    init()
    make_chips(df, d / "chips")
    sheets(df, d)


if __name__ == "__main__":
    main()
