"""State map from the local model scores. Writes the rasters plus work/classified.npz in the layout 06_stats_maps.py reads.
Classes: 1 clearing, 2 partial canopy loss, 3 small low-confidence patch (0.5-2.25 ha; reported apart from the totals).
Recovery: 1 recovered, 2 persistent, 3 unknown (fewer than 3 years of follow-up). Usage: e8_classify.py <version> | --selftest"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage

import anomalies
from common import *

EIGHT = np.ones((3, 3), bool)
FIRST, LAST = 2018, 2025
YEARS8 = list(range(FIRST, LAST + 1))


def patches(mask, yod, min_px):
    """Pixels of `mask` in patches of at least min_px; a patch may span adjacent years, as one felling often does."""
    keep = np.zeros(yod.shape, bool)
    for y in YEARS8:
        m = mask & ((yod == y) | (yod == y + 1))
        if not m.any():
            continue
        lab, n = ndimage.label(m, structure=EIGHT)
        size = np.bincount(lab.ravel(), minlength=n + 1)
        size[0] = 0
        keep |= size[lab] >= min_px
    return keep


def decide(score, yod, pre_tree, post_tree, rec_tree, zone, th):
    """Inputs are state or tile arrays: score = top model score x1000, yod its year, tree values x10000."""
    valid = (zone > 0) & (yod > 0)
    pre, post, rec_t = (a.astype("int32") for a in (pre_tree, post_tree, rec_tree))
    drop = pre - post
    core = patches(valid & (score >= th["core_z"] * 1000) & (drop >= th["core_tree_drop"] * 1e4), yod, th["core_min_px"])
    grow = valid & (score >= th["grow_z"] * 1000) & (drop >= th["grow_tree_drop"] * 1e4)
    main = ndimage.binary_dilation(core, structure=EIGHT, iterations=th["grow_px"], mask=grow)
    small = patches(valid & (score >= th["small_z"] * 1000) & (drop >= th["small_tree_drop"] * 1e4) & ~main, yod, th["small_min_px"])
    clear = main & (post <= th["clear_post_tree"] * 1e4) & (drop >= th["clear_tree_drop"] * 1e4)
    cls = np.zeros(yod.shape, "uint8")
    cls[main] = 2
    cls[clear] = 1
    cls[small] = 3
    out_yod = np.where(cls > 0, yod, 0).astype("int16")
    recovered = (rec_t - post) >= th["rec_fraction"] * np.maximum(drop, 1)
    enough = (yod + 3) <= LAST
    rec = np.where(cls > 0, np.where(enough, np.where(recovered, 1, 2), 3), 0).astype("uint8")
    return out_yod, cls, rec


def tree_at(trees, yod, offsets):
    """Mean tree value at yod + each offset, clamped to the available years."""
    y0 = FIRST - 1
    idx = np.stack([np.clip(yod + o - y0, 0, trees.shape[0] - 1) for o in offsets])
    r, c = np.indices(yod.shape)
    return np.mean([trees[i, r, c] for i in idx], axis=0).astype("int16")


def load_state(version):
    """Top score, its year and pre/post/recovery tree cover per pixel, tile by tile to keep memory down."""
    g = json.load(open(WORK / "grid.json"))
    H, W = g["height"], g["width"]
    A = {k: np.zeros((H, W), "int16") for k in ("score", "yod", "pre", "post", "rec")}
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    missing = []
    off, off_names = anomalies.load(version)
    for s in t.itertuples():
        f = WORK / f"emb_{version}" / f"{s.tile}.tif"
        if not f.exists():
            missing.append(s.tile)
            continue
        with rasterio.open(f) as src:
            names = list(src.descriptions)
            arr = src.read()
        assert names == off_names
        arr = arr - anomalies.tile_offset(off, s)        # remove the regional drought or wet-year shift
        zi = [i for i, n in enumerate(names) if n.startswith("z")]
        ti = [i for i, n in enumerate(names) if n.startswith("tree")]
        z, tr = arr[zi], arr[ti]
        yod = np.array(YEARS8)[z.argmax(0)]
        A["score"][s.row:s.row + s.h, s.col:s.col + s.w] = z.max(0)
        A["yod"][s.row:s.row + s.h, s.col:s.col + s.w] = yod
        A["pre"][s.row:s.row + s.h, s.col:s.col + s.w] = tree_at(tr, yod, (-2, -1))
        A["post"][s.row:s.row + s.h, s.col:s.col + s.w] = tree_at(tr, yod, (1, 2))
        A["rec"][s.row:s.row + s.h, s.col:s.col + s.w] = tree_at(tr, yod, (3,))
    return g, A, missing


def selftest():
    th = dict(core_z=1, grow_z=0, small_z=2, core_min_px=25, small_min_px=6, grow_px=2, clear_post_tree=.25, clear_tree_drop=.2, rec_fraction=.5,
              core_tree_drop=.1, grow_tree_drop=.05, small_tree_drop=.1)
    sh = (40, 40)
    zone, score, yod = np.ones(sh, "uint16"), np.zeros(sh, "int16"), np.zeros(sh, "int16")
    pre, post, rec = np.full(sh, 7000, "int16"), np.full(sh, 7000, "int16"), np.full(sh, 7000, "int16")
    score[2:8, 2:8], yod[2:8, 2:8], post[2:8, 2:8], rec[2:8, 2:8] = 3000, 2020, 1000, 1000   # 6x6 clearing, stays low
    score[20:23, 2:5], yod[20:23, 2:5], post[20:23, 2:5] = 3000, 2021, 3000                  # 3x3 strong, small
    score[30, 30], yod[30, 30] = 5000, 2020                                                  # lone pixel
    score[12:18, 20:26], yod[12:18, 20:26], post[12:18, 20:26] = 1500, 2024, 5500            # 6x6 partial, recent
    score[30:36, 2:8], yod[30:36, 2:8], post[30:36, 2:8] = 3000, 2020, 6900                  # strong score but trees unchanged
    y, c, r = decide(score, yod, pre, post, rec, zone, th)
    assert (c[2:8, 2:8] == 1).all() and (r[2:8, 2:8] == 2).all(), "clearing + persistent"
    assert (c[20:23, 2:5] == 3).all() and c[30, 30] == 0, "small class; lone pixel dropped"
    assert (c[12:18, 20:26] == 2).all() and (r[12:18, 20:26] == 3).all(), "partial + too recent"
    assert (c[30:36, 2:8] == 0).all(), "no tree-cover fall means no loss, whatever the score"
    t = np.arange(9)[:, None, None] * np.ones((9, 1, 1), "int16")
    assert tree_at(t, np.array([[2020]]), (-2, -1))[0, 0] == 1 and tree_at(t, np.array([[2025]]), (3,))[0, 0] == 8
    print("selftest ok")


def main(version):
    from importlib import import_module
    from rasterio.transform import from_origin
    th = json.load(open(ROOT / "scripts" / "thresholds_emb.json"))
    g, A, missing = load_state(version)
    if missing:
        print("WARNING tiles missing:", len(missing), missing[:6])
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zone = s.read(1)
    water = np.load(WORK / "water.npy")
    yod, cls, rec = decide(A["score"], A["yod"], A["pre"], A["post"], A["rec"], np.where(water, 0, zone), th)
    r = OUT / "rasters"
    r.mkdir(parents=True, exist_ok=True)
    wc = import_module("05_classify").write_cog
    wc(r / "mp_loss_year.tif", yod, g)
    wc(r / "mp_loss_class.tif", cls, g)
    wc(r / "mp_loss_recovery.tif", rec, g)
    wc(r / "mp_loss_score_x1000.tif", np.where(cls > 0, A["score"], 0).astype("int16"), g)
    aux = WORK / "aux_state.npz"
    hansen_any = burned = np.zeros(yod.shape, bool)
    if aux.exists():
        x = np.load(aux)
        hansen_any = (x["hansen_year"] >= FIRST - 2000) & (x["hansen_year"] <= LAST - 2000) & (yod > 0)
        i = np.clip(yod - FIRST, 0, len(YEARS8) - 1)
        rr, cc = np.nonzero(yod)
        burned = np.zeros(yod.shape, bool)
        burned[rr, cc] = x["burned"][i[rr, cc], rr, cc] > 0
    np.savez_compressed(WORK / "classified.npz", yod=yod, cls=cls, rec=rec, burned=burned, hansen=hansen_any)
    np.savez_compressed(WORK / "score_state.npz", score=A["score"], drop=(A["pre"].astype("int32") - A["post"]).clip(-32000, 32000).astype("int16"))
    print("main ha", round(((cls == 1) | (cls == 2)).sum() * PX_HA), "small ha", round((cls == 3).sum() * PX_HA))
    print({y: round((((cls == 1) | (cls == 2)) & (yod == y)).sum() * PX_HA) for y in YEARS8})


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main(sys.argv[1])
