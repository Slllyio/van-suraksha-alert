"""Same chips for a sample of the owner's Bamori shrub/bare-to-crop polygons, with the flagged random points beside them, to calibrate my labels against the owner's. Usage: e57_bamori_chips.py"""
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from common import *
from e33_map10m import init_retry
from e48_tests import GT
from e51_chips import CH, HI, LO, SCALE, chip


def main():
    init_retry()
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    q = g[(g.source == "bamori_validated") & g.cls.isin(["shrub_to_crop", "bare_to_crop"])].sample(20, random_state=5)
    for s in q.itertuples():
        chip(s)
    r = pd.read_csv(GT / "s2f_random300.csv")
    extra = r[r.pid.isin([600000 + i for i in (61, 133, 149, 253, 261, 291, 52, 170)])]
    P = 81 * SCALE
    S, gap = 2 * P + 2, 14
    items = [(s.pid, f"{s.cls[:5]} {s.pid}") for s in q.itertuples()]
    can = Image.new("RGB", (5 * (S + gap), 4 * (S + gap + 12)), "white")
    dr = ImageDraw.Draw(can)
    for j, (pid, lab) in enumerate(items):
        a = np.load(CH / f"{pid}.npy")
        x0, y0 = (j % 5) * (S + gap), (j // 5) * (S + gap + 12)
        dr.text((x0 + 2, y0), lab, fill="black")
        for k, (dx, dy) in enumerate(((0, 0), (P + 2, 0), (0, P + 2), (P + 2, P + 2))):
            im = Image.fromarray((np.clip((a[k] - LO) / (HI - LO), 0, 1) * 255).astype("uint8")).resize((P, P), Image.NEAREST)
            c = P // 2
            ImageDraw.Draw(im).rectangle([c - 7, c - 7, c + 7, c + 7], outline="yellow")
            can.paste(im, (x0 + dx, y0 + 12 + dy))
    can.save(OUT / "s2f_sheets" / "bamori_sample.png")
    print("saved")


if __name__ == "__main__":
    main()
