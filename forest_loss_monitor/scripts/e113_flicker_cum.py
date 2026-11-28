"""Flicker confirmation by class and a cumulative NBR trigger (max-recall view only), Guna, fixed rules (no tuning, so every label set is held out).
Confirmation: the pixel's DW loss year y (first year trees < 0.30 after >= 0.30) must have DW trees <= 0.10 in y + 1 (2025 cannot be confirmed).
Cumulative trigger: Oct-Nov NBR falls >= 0.15 over some 3 consecutive years (NBR[y] - NBR[y+3], y = 2017-2022), woody before (DW trees + shrub 2017-19 >= 0.40),
patches >= 10 px; added to the default tree loss as a max-recall view. Scored with e110's scorer. Writes outputs/final/flicker_cum/. Usage: e113_flicker_cum.py"""
import numpy as np
import pandas as pd
from scipy import ndimage

from common import *
from e33_map10m import jobs
from e72_map_wide import W
from e97_guna_eval import GD, grid, rd
from e98_dw_year import OUTD as DWY, loss_year
from e110_survey_score import context, score, sieve

OD = OUT / "final" / "flicker_cum"


def layers(tr, shp):
    beat = np.load(GD / "guna_beat.npy", mmap_mode="r")
    conf = np.zeros(shp, bool)
    cum = np.zeros(shp, bool)
    H, Wd = shp
    for s, r, c, h, w, p in jobs():
        f = W / p.name
        if not f.exists():
            continue
        col, row = map(int, ~tr * (s.x0 + c * 10, s.y1 - r * 10))
        if row >= H or col >= Wd or row + h <= 0 or col + w <= 0:
            continue
        rs, cs = max(0, -row), max(0, -col)
        re_, ce = min(h, H - row), min(w, Wd - col)
        if not np.asarray(beat[row + rs:row + re_:9, col + cs:col + ce:9]).any():
            continue
        if (DWY / p.name).exists():
            t = np.load(DWY / p.name)["t"].astype("int16")
            y = loss_year(t.astype("uint8"))
            nxt = np.zeros(y.shape, "int16") + 255
            for i in range(8):
                m = y == 2017 + i
                nxt[m] = t[i + 1][m]
            ok = (y > 0) & (y <= 2024) & (nxt <= 10)
            ok = np.repeat(np.repeat(ok, 3, 0), 3, 1)[:h, :w]
            conf[row + rs:row + re_, col + cs:col + ce] = ok[rs:re_, cs:ce]
        z = np.load(f)
        lr = np.stack([z[f"y_lr{yy}"].astype("int16") for yy in range(2017, 2026)])
        valid = lr != -128
        fall = np.zeros((h, w), "int16")
        for i in range(6):
            d = np.where(valid[i] & valid[i + 3], lr[i] - lr[i + 3], -999)
            fall = np.maximum(fall, d)
        woody = (z["d_ea_t"].astype("int16") + z["d_ea_s"].astype("int16")) >= 40
        woody = np.repeat(np.repeat(woody, 3, 0), 3, 1)[:h, :w]
        cm = (fall >= 15) & woody
        cum[row + rs:row + re_, col + cs:col + ce] = cm[rs:re_, cs:ce]
    return conf, cum


def main():
    OD.mkdir(parents=True, exist_ok=True)
    tr, shp = grid()
    ctx = context(tr, shp)
    a, yr = rd("guna_default"), rd("guna_year")
    conf, cum = layers(tr, shp)
    gm = np.load(GD / "guna_beat.npy") > 0
    cl, th = (a == 1), (a == 2)
    cumv = sieve((cum & gm & (a == 0)).astype("uint8"), 10).astype(bool)
    variants = {
        "default tree loss (clearing + tree-to-shrub)": cl | th,
        "clearing only": cl, "clearing, confirmed (DW trees <= 0.10 next year)": cl & conf,
        "tree-to-shrub only": th, "tree-to-shrub, confirmed": th & conf,
        "default with confirmation on tree-to-shrub only": cl | (th & conf),
        "default with confirmation on both": (cl | th) & conf,
        "max-recall view: default + cumulative NBR trigger": cl | th | cumv,
        "cumulative NBR trigger alone (new area)": cumv,
    }
    out, areas = [], []
    for nm, m in variants.items():
        code = sieve(m.astype("uint8"), 10)
        r, _ = score(nm, code, np.where(code > 0, yr, 0), tr, shp, ctx)
        out.append(r[~r.label_set.str.startswith(("155", "222 Bamori polygons"))])
        areas.append(dict(method=nm, guna_ha=round(float((code > 0).sum()) * .01)))
        print("scored", nm, flush=True)
    R = pd.concat(out)
    W_ = R.pivot_table(index=["label_set", "metric"], columns="method", values="value", aggfunc="first", sort=False)
    W_.to_csv(OD / "flicker_cum_scores.csv")
    pd.DataFrame(areas).to_csv(OD / "flicker_cum_areas.csv", index=False)
    pd.set_option("display.width", 300)
    pd.set_option("display.max_colwidth", 26)
    print(W_.T.to_string())
    print(pd.DataFrame(areas).to_string())


if __name__ == "__main__":
    main()
