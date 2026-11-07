"""Shared data for the survey-calibrated state models (owner's experiment, 7 Nov), all on the 30 m Guna grid (= zone grid window = HLS tile grid).
Labels from the 2015 Forest Dept stock survey: 1 forest (UNDER STOCK, PLANTATION), 2 open (BLANK), 3 farm (CULTIVATION, ENCROACHMENT, PATTA); TANK/RIVER/other dropped;
interior only (compartment eroded 30 m); compartments with a clearly mixed 2015 signal dropped (fixed rule: rabi NDVI IQR > 0.25 inside the compartment).
Also: HLS stack mosaics per year (18 bands = 3 seasons x 6), AlphaEarth embeddings per year for Guna forest pixels, range and beat rasters. Usage: e106_survey_data.py build"""
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine

from common import *
from e97_guna_eval import GD, SH, grid, survey_type
from e105_hls_guna import HD as HLS, T

SM = WORK / "survey_model"
CLS = {"UNDER STOCK": 1, "PLANTATION": 1, "BLANK": 2, "CULTIVATION": 3, "ENCROACHMENT": 3, "PATTA": 3}
NAMES = {1: "forest", 2: "open", 3: "farm"}
IQR_MAX = .25


def grid30():
    tr, shp = grid()
    return Affine(30, 0, tr.c, 0, -30, tr.f), (shp[0] // 3, shp[1] // 3)


def zone30():
    """Zone (beat) ids at 30 m: the 10 m Guna beat array is the zone grid repeated 3 x 3."""
    return np.load(GD / "guna_beat.npy", mmap_mode="r")[::3, ::3].copy()


def hls(year):
    tr, (H, W) = grid30()
    out = np.full((18, H, W), -9999, "int16")
    for f in (HLS / str(year)).glob("*.npy"):
        if f.name.endswith(".tmp.npy"):
            continue
        r, c = map(int, f.stem.split("_"))
        a = np.load(f)
        h, w = min(T, H - r), min(T, W - c)
        out[:, r:r + h, c:c + w] = a[:, :h, :w]
    return out


def ndvi(a, k):
    """NDVI of season k from an 18-band stack (B4 = index 2, B5 = index 3 within each season)."""
    red, nir = a[6 * k + 2].astype("float32"), a[6 * k + 3].astype("float32")
    v = (nir - red) / np.maximum(nir + red, 1)
    v[(a[6 * k + 2] == -9999) | (a[6 * k + 3] == -9999)] = np.nan
    return v


def emb(year, zone):
    """AlphaEarth 64-d embeddings (int8 x 127) on the Guna 30 m grid for Guna forest pixels: returns (rows, cols, vals)."""
    t = pd.read_csv(WORK / "tiles.csv", keep_default_na=False)
    with rasterio.open(WORK / "zone_beat.tif") as s:
        zb = s.read(1)
    b = pd.read_csv(OUT / "beat_lookup.csv")
    gids = set(b[b.Division == "Guna"].zone_id)
    # Guna 30 m window origin in the zone grid
    tr, shp = grid()
    g = __import__("json").load(open(WORK / "grid.json"))
    r0, c0 = int(round((g["y1"] - tr.f) / RES)), int(round((tr.c - g["x0"]) / RES))
    H, W = zone.shape
    R, C, V = [], [], []
    for s_ in t.itertuples():
        rr0, cc0 = int(s_.row), int(s_.col)
        if rr0 + s_.h <= r0 or rr0 >= r0 + H or cc0 + s_.w <= c0 or cc0 >= c0 + W:
            continue
        f = WORK / "embeddings" / f"{s_.tile}_{year}.npz"
        if not f.exists():
            continue
        z = zb[rr0:rr0 + int(s_.h), cc0:cc0 + int(s_.w)]
        mask = z > 0
        idx = np.cumsum(mask.ravel()).reshape(mask.shape) - 1
        rr, cc = np.nonzero(mask & np.isin(z, list(gids)))
        gr, gc = rr + rr0 - r0, cc + cc0 - c0
        ok = (gr >= 0) & (gr < H) & (gc >= 0) & (gc < W)
        vals = np.load(f)["vals"]
        R.append(gr[ok]), C.append(gc[ok]), V.append(vals[idx[rr[ok], cc[ok]]])
    return np.concatenate(R), np.concatenate(C), np.concatenate(V)


def build():
    SM.mkdir(parents=True, exist_ok=True)
    tr, (H, W) = grid30()
    zone = zone30()
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    ranges = sorted(lk[lk.Division == "Guna"].Range.unique())
    rng = np.zeros((H, W), "uint8")
    for i, r in enumerate(ranges, 1):
        rng[np.isin(zone, lk[(lk.Division == "Guna") & (lk.Range == r)].index.values)] = i
    sv = gpd.read_file(SH / "forest-stock-2015" / "guna_stock_2015.gpkg").to_crs(PROJ4).reset_index(drop=True)
    sv["T"] = sv.Type.map(survey_type)
    sv["cls"] = sv["T"].map(CLS).fillna(0).astype(int)
    sv["cid"] = np.arange(1, len(sv) + 1)
    inner = sv.geometry.buffer(-30)
    lab = rasterize([(g, c) for g, c in zip(inner, sv.cls) if c > 0 and g is not None and not g.is_empty], out_shape=(H, W), transform=tr, fill=0, dtype="uint8")
    cid = rasterize([(g, i) for g, i, c in zip(inner, sv.cid, sv.cls) if c > 0 and g is not None and not g.is_empty], out_shape=(H, W), transform=tr, fill=0, dtype="int32")
    a15 = hls(2015)
    rabi = ndvi(a15, 0)
    df = pd.DataFrame(dict(cid=cid[cid > 0], v=rabi[cid > 0]))
    iqr = df.groupby("cid").v.quantile(.75) - df.groupby("cid").v.quantile(.25)
    mixed = set(iqr[iqr > IQR_MAX].index)
    keep = (cid > 0) & ~np.isin(cid, list(mixed)) & (zone > 0)
    lab = np.where(keep, lab, 0).astype("uint8")
    np.savez_compressed(SM / "labels30.npz", lab=lab, cid=cid, rng=rng, zone=zone)
    pd.Series(ranges, index=range(1, len(ranges) + 1)).to_csv(SM / "ranges.csv")
    st = pd.DataFrame(dict(cls=lab[lab > 0], rng=rng[lab > 0])).groupby(["rng", "cls"]).size().unstack(fill_value=0)
    st.index = [ranges[i - 1] for i in st.index]
    st.columns = [NAMES[c] for c in st.columns]
    print("compartments", len(sv), "labelled", int((sv.cls > 0).sum()), "mixed dropped", len(mixed), "| HLS 2015 coverage", round(float((a15[0] != -9999).mean()), 3))
    print(sv.groupby("T").size().to_string())
    print("interior labelled pixels by range and class\n", st.to_string())


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
