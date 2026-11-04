"""Calibration: blind chips of candidate pixels binned by NBR drop on the calibration tiles.
Writes shuffled contact sheets; the key (bin, attributes) stays in calib_key.csv until labels are done."""
import numpy as np
import pandas as pd
import rasterio
from PIL import Image

from chips import make_chips
from common import *

SEED = 7
BINS = [(800, 1200), (1200, 1600), (1600, 2000), (2000, 2500), (2500, 3000), (3000, 4000), (4000, 20000)]
PER_BIN_TILE = 6
MIN_PRE_NDVI = 3000     # permissive here; the threshold itself is what is being calibrated


def main():
    d = OUT / "calibration"
    d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    rows = []
    for s in t[t.cal != ""].itertuples():
        f = WORK / "lt_v2" / f"{s.tile}.tif"
        with rasterio.open(f) as src:
            A = {n: src.read(i + 1) for i, n in enumerate(src.descriptions)}
        with rasterio.open(WORK / "zone_beat.tif") as z:
            zone = z.read(1, window=((s.row, s.row + s.h), (s.col, s.col + s.w)))
        cand = (zone > 0) & (A["yod"] > 0) & (A["pre_ndvi"] >= MIN_PRE_NDVI)
        for lo, hi in BINS:
            ii = np.flatnonzero(cand & (A["mag"] >= lo) & (A["mag"] < hi))
            for p in rng.choice(ii, min(PER_BIN_TILE, len(ii)), replace=False):
                r, c = np.unravel_index(p, zone.shape)
                row = dict(tile=s.tile, area=s.cal, bin=f"{lo}-{hi}", x=s.x0 + (c + .5) * RES, y=s.y1 - (r + .5) * RES,
                           map_year=int(A["yod"][r, c]))
                row.update({k: int(A[k][r, c]) for k in ("dur", "mag", "pre_ndvi", "post_ndvi", "rec_ndvi", "last_ndvi", "base_ndvi", "burned", "hansen_year", "treecover")})
                rows.append(row)
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    df.insert(0, "sample_id", np.arange(1, len(df) + 1))
    df.to_csv(d / "calib_key.csv", index=False)
    init()
    make_chips(df, d / "chips")
    sheets(df, d)


def sheets(df, d, per_sheet=20):
    """Contact sheets: one row per sample, id burnt into the file order only (see sheet index)."""
    ids = df.sample_id.tolist()
    for k in range(0, len(ids), per_sheet):
        part = ids[k:k + per_sheet]
        ims = [Image.open(d / "chips" / f"{i:04d}.png") for i in part]
        w, h = ims[0].size
        cols = 2
        rows = int(np.ceil(len(ims) / cols))
        sheet = Image.new("RGB", (cols * (w + 40), rows * (h + 4)), "white")
        from PIL import ImageDraw
        dr = ImageDraw.Draw(sheet)
        for j, (i, im) in enumerate(zip(part, ims)):
            x, y = (j % cols) * (w + 40), (j // cols) * (h + 4)
            dr.text((x + 2, y + 40), str(i), fill="black")
            sheet.paste(im, (x + 40, y))
        sheet.save(d / f"sheet_{k // per_sheet:02d}.png")
    print("sheets", (len(ids) + per_sheet - 1) // per_sheet)


if __name__ == "__main__":
    main()
