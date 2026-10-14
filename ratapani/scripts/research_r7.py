"""Research round 7: does a spatial CNN (learns neighbourhood patterns itself) beat / complement LightGBM?
Each issue day is a 150x67 raster stack -> per-cell logit for fire on t+1..t+2.
Split: train 2013-2020, early-stop on 2021-22, test 2023-24 (same for LightGBM). Metric: 3x3-tolerant recall
when flagging the top 10% of test cell-days (pooled), plus recall on brand-new fires."""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
import torch
import torch.nn as nn
from scipy.ndimage import maximum_filter
from sklearn.metrics import average_precision_score

torch.manual_seed(0); np.random.seed(0)
M = Path(r"E:\FIRE\ratapani\model")
OUT = M / "r7"; OUT.mkdir(exist_ok=True)
df = pd.read_parquet(M / "celldays_v2.parquet")
df["cls"] = pd.read_parquet(M / "r3" / "oof_preds.parquet", columns=["cls"])["cls"].to_numpy()
G = json.loads((M / "r3" / "feature_groups.json").read_text())
NI, NJ = df.i.max() + 1, df.j.max() + 1
dates = np.sort(df.date.unique())
yr_of = pd.DatetimeIndex(dates).year

CH = ([c for c in G["fire"] if c.startswith(("cell_d", "fdist_", "aoi_", "clim_")) or c in ("dsl", "doy")]
      + G["static"] + G["modis"] + G["weather"])  # no hand-made neighbour counts: the CNN sees neighbours
print(len(CH), "channels")
di = pd.Series(np.arange(len(dates)), index=dates)
d_idx = df.date.map(di).to_numpy()
X = np.zeros((len(dates), len(CH), NI, NJ), np.float32)
Y = np.zeros((len(dates), NI, NJ), np.float32)
V = np.zeros((NI, NJ), np.float32)  # valid-cell mask
V[df.i[:3614], df.j[:3614]] = 1
trn = np.isin(yr_of, range(2013, 2021))
mu = df.loc[df.date.dt.year <= 2020, CH].mean(); sd = df.loc[df.date.dt.year <= 2020, CH].std().replace(0, 1)
Z = ((df[CH] - mu) / sd).fillna(0).to_numpy(np.float32)
for k in range(len(CH)):
    X[d_idx, k, df.i, df.j] = Z[:, k]
Y[d_idx, df.i, df.j] = df.y.to_numpy()
Xt, Yt, Vt = torch.from_numpy(X), torch.from_numpy(Y), torch.from_numpy(V)


class Net(nn.Module):
    def __init__(self, c, w=64):
        super().__init__()
        blk = lambda i, o, d: nn.Sequential(nn.Conv2d(i, o, 3, padding=d, dilation=d), nn.BatchNorm2d(o), nn.GELU())
        self.inp = nn.Sequential(nn.Conv2d(c, w, 1), nn.GELU())
        self.body = nn.Sequential(blk(w, w, 1), blk(w, w, 2), blk(w, w, 4), blk(w, w, 8), blk(w, w, 1))  # RF ~ 33 cells
        self.out = nn.Conv2d(2 * w, 1, 1)
    def forward(self, x):
        h = self.inp(x)
        return self.out(torch.cat([h, self.body(h)], 1)).squeeze(1)


net = Net(len(CH))
opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
lossf = nn.BCEWithLogitsLoss(reduction="none", pos_weight=torch.tensor(20.0))
tr_idx = np.where(trn)[0]; va_idx = np.where(np.isin(yr_of, [2021, 2022]))[0]; te_idx = np.where(yr_of >= 2023)[0]


def predict(idx):
    net.eval(); out = []
    with torch.no_grad():
        for s in range(0, len(idx), 64):
            out.append(torch.sigmoid(net(Xt[idx[s:s + 64]])))
    return torch.cat(out).numpy()


def ap(idx, p):
    m = V.astype(bool)
    return average_precision_score(Y[idx][:, m].ravel(), p[:, m].ravel())


best, best_state, patience = -1, None, 0
for ep in range(40):
    net.train(); t0 = time.time(); perm = np.random.permutation(tr_idx)
    for s in range(0, len(perm), 16):
        b = perm[s:s + 16]
        x = Xt[b]
        if np.random.rand() < 0.5: x, yb = x.flip(-1), Yt[b].flip(-1); vb = Vt.flip(-1)
        else: yb, vb = Yt[b], Vt
        l = (lossf(net(x), yb) * vb).sum() / vb.sum() / len(b)
        opt.zero_grad(); l.backward(); opt.step()
    a = ap(va_idx, predict(va_idx))
    print(f"epoch {ep} val AP {a:.4f} {time.time() - t0:.0f}s", flush=True)
    if a > best: best, best_state, patience = a, {k: v.clone() for k, v in net.state_dict().items()}, 0
    else:
        patience += 1
        if patience >= 6: break
net.load_state_dict(best_state)
torch.save(best_state, OUT / "cnn.pt")

# ---- test scores back to rows ----
te = df.date.dt.year.to_numpy() >= 2023
sub = df[te].reset_index(drop=True)
P_te = predict(te_idx)
pos_in = pd.Series(np.arange(len(te_idx)), index=te_idx)
s_cnn = P_te[pos_in[sub.date.map(di)].to_numpy(), sub.i, sub.j]

# LightGBM, same split (train <=2020 + early-stop rounds on 2021-22, then refit on <=2022 like train_v2)
COLS = sum((G[g] for g in ["fire", "static", "modis", "alphaearth", "weather"]), [])
yr = df.date.dt.year.to_numpy(); rng = np.random.default_rng(0); neg = rng.random(len(df)) < 0.10
Pg = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200, feature_fraction=0.7,
          bagging_fraction=0.8, bagging_freq=1, lambda_l2=5, verbose=-1, seed=0)
trm = (yr <= 2020) & ((df.y == 1).to_numpy() | neg)
b = lgb.train(Pg | {"metric": "average_precision"}, lgb.Dataset(df.loc[trm, COLS], df.y[trm]), 1000,
              valid_sets=[lgb.Dataset(df.loc[(yr >= 2021) & (yr <= 2022), COLS], df.y[(yr >= 2021) & (yr <= 2022)])],
              callbacks=[lgb.early_stopping(100, verbose=False)])
s_lgb = b.predict(sub[COLS])


def tol(s):
    flag = s >= np.quantile(s, 0.90)
    c = np.zeros(len(sub), bool)
    for _, idx in sub.groupby("date").indices.items():
        g = sub.iloc[idx]; r = np.zeros((NI, NJ), bool); r[g.i, g.j] = flag[idx]
        c[idx] = maximum_filter(r, 3)[g.i, g.j]
    p = sub.y.to_numpy() == 1; new = p & (sub.cls.to_numpy() == "new")
    return dict(pr_auc=round(average_precision_score(sub.y, s), 4), recall=round(c[p].mean(), 3),
                recall_new=round(c[new].mean(), 3), precision_strict=round(p[flag].mean(), 4))


rk = lambda s: pd.Series(s).rank(pct=True).to_numpy()
res = {"cnn": tol(s_cnn), "lightgbm": tol(s_lgb), "ensemble_rank_mean": tol(rk(s_cnn) + rk(s_lgb)),
       "cnn_best_val_ap": round(best, 4), "lgb_best_iter": b.best_iteration}
(OUT / "r7_results.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
