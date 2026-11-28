"""Sheets of round-2 points the map rule flags and I labelled not lost, by zone, from the saved 30 m chips. Usage: e78_false_sheets.py"""
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from common import *
from e48_tests import by_point, load, rule
from zones import zone as zone_of

k = pd.read_csv(OUT / "validation2" / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv").merge(pd.read_csv(OUT / "validation2" / "prelabels.csv"), on="sample_id").assign(pid=lambda d: d.sample_id + 200000)
p = load()
p = p[p.pid.isin(k.pid)].reset_index(drop=True)
f = by_point(p, rule(p)[0], 1).reindex(k.pid).fillna(False).values
k["zone"] = k.Division.map(zone_of)
q = k[f & ~k.label.isin(list("LD"))].sort_values(["zone", "sample_id"])
q.to_csv(WORK / "false_alarm_points.csv", index=False)
print(pd.crosstab(q.zone, q.label).to_string())
out = OUT / "false_sheets"
out.mkdir(exist_ok=True)
for z, g in q.groupby("zone"):
    for i in range(0, len(g), 18):
        sub = g.iloc[i:i + 18]
        ims = [Image.open(OUT / "validation2" / "chips" / f"{s:04d}.png").convert("RGB") for s in sub.sample_id]
        w, h = ims[0].size
        w2, h2 = w // 2 * 2 // 2, h
        can = Image.new("RGB", (2 * (w + 8), 9 * (h + 14)), "white")
        d = ImageDraw.Draw(can)
        for j, (im, s, l) in enumerate(zip(ims, sub.sample_id, sub.label)):
            x, y = (j % 2) * (w + 8), (j // 2) * (h + 14)
            d.text((x + 2, y), f"{s} mine={l}", fill="black")
            can.paste(im, (x, y + 12))
        can.save(out / f"{z[:5]}_{i // 18}.png")
        print(z, i, can.size)
