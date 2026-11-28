"""Frozen Prithvi-EO-2.0-300M on HLS scenes already on disk (read-only, data_lake/satellite_imagery/hls_s30): 224 px around each Guna-area labelled point, spring 2018 or 2019 against spring 2024.
No Earth Engine, CPU only. Saves the mean of the 3 x 3 tokens around the point and over the chip. Usage: e67_prithvi.py scan | embed | test"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

from common import *
from e48_tests import GT

ROOT_HLS = Path("E:/FIRE/data_lake/satellite_imagery/hls_s30")
WEIGHTS = next(Path.home().glob(".cache/huggingface/hub/models--ibm-nasa-geospatial--Prithvi-EO-2.0-300M/snapshots/*/Prithvi_EO_V2_300M.pt"))
TT = "E:/FIRE/refs/terratorch/terratorch/models/backbones"
BANDS = ["B02", "B03", "B04", "B8A", "B11", "B12"]
MEAN = np.array([1087.0, 1342.0, 1433.0, 2734.0, 1958.0, 1363.0])
STD = np.array([2248.0, 2179.0, 2178.0, 1850.0, 1242.0, 1049.0])
SCENES = WORK / "prithvi_scenes.csv"
OUTF = WORK / "prithvi_points.npz"
SIZE = 224


def scan():
    rows = []
    for f in ROOT_HLS.rglob("*.B04.tif"):
        with rasterio.open(f) as s:
            b = s.bounds
            rows.append(dict(path=str(f), year=int(f.name.split(".")[3][:4]), doy=int(f.name.split(".")[3][4:7]), crs=str(s.crs), left=b.left, bottom=b.bottom, right=b.right, top=b.top))
    d = pd.DataFrame(rows)
    d.to_csv(SCENES, index=False)
    print(d.groupby(["year"]).size().to_dict(), d.crs.unique(), len(d))


def read_chip(row, x, y):
    with rasterio.open(row.path) as s:
        c, r = ~s.transform * (x, y)
    w = Window(int(c) - SIZE // 2, int(r) - SIZE // 2, SIZE, SIZE)
    out = []
    for b in BANDS:
        with rasterio.open(row.path.replace(".B04.tif", f".{b}.tif")) as s:
            if w.col_off < 0 or w.row_off < 0 or w.col_off + SIZE > s.width or w.row_off + SIZE > s.height:
                return None
            out.append(s.read(1, window=w).astype("float32"))
    return np.stack(out)


def good(a):
    return a is not None and (a[2] > -9000).mean() > .9 and np.median(a[2][a[2] > -9000]) < 2500        # mostly valid and not cloud-bright


def model():
    import importlib.util

    import torch
    sys.path.insert(0, TT)
    spec = importlib.util.spec_from_file_location("prithvi_mae", TT + "/prithvi_mae.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = mod.PrithviMAE(img_size=224, patch_size=(1, 16, 16), num_frames=1, in_chans=6, embed_dim=1024, depth=24, num_heads=16, decoder_embed_dim=512, decoder_depth=8, decoder_num_heads=16, mlp_ratio=4.0, coords_encoding=[], coords_scale_learn=False)
    sd = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
    sd = {k: v for k, v in sd.items() if not k.endswith("pos_embed") and "temporal_embed" not in k and "location_embed" not in k}
    print(m.load_state_dict(sd, strict=False)[1][:3])
    return m.eval()


def embed_one(m, a):
    import torch
    x = (np.nan_to_num(a) - MEAN[:, None, None]) / STD[:, None, None]
    with torch.no_grad():
        t = m.encoder.forward_features(torch.tensor(x[None, :, None], dtype=torch.float32))[-1][0, 1:]
    g = t.reshape(14, 14, -1)
    return g[6:8 + 1, 6:8 + 1].mean((0, 1)).numpy(), t.mean(0).numpy()


def points():
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    return g[["pid", "x", "y", "source"]]


def embed(limit=None):
    import torch
    torch.set_num_threads(8)
    S = pd.read_csv(SCENES)
    m = model()
    P = points()
    done = {}
    if OUTF.exists():
        z = np.load(OUTF)
        done = {int(i): (a, b) for i, a, b in zip(z["pid"], z["pre"], z["post"])}
    trs = {}
    t0 = time.time()
    n = 0
    for q in P.itertuples():
        if q.pid in done:
            continue
        vec = {}
        for label, years in (("pre", (2018, 2019)), ("post", (2024,))):
            for r in S[S.year.isin(years)].sort_values(["year", "doy"]).itertuples():
                tr = trs.setdefault(r.crs, Transformer.from_crs(PROJ4, r.crs, always_xy=True))
                x, y = tr.transform(q.x, q.y)
                if not (r.left + 3400 < x < r.right - 3400 and r.bottom + 3400 < y < r.top - 3400):
                    continue
                a = read_chip(r, x, y)
                if good(a):
                    vec[label] = embed_one(m, a)[0]
                    break
        if len(vec) == 2:
            done[q.pid] = (vec["pre"], vec["post"])
        n += 1
        if n % 25 == 0:
            ids = list(done)
            np.savez_compressed(OUTF, pid=np.array(ids), pre=np.stack([done[i][0] for i in ids]), post=np.stack([done[i][1] for i in ids]))
            print(n, "of", len(P), "with both", len(done), int(time.time() - t0), "s", flush=True)
        if limit and n >= limit:
            break
    ids = list(done)
    np.savez_compressed(OUTF, pid=np.array(ids), pre=np.stack([done[i][0] for i in ids]), post=np.stack([done[i][1] for i in ids]))
    print("FINISHED", len(done), "of", len(P), int(time.time() - t0), "s")


if __name__ == "__main__":
    {"scan": scan, "embed": embed, "test": lambda: embed(25)}[sys.argv[1]]()
