"""Fire regimes of MP beat cells from the 2017-25 scars, and whether they help.
1. Per cell: how often it burns, how much of it burns, when in the season (days since 15 Feb), how big the fires reaching it
   are, longest run of burning years. Gaussian mixture on these (k by BIC) = regimes 2017-25 (regimes/cell_regime.csv).
2. Held-forward test, seasons 2020-25: LightGBM trained on earlier seasons only, label = any S-NPP point in the cell
   (15 Feb-15 Jun, not from scars). Base = years burned (scars, VIIRS since 2014), seasons since last burn, forest share;
   + regime = the same plus share, timing, fire size, run length. Top-10% capture and AUC (regimes/test.csv).
3. Timing: does a cell's usual burn date say when it burns next season (Spearman, vs division median)."""
import glob, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr
from pyproj import Transformer
R = "/mnt/project-files/fire-alert-scars/mp/regimes/"
BH = "/mnt/project-files/fire-alert-scars/mp/burn_history/"
X0, Y1, NC, S = 399000.0, 2996000.0, 1829, 500.0
C = pd.read_parquet("/mnt/project-files/ratapani/mp_grid/mp_cells.parquet")[["cell", "beat_uid"]]
D = pd.read_parquet(BH + "cell_year.parquet").merge(pd.read_parquet(R + "cell_year_timing.parquet"), on=["cell", "year"], how="left")
C["forest"] = C.cell.map(D.groupby("cell").forest.first())
C["division"] = C.beat_uid.str[:3]
H = D[D.burned_forest >= 0.10].copy()
H["logha"] = np.log10(H.max_fire_ha.fillna(0) + 1)
H["big"] = H.max_fire_ha >= 200


def streak(ys):
    best = cur = 0; prev = None
    for y in sorted(ys):
        cur = cur + 1 if prev is not None and y == prev + 1 else 1; best = max(best, cur); prev = y
    return best


def feats(years):
    h = H[H.year.isin(years)]
    g = h.groupby("cell")
    F = pd.DataFrame(dict(n=g.size(), share=g.burned_forest.mean(), day_med=g.first_day.median(), day_sd=g.first_day.std().fillna(0),
                          size_med=g.logha.median(), big_frac=g.big.mean(), streak=g.year.apply(streak), last=g.year.max()))
    return F.reindex(C.cell)


# 1. regimes 2017-25
F = feats(range(2017, 2026))
cols = ["n", "share", "day_med", "day_sd", "size_med", "big_frac", "streak"]
Z = F.dropna(subset=["n"])
X = StandardScaler().fit_transform(Z[cols])
rng = np.random.default_rng(0); sam = rng.choice(len(X), min(60000, len(X)), replace=False)
bic = {k: GaussianMixture(k, covariance_type="full", random_state=0, n_init=2).fit(X[sam]).bic(X[sam]) for k in range(3, 11)}
print("BIC", {k: round(v) for k, v in bic.items()})
K = min(bic, key=bic.get)
gm = GaussianMixture(K, covariance_type="full", random_state=0, n_init=3).fit(X[sam])
Z = Z.assign(regime=gm.predict(X), regime_p=gm.predict_proba(X).max(1).round(3))
prof = Z.groupby("regime")[cols].mean().round(2).assign(cells=Z.regime.value_counts().sort_index())
prof["day_med_date"] = [(pd.Timestamp(2025, 2, 14) + pd.Timedelta(days=float(d))).strftime("%d %b") for d in prof.day_med]
print(prof.to_string()); prof.to_csv(R + "regime_profiles.csv")
out = C.join(Z[cols + ["regime", "regime_p"]], on="cell")
out["regime"] = out.regime.fillna(-1).astype(int)   # -1 = not burned 2017-25
out.to_csv(R + "cell_regime.csv", index=False)
dv = pd.crosstab(out.division, out.regime, normalize="index").round(3); dv.to_csv(R + "regime_by_division.csv")

# labels: S-NPP points per cell per season
T = Transformer.from_crs(4326, 32643, always_xy=True); V = {}
for f in sorted(glob.glob("/mnt/project-files/fire-alert-scars/alerts_mp/viirs-snpp_*.csv")):
    y = int(f[-8:-4])
    if y > 2025: continue
    a = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date"]); md = a.acq_date.str[5:]
    a = a[(md >= "02-15") & (md <= "06-15")]
    x, yy = T.transform(a.longitude.values, a.latitude.values)
    V[y] = set((((Y1 - yy) // S).astype(int) * NC + ((x - X0) // S).astype(int)).tolist())
cellv = C.cell.values

# 2. held-forward test
rows = []
for Y in range(2018, 2026):
    f = feats(range(2017, Y))
    d = pd.DataFrame(dict(year=Y, cell=cellv, forest=C.forest.values,
                          viirs_years=sum(np.isin(cellv, list(V[y])) for y in range(2014, Y)),
                          y=np.isin(cellv, list(V[Y])).astype(int)))
    for c in cols: d[c] = f[c].values
    d["n"] = d.n.fillna(0); d["since_last"] = (Y - f["last"].values); d["since_last"] = d.since_last.fillna(99)
    rows.append(d)
A = pd.concat(rows, ignore_index=True)
base = ["n", "viirs_years", "since_last", "forest"]; full = base + [c for c in cols if c != "n"]
res = []
for Y in range(2020, 2026):
    tr, te = A[A.year < Y], A[A.year == Y]
    r = dict(year=Y, base_rate=round(te.y.mean(), 4))
    for nm, fs in (("base", base), ("regime", full)):
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=200, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.8, verbose=-1).fit(tr[fs], tr.y)
        p = m.predict_proba(te[fs])[:, 1]
        r["auc_" + nm] = round(roc_auc_score(te.y, p), 4)
        top = np.argsort(-p)[:int(0.1 * len(p))]; r["top10_" + nm] = round(te.y.values[top].sum() / te.y.sum(), 4)
    res.append(r); print(r, flush=True)
Rt = pd.DataFrame(res); Rt.to_csv(R + "test.csv", index=False); print(Rt.mean(numeric_only=True).round(4).to_string())

# 3. timing: usual burn date vs next season's burn date
tt = []
for Y in range(2019, 2026):
    f = feats(range(2017, Y))
    h = H[H.year == Y].set_index("cell")
    j = h.join(f[["day_med", "n"]], rsuffix="_p").dropna(subset=["day_med"])
    j["division"] = C.set_index("cell").division.reindex(j.index).values
    dmed = j.groupby("division").day_med.transform("median")
    tt.append(dict(year=Y, cells=len(j), rho_cell=round(spearmanr(j.day_med, j.first_day)[0], 3),
                   rho_division=round(spearmanr(dmed, j.first_day)[0], 3),
                   mae_cell=round((j.day_med - j.first_day).abs().median(), 1), mae_division=round((dmed - j.first_day).abs().median(), 1)))
Tt = pd.DataFrame(tt); Tt.to_csv(R + "timing_test.csv", index=False); print(Tt.to_string())
