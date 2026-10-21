"""Round 15: in-season Prithvi. For an issue date in month M of season Y, encode the last 3 COMPLETE months before M
(Jan: Oct-Dec, Feb: Nov-Jan, Mar: Dec-Feb, Apr: Jan-Mar, May: Feb-Apr), so Prithvi sees drying fuel and earlier burn
scars without seeing the target days. Prithvi-EO-2.0-300M, tokens averaged over frames, token under each cell centroid,
PCA-16 across all windows. LOYO 2014-2024 with the r8/r14 large LightGBM + leaf-fall setup."""
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
R = Path(r"E:\FIRE\ratapani"); M = R / "model"; OUT = M / "r15"; OUT.mkdir(exist_ok=True)
EMB = OUT / "prithvi_inseason_embeddings.parquet"
MEAN = np.array([1087.0, 1342.0, 1433.0, 2734.0, 1958.0, 1363.0], np.float32)[None, :, None, None]
STD = np.array([2248.0, 2179.0, 2178.0, 1850.0, 1242.0, 1049.0], np.float32)[None, :, None, None]

if not EMB.exists():
    from terratorch.registry import BACKBONE_REGISTRY
    net = BACKBONE_REGISTRY.build("prithvi_eo_v2_300", pretrained=True, num_frames=3,
                                  bands=["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"]).eval()
    g = json.loads((R / "hls" / "grid.json").read_text())
    grid = gpd.read_file(R / "grid_500m.geojson")
    c = grid.to_crs(32643).centroid
    rp = ((g["y1"] - c.y) / 30).astype(int).to_numpy(); cp = ((c.x - g["x0"]) / 30).astype(int).to_numpy()

    def encode(a):
        a = a.astype(np.float32); a[a == -9999] = np.nan
        a = np.where(np.isnan(a), np.nanmedian(a, axis=0, keepdims=True), a)
        x = np.nan_to_num((a - MEAN) / STD, nan=0.0)
        T_, C_, H, W = x.shape
        Hp, Wp = int(np.ceil(H / 224)) * 224, int(np.ceil(W / 224)) * 224
        xp = np.zeros((T_, C_, Hp, Wp), np.float32); xp[:, :, :H, :W] = x
        tok = np.zeros((Hp // 16, Wp // 16, 1024), np.float32)
        tiles = [(r, q) for r in range(0, Hp, 224) for q in range(0, Wp, 224)]
        with torch.no_grad():
            for s in range(0, len(tiles), 8):
                b = tiles[s:s + 8]
                xb = torch.from_numpy(np.stack([xp[:, :, r:r + 224, q:q + 224].transpose(1, 0, 2, 3) for r, q in b]))
                f = net(xb)[-1][:, 1:].reshape(len(b), 3, 14, 14, 1024).mean(1).numpy()
                for (r, q), ff in zip(b, f):
                    tok[r // 16:r // 16 + 14, q // 16:q // 16 + 14] = ff
        return tok[rp // 16, cp // 16]

    out = []
    for Y in range(2014, 2025):
        allm = np.concatenate([np.load(R / "hls" / f"season_{Y}.npy"), np.load(R / "hls" / f"inseason_{Y}.npy")])  # Oct..Apr
        for mth in range(1, 6):
            t0 = time.time()
            e = encode(allm[mth - 1:mth + 2])
            out.append(pd.DataFrame(e, columns=[str(k) for k in range(1024)]).assign(season=Y, month=mth, cell_id=grid.cell_id.to_numpy()))
            print("encoded", Y, mth, f"{time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(EMB)
E = pd.read_parquet(EMB)
raw = E[[str(k) for k in range(1024)]].to_numpy()
pca = PCA(16, random_state=0).fit(raw)
print("PCA-16 explained var", pca.explained_variance_ratio_.sum().round(3), flush=True)
IP = [f"ip{k:02d}" for k in range(16)]
E = pd.concat([E[["season", "month", "cell_id"]], pd.DataFrame(pca.transform(raw), columns=IP)], axis=1)

# pre-season Prithvi from r14 (same PCA recipe)
P14 = pd.read_parquet(M / "r14" / "prithvi_cell_embeddings.parquet")
r14raw = P14[[str(k) for k in range(1024)]].to_numpy()
PR = [f"pr{k:02d}" for k in range(16)]
P14 = pd.concat([P14[["season", "cell_id"]], pd.DataFrame(PCA(16, random_state=0).fit_transform(r14raw), columns=PR)], axis=1)

# ---- data (as r14) ----
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
m = pd.read_csv(R / "ee" / "modis_ndvi_ndmi.csv", parse_dates=["date"]); m = m[m.date.dt.month >= 9]
peak = m.groupby([m.date.dt.year + 1, "cell_id"]).ndvi.quantile(0.9).rename("ndvi_peak"); peak.index.names = ["season", "cell_id"]
df["season"] = df.date.dt.year; df["month"] = df.date.dt.month
df = df[df.season >= 2014]
df = df.join(peak, on=["season", "cell_id"]); df["leaf_loss"] = 1 - df.ndvi / df.ndvi_peak
df = df.sort_values(["cell_id", "date"]).reset_index(drop=True)
for k in (16, 32):
    for col in ("ndvi", "ndmi"):
        df[f"{col}_chg{k}"] = df[col] - df.groupby(["cell_id", "season"])[col].shift(k)
df = df.merge(E, on=["season", "month", "cell_id"], how="left").merge(P14, on=["season", "cell_id"], how="left")
assert df[IP[0]].notna().all() and df[PR[0]].notna().all()
LEAF = ["ndvi_peak", "leaf_loss", "ndvi_chg16", "ndvi_chg32", "ndmi_chg16", "ndmi_chg32"]
NOAE = sum((G[g_] for g_ in ["fire", "static", "modis", "weather"]), []) + LEAF
SETS = {"AlphaEarth (base)": NOAE + G["alphaearth"], "Prithvi pre-season (r14)": NOAE + PR,
        "Prithvi in-season": NOAE + IP, "Prithvi pre-season + in-season": NOAE + PR + IP}
year = df.season.to_numpy(); NI, NJ = df.i.max() + 1, df.j.max() + 1
neg = np.random.default_rng(0).random(len(df)) < 0.10; ypos = (df.y == 1).to_numpy()
P = dict(objective="binary", feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=0,
         num_leaves=255, min_data_in_leaf=100, learning_rate=0.03, lambda_l2=5)


def score(sub, s):
    flag = s >= np.quantile(s, 0.90); cc = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        gg = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[gg.i, gg.j] = flag[idx]
        cc[idx] = maximum_filter(r, 3)[gg.i, gg.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.cls.to_numpy() == "new")
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), recall=cc[p].mean(), recall_new=cc[new].mean() if new.any() else np.nan)


rows = []
for tag, cols in SETS.items():
    for yv in range(2014, 2025):
        t0 = time.time(); tr = (year != yv) & (ypos | neg); te = year == yv
        s = lgb.train(P, lgb.Dataset(df.loc[tr, cols], df.y[tr]), 600).predict(df.loc[te, cols])
        rows.append(dict(exp=tag, fold=yv, **score(df[te], s)))
        print(tag, yv, round(rows[-1]["recall"], 3), f"{time.time() - t0:.0f}s", flush=True)
Rr = pd.DataFrame(rows); Rr.to_csv(OUT / "r15_folds.csv", index=False)
S = Rr.groupby("exp").apply(lambda g_: pd.Series(dict(recall=np.average(g_.recall, weights=g_.n_pos),
        recall_new=np.average(g_.recall_new.fillna(0), weights=g_.n_new), recall_min=g_.recall.min(),
        recall_max=g_.recall.max())), include_groups=False).round(3)
S.to_csv(OUT / "r15_summary.csv"); print(S.to_string())
