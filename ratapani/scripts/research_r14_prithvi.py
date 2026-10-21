"""Round 14: Prithvi-EO-2.0-300M embeddings of pre-season HLS (Oct/Nov/Dec before each season) as per-cell features.
Step 1: encode each season's 3-frame raster in 224x224 tiles; one 1024-d token per 16x16 px (480 m) patch, averaged
over frames; each 500 m cell takes the token under its centroid; PCA-16 across all seasons (unsupervised).
Step 2: LOYO 2014-2024, large LightGBM + leaf-fall (r8 setup): base (with AlphaEarth) vs Prithvi-instead-of-AlphaEarth
vs base + Prithvi."""
import json, os, time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import torch
import lightgbm as lgb
from scipy.ndimage import maximum_filter
from sklearn.decomposition import PCA

os.environ["HF_HUB_OFFLINE"] = "1"
R = Path(r"E:\FIRE\ratapani"); M = R / "model"; OUT = M / "r14"; OUT.mkdir(exist_ok=True)
EMB = OUT / "prithvi_cell_embeddings.parquet"
MEAN = np.array([1087.0, 1342.0, 1433.0, 2734.0, 1958.0, 1363.0], np.float32)[None, :, None, None]
STD = np.array([2248.0, 2179.0, 2178.0, 1850.0, 1242.0, 1049.0], np.float32)[None, :, None, None]

if not EMB.exists():
    from terratorch.registry import BACKBONE_REGISTRY
    net = BACKBONE_REGISTRY.build("prithvi_eo_v2_300", pretrained=True, num_frames=3,
                                  bands=["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"]).eval()
    g = json.loads((R / "hls" / "grid.json").read_text())
    grid = gpd.read_file(R / "grid_500m.geojson")
    c = grid.to_crs(32643).centroid
    rows_px = ((g["y1"] - c.y) / 30).astype(int).to_numpy(); cols_px = ((c.x - g["x0"]) / 30).astype(int).to_numpy()
    out = []
    for Y in range(2014, 2025):
        t0 = time.time()
        a = np.load(R / "hls" / f"season_{Y}.npy").astype(np.float32)  # (3, 6, H, W)
        miss = a == -9999
        a[miss] = np.nan
        fill = np.nanmedian(a, axis=0, keepdims=True)  # gap-fill from the other months
        a = np.where(np.isnan(a), fill, a)
        x = np.nan_to_num((a - MEAN) / STD, nan=0.0)  # still-missing -> band mean
        T_, C_, H, W = x.shape
        Hp, Wp = int(np.ceil(H / 224)) * 224, int(np.ceil(W / 224)) * 224
        xp = np.zeros((T_, C_, Hp, Wp), np.float32); xp[:, :, :H, :W] = x
        tok = np.zeros((Hp // 16, Wp // 16, 1024), np.float32)
        tiles = [(r, q) for r in range(0, Hp, 224) for q in range(0, Wp, 224)]
        with torch.no_grad():
            for s in range(0, len(tiles), 8):
                batch = tiles[s:s + 8]
                xb = torch.from_numpy(np.stack([xp[:, :, r:r + 224, q:q + 224].transpose(1, 0, 2, 3) for r, q in batch]))
                feat = net(xb)[-1][:, 1:]  # (B, 3*196, 1024), drop CLS
                feat = feat.reshape(len(batch), 3, 14, 14, 1024).mean(1).numpy()
                for (r, q), f in zip(batch, feat):
                    tok[r // 16:r // 16 + 14, q // 16:q // 16 + 14] = f
        e = tok[rows_px // 16, cols_px // 16]
        out.append(pd.DataFrame(e).assign(season=Y, cell_id=grid.cell_id.to_numpy(),
                                          valid_frac=1 - miss[:, 0].reshape(3, -1).mean()))
        print("encoded", Y, f"{time.time() - t0:.0f}s", f"gap {miss.mean():.3f}", flush=True)
    E = pd.concat(out, ignore_index=True)
    E.columns = [str(k) for k in E.columns]
    E.to_parquet(EMB)
E = pd.read_parquet(EMB)
raw = E[[str(k) for k in range(1024)]].to_numpy()
pca = PCA(16, random_state=0).fit(raw)
print("PCA-16 explained var", pca.explained_variance_ratio_.sum().round(3))
PR = [f"pr{k:02d}" for k in range(16)]
E = pd.concat([E[["season", "cell_id"]], pd.DataFrame(pca.transform(raw), columns=PR)], axis=1)

# ---- data (as r8) ----
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
m = pd.read_csv(R / "ee" / "modis_ndvi_ndmi.csv", parse_dates=["date"]); m = m[m.date.dt.month >= 9]
peak = m.groupby([m.date.dt.year + 1, "cell_id"]).ndvi.quantile(0.9).rename("ndvi_peak"); peak.index.names = ["season", "cell_id"]
df["season"] = df.date.dt.year
df = df[df.season >= 2014]
df = df.join(peak, on=["season", "cell_id"]); df["leaf_loss"] = 1 - df.ndvi / df.ndvi_peak
df = df.sort_values(["cell_id", "date"]).reset_index(drop=True)
for k in (16, 32):
    for col in ("ndvi", "ndmi"):
        df[f"{col}_chg{k}"] = df[col] - df.groupby(["cell_id", "season"])[col].shift(k)
df = df.merge(E, on=["season", "cell_id"], how="left")
LEAF = ["ndvi_peak", "leaf_loss", "ndvi_chg16", "ndvi_chg32", "ndmi_chg16", "ndmi_chg32"]
NOAE = sum((G[g_] for g_ in ["fire", "static", "modis", "weather"]), []) + LEAF
SETS = {"base (AlphaEarth)": NOAE + G["alphaearth"], "Prithvi instead of AlphaEarth": NOAE + PR,
        "base + Prithvi": NOAE + G["alphaearth"] + PR, "no embeddings": NOAE}
year = df.season.to_numpy(); NI, NJ = df.i.max() + 1, df.j.max() + 1
neg = np.random.default_rng(0).random(len(df)) < 0.10; ypos = (df.y == 1).to_numpy()
P = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0,
         num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5)


def score(sub, s):
    flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        gg = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[gg.i, gg.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[gg.i, gg.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.cls.to_numpy() == "new")
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), recall=c[p].mean(), recall_new=c[new].mean() if new.any() else np.nan)


rows = []
for tag, cols in SETS.items():
    for yv in range(2014, 2025):
        t0 = time.time(); tr = (year != yv) & (ypos | neg); te = year == yv
        s = lgb.train(P, lgb.Dataset(df.loc[tr, cols], df.y[tr]), 600).predict(df.loc[te, cols])
        rows.append(dict(exp=tag, fold=yv, **score(df[te], s)))
        print(tag, yv, round(rows[-1]["recall"], 3), f"{time.time() - t0:.0f}s", flush=True)
Rr = pd.DataFrame(rows); Rr.to_csv(OUT / "r14_folds.csv", index=False)
S = Rr.groupby("exp").apply(lambda g_: pd.Series(dict(recall=np.average(g_.recall, weights=g_.n_pos),
        recall_new=np.average(g_.recall_new.fillna(0), weights=g_.n_new), recall_min=g_.recall.min(),
        recall_max=g_.recall.max())), include_groups=False).round(3)
S.to_csv(OUT / "r14_summary.csv"); print(S.to_string())
