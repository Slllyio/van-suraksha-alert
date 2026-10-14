"""Research round 10: CNN under LOYO (12 folds, fixed 4 epochs = r7's best) and rank-ensemble with the best
LightGBM OOF predictions from r8 (large 255x600 + leaf-fall). Channel standardisation uses all years (unsupervised,
negligible leakage)."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy.ndimage import maximum_filter

torch.manual_seed(0); np.random.seed(0)
M = Path(r"E:\FIRE\ratapani\model"); OUT = M / "r10"; OUT.mkdir(exist_ok=True)
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
lgb_oof = pd.read_parquet(M / "r8" / "oof_best.parquet")[["date", "cell_id", "q_best"]]
df = df.merge(lgb_oof, on=["date", "cell_id"], how="left")
assert df.q_best.notna().all()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
NI, NJ = df.i.max() + 1, df.j.max() + 1
CH = ([c for c in G["fire"] if c.startswith(("cell_d", "fdist_", "aoi_", "clim_")) or c in ("dsl", "doy")]
      + G["static"] + G["modis"] + G["weather"])
dates = np.sort(df.date.unique()); yr_of = pd.DatetimeIndex(dates).year
di = pd.Series(np.arange(len(dates)), index=dates); d_idx = df.date.map(di).to_numpy()
Z = ((df[CH] - df[CH].mean()) / df[CH].std().replace(0, 1)).fillna(0).to_numpy(np.float32)
X = np.zeros((len(dates), len(CH), NI, NJ), np.float32); Y = np.zeros((len(dates), NI, NJ), np.float32)
for k in range(len(CH)):
    X[d_idx, k, df.i, df.j] = Z[:, k]
Y[d_idx, df.i, df.j] = df.y.to_numpy()
V = np.zeros((NI, NJ), np.float32); V[df.i, df.j] = 1
Xt, Yt, Vt = torch.from_numpy(X), torch.from_numpy(Y), torch.from_numpy(V)


class Net(nn.Module):
    def __init__(self, c, w=64):
        super().__init__()
        blk = lambda i, o, d: nn.Sequential(nn.Conv2d(i, o, 3, padding=d, dilation=d), nn.BatchNorm2d(o), nn.GELU())
        self.inp = nn.Sequential(nn.Conv2d(c, w, 1), nn.GELU())
        self.body = nn.Sequential(blk(w, w, 1), blk(w, w, 2), blk(w, w, 4), blk(w, w, 8), blk(w, w, 1))
        self.out = nn.Conv2d(2 * w, 1, 1)
    def forward(self, x):
        h = self.inp(x)
        return self.out(torch.cat([h, self.body(h)], 1)).squeeze(1)


lossf = nn.BCEWithLogitsLoss(reduction="none", pos_weight=torch.tensor(20.0))
cnn_oof = np.zeros((len(dates), NI, NJ), np.float32)
for yv in range(2013, 2025):
    t0 = time.time(); torch.manual_seed(yv)
    net = Net(len(CH)); opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
    tr = np.where(yr_of != yv)[0]; te = np.where(yr_of == yv)[0]
    for ep in range(4):
        net.train()
        for s in np.array_split(np.random.permutation(tr), max(1, len(tr) // 16)):
            x, yb, vb = Xt[s], Yt[s], Vt
            if np.random.rand() < 0.5: x, yb, vb = x.flip(-1), yb.flip(-1), vb.flip(-1)
            l = (lossf(net(x), yb) * vb).sum() / vb.sum() / len(s)
            opt.zero_grad(); l.backward(); opt.step()
    net.eval()
    with torch.no_grad():
        cnn_oof[te] = torch.cat([torch.sigmoid(net(Xt[te[i:i + 64]])) for i in range(0, len(te), 64)]).numpy()
    print("cnn fold", yv, f"{time.time() - t0:.0f}s", flush=True)
df["s_cnn"] = cnn_oof[d_idx, df.i, df.j]
df[["date", "cell_id", "s_cnn"]].to_parquet(OUT / "cnn_oof.parquet")


def score(sub, s):
    flag = s >= np.quantile(s, 0.90); c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.cls.to_numpy() == "new")
    return dict(n_pos=int(p.sum()), n_new=int(new.sum()), recall=c[p].mean(), recall_new=c[new].mean() if new.any() else np.nan)


rows = []
year = df.date.dt.year.to_numpy()
for yv in range(2013, 2025):
    sub = df[year == yv].reset_index(drop=True)
    rl, rc = sub.q_best.rank(pct=True).to_numpy(), sub.s_cnn.rank(pct=True).to_numpy()
    for tag, s in [("lgbm_large+leaf", rl), ("cnn", rc), ("ensemble 50/50", rl + rc), ("ensemble 70 lgbm/30 cnn", 0.7 * rl + 0.3 * rc)]:
        rows.append(dict(exp=tag, fold=yv, **score(sub, s)))
R = pd.DataFrame(rows); R.to_csv(OUT / "r10_folds.csv", index=False)
S = R.groupby("exp").apply(lambda g: pd.Series(dict(recall=np.average(g.recall, weights=g.n_pos),
        recall_new=np.average(g.recall_new.fillna(0), weights=g.n_new), recall_min=g.recall.min(),
        recall_max=g.recall.max())), include_groups=False).round(3)
S.to_csv(OUT / "r10_summary.csv"); print(S.to_string())
