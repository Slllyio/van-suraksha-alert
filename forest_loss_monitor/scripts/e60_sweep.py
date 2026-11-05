"""Missed-loss sweep. Random unflagged 10 m pixels in finished chunks by zone; Oct-Nov series fetched at them; those with a moderate fitted fall below the filter's level
go to chips, mixed with random controls, in an order that hides which is which. Usage: e60_sweep.py sample | feats [threads] | select | chips [threads] | sheets | score"""
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import rasterio

from common import *
from e33_map10m import D, init_retry
from e47_px import YS
from e48_tests import GT
from e49_ts import series_feats
from e51_chips import chip
from e53_ts_chunks import fetch_part
from zones import zone as zone_of

PER_ZONE = 600
PTS = WORK / "sweep_points.csv"
FE = WORK / "sweep_feats.csv"
SEL = WORK / "sweep_selected.csv"
BASE = 700000
KEEP_MOD, KEEP_CTL = 50, 12
LO, HI = .05, .15


def sample():
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False).set_index("tile")
    with rasterio.open(WORK / "zone_beat.tif") as src:
        zb = src.read(1)
    b = pd.read_csv(OUT / "beat_lookup.csv")
    zmap = b.set_index("zone_id").Division.map(zone_of)
    rng = np.random.default_rng(20261106)
    rows = []
    for f in sorted(D.glob("*.npz")):
        tile, r, c = f.stem.split("_")
        r, c = int(r), int(c)
        s = t.loc[tile]
        a = np.load(f)["cls"]
        h, w = a.shape
        zz = zb[np.ix_(np.arange(h) // 3 + s.row + r // 3, np.arange(w) // 3 + s.col + c // 3)]
        ii = np.flatnonzero((zz.ravel() > 0) & (a.ravel() == 0))
        if not len(ii):
            continue
        for i in rng.choice(ii, min(40, len(ii)), replace=False):
            rr, cc = np.unravel_index(i, a.shape)
            rows.append(dict(x=s.x0 + (c + cc + .5) * 10, y=s.y1 - (r + rr + .5) * 10, zone_id=int(zz[rr, cc]), n_pool=len(ii)))
    d = pd.DataFrame(rows)
    d["zone"] = d.zone_id.map(zmap)
    d = d.groupby("zone", group_keys=False).apply(lambda q: q.sample(min(PER_ZONE, len(q)), random_state=7)).reset_index(drop=True)
    d.insert(0, "pid", BASE + d.index)
    d.to_csv(PTS, index=False)
    print(d.zone.value_counts().to_dict())


def part(q):
    try:
        return fetch_part(q.x.values, q.y.values, q.pid.values)
    except Exception as e:
        print("failed", str(e)[:120], flush=True)
        return []


def feats(th):
    init_retry()
    d = pd.read_csv(PTS)
    old = pd.read_csv(FE) if FE.exists() else pd.DataFrame(columns=["i"])
    d = d[~d.pid.isin(old.i)].assign(ry=lambda q: (q.y // 30000).astype(int), rx=lambda q: (q.x // 30000).astype(int)).sort_values(["ry", "rx"])
    rows = []
    with ThreadPoolExecutor(th) as ex:
        for k, r in enumerate(ex.map(part, [d.iloc[i:i + 25] for i in range(0, len(d), 25)])):
            rows += r
            if k % 5 == 0:
                pd.concat([old, pd.DataFrame(rows)], ignore_index=True).to_csv(FE, index=False)
                print(len(rows), flush=True)
    pd.concat([old, pd.DataFrame(rows)], ignore_index=True).to_csv(FE, index=False)
    print("FINISHED")


def select():
    d = pd.read_csv(PTS)
    f = pd.read_csv(FE).rename(columns=dict(i="pid"))
    for c in [f"{b}{y}" for b in ("ln", "lr") for y in YS]:
        f[c] = f.get(c, np.nan)
    sf = series_feats(f)
    x = d.merge(pd.concat([f[["pid"]], sf], axis=1), on="pid")
    mod = (x.persist >= 2) & (((x.drop_n >= LO) & (x.drop_n < HI)) | ((x.drop_r >= LO) & (x.drop_r < HI)))
    big = (x.drop_n >= HI) & (x.drop_r >= HI)
    x["group"] = np.where(big, "big_fall", np.where(mod, "moderate", "other"))
    print(pd.crosstab(x.zone, x.group).to_string())
    pick = []
    for z, q in x.groupby("zone"):
        pick.append(q[q.group == "moderate"].sample(min(KEEP_MOD, int((q.group == "moderate").sum())), random_state=3))
        pick.append(q[q.group == "big_fall"].sample(min(KEEP_CTL, int((q.group == "big_fall").sum())), random_state=3))
        pick.append(q[q.group == "other"].sample(min(KEEP_CTL, int((q.group == "other").sum())), random_state=3))
    s = pd.concat(pick).sample(frac=1, random_state=11).reset_index(drop=True)
    s["view"] = s.index
    s.to_csv(SEL, index=False)
    x.to_csv(WORK / "sweep_all.csv", index=False)
    print("to view", len(s))


def chips(th):
    init_retry()
    with ThreadPoolExecutor(th) as ex:
        for i, _ in enumerate(ex.map(chip, pd.read_csv(SEL).itertuples())):
            if i % 25 == 0:
                print(i, flush=True)
    print("FINISHED")


def sheets(per=20, cols=5):
    from PIL import Image, ImageDraw

    from e51_chips import CH, HI as VHI, LO as VLO, SCALE
    out = OUT / "sweep_sheets"
    out.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(SEL)
    P = 81 * SCALE
    S, gap = 2 * P + 2, 14
    for k in range(0, len(t), per):
        sub = t.iloc[k:k + per]
        rows = int(np.ceil(len(sub) / cols))
        can = Image.new("RGB", (cols * (S + gap), rows * (S + gap + 12)), "white")
        dr = ImageDraw.Draw(can)
        for j, s in enumerate(sub.itertuples()):
            a = np.load(CH / f"{s.pid}.npy")
            x0, y0 = (j % cols) * (S + gap), (j // cols) * (S + gap + 12)
            dr.text((x0 + 2, y0), str(s.view), fill="black")
            for q, (dx, dy) in enumerate(((0, 0), (P + 2, 0), (0, P + 2), (P + 2, P + 2))):
                im = Image.fromarray((np.clip((a[q] - VLO) / (VHI - VLO), 0, 1) * 255).astype("uint8")).resize((P, P), Image.NEAREST)
                c = P // 2
                ImageDraw.Draw(im).rectangle([c - 7, c - 7, c + 7, c + 7], outline="yellow")
                can.paste(im, (x0 + dx, y0 + 12 + dy))
        can.save(out / f"sheet_{k // per:02d}.png")
    print("sheets", int(np.ceil(len(t) / per)))


if __name__ == "__main__":
    m = sys.argv[1]
    th = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    {"sample": sample, "select": select, "sheets": sheets}.get(m, lambda: None)() if m in ("sample", "select", "sheets") else {"feats": feats, "chips": chips}[m](th)
