"""Label sheets for the blind Guna sample: per spot, Oct-Nov NDVI 2017-2025 at 10 m (510 m window, centre marked) and the annual DW trees at the centre.
No map, stratum or rule output is shown. Writes outputs/final/guna_sample/sheets/sheet_NN.png. Usage: e103_sample_sheets.py"""
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from e33_map10m import jobs
from e72_map_wide import W
from e98_dw_year import OUTD as DWY

SD = OUT / "final" / "guna_sample"
PER, HALF = 12, 25
YS = range(2017, 2026)


def main():
    p = pd.read_csv(SD / "sample_points.csv")
    idx = [(s.x0 + c * 10, s.y1 - r * 10, h, w, pp.name) for s, r, c, h, w, pp in jobs()]
    (SD / "sheets").mkdir(exist_ok=True)
    for k0 in range(0, len(p), PER):
        q = p.iloc[k0:k0 + PER]
        fig, ax = plt.subplots(len(q), 9, figsize=(13.5, 1.6 * len(q)))
        for i, r in enumerate(q.itertuples()):
            f = next(t for t in idx if t[0] <= r.x < t[0] + t[3] * 10 and t[1] - t[2] * 10 < r.y <= t[1] and (W / t[4]).exists())
            cc, rr = int((r.x - f[0]) / 10), int((f[1] - r.y) / 10)
            with np.load(W / f[4]) as z:
                v = {y: z[f"y_ln{y}"][max(rr - HALF, 0):rr + HALF + 1, max(cc - HALF, 0):cc + HALF + 1].astype(float) for y in YS}
            t = np.load(DWY / f[4])["t"][:, min(rr // 3, 299), min(cc // 3, 299)] if (DWY / f[4]).exists() else np.full(9, 255)
            for j, y in enumerate(YS):
                a = ax[i, j]
                a.imshow(np.where(v[y] == -128, np.nan, v[y] / 100), cmap="RdYlGn", vmin=0, vmax=.8)
                a.plot(min(cc, HALF), min(rr, HALF), "c+", ms=8, mew=1.2)
                a.set_xticks([]), a.set_yticks([])
                a.set_title(f"{y} DWt {'-' if t[j] == 255 else t[j] / 100:.2}" if t[j] != 255 else f"{y} DWt -", fontsize=6)
            ax[i, 0].set_ylabel(f"spot {r.sid}", fontsize=8)
        plt.tight_layout()
        plt.savefig(SD / "sheets" / f"sheet_{k0 // PER:02d}.png", dpi=80)
        plt.close()
    print("sheets", -(-len(p) // PER))


if __name__ == "__main__":
    main()
