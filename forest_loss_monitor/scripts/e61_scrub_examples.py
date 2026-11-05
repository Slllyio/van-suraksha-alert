"""Side-by-side examples for the scrub-to-farm decision: flagged points I called already farmed in 2018-19, and Bamori polygons that look alike. Uses saved chips. Usage: e61_scrub_examples.py"""
import numpy as np
from PIL import Image, ImageDraw

from common import *
from e51_chips import CH, HI, LO, SCALE

OUTD = OUT / "interim" / "report" / "scrub_examples"
TIGHT = [61, 133, 149, 253, 261, 291]
LOOSE = [37, 63, 153]                # also flagged at the loose setting and labelled already farmed: the tight setting has only 6
BAMORI = [500482, 500519, 500458, 500364, 500360, 500447, 500534, 500391, 500386, 500517]
P = 81 * SCALE
NAMES = ("Winter 2018-19", "Winter 2023-24", "Oct-Nov 2018-19", "Oct-Nov 2023-24")


def card(pid, title):
    a = np.load(CH / f"{pid}.npy")
    S = 2 * P + 2
    can = Image.new("RGB", (S, S + 32), "white")
    d = ImageDraw.Draw(can)
    d.text((2, 2), title, fill="black")
    for q, (dx, dy) in enumerate(((0, 0), (P + 2, 0), (0, P + 2), (P + 2, P + 2))):
        im = Image.fromarray((np.clip((a[q] - LO) / (HI - LO), 0, 1) * 255).astype("uint8")).resize((P, P), Image.NEAREST)
        c = P // 2
        d2 = ImageDraw.Draw(im)
        d2.rectangle([c - 7, c - 7, c + 7, c + 7], outline="yellow")
        d2.text((3, 3), NAMES[q], fill="white")
        can.paste(im, (dx, 32 + dy))
    return can


def sheet(items, name, head):
    w = 2 * P + 16
    h = 2 * P + 46
    can = Image.new("RGB", (5 * w, 26 + 2 * h), "white")
    ImageDraw.Draw(can).text((6, 6), head, fill="black")
    for j, (pid, t) in enumerate(items):
        can.paste(card(pid, t), ((j % 5) * w, 26 + (j // 5) * h))
    can.save(OUTD / name)


def main():
    OUTD.mkdir(parents=True, exist_ok=True)
    sheet([(600000 + i, f"Random point {i}, tight") for i in TIGHT] + [(600000 + i, f"Random point {i}, loose only") for i in LOOSE], "A_flagged_called_already_farm.png", "Flagged by the rule; I labelled these already farmed in 2018-19. False colour: bright red = green crop or forest. Yellow box = 50 m.")
    sheet([(i, f"Your Bamori polygon {i - 500000}") for i in BAMORI], "B_bamori_polygons.png", "Your validated Bamori polygons that look similar. Same bands and years.")
    print("saved")


if __name__ == "__main__":
    main()
