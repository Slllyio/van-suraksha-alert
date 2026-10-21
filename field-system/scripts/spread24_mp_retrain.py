# Akkshay 19 Oct "train on all over mp": 24 h area model on Ratapani (818 fires, 2,246 forecasts) + MP big fires (600 fires,
# 3,535 forecasts; plus 2,000 small MP fires 20-200 ha, 6,187 forecasts, spread thread's mp_bigfire_apply.py truth: MP history scars + straight-line timing blend). Every model is
# scored on fires it never saw: leave-one-season-out, and for MP also leave-division-group-out (5 groups). Map = 265 m blocks +
# extra area nearest-first (as app/spread24.py); score = overlap (Dice) with the burnt-by-24 h truth, mean per fire.
#   python scripts/spread24_mp_retrain.py <scratch>/u_maps.pkl
import json, pickle, sys
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import spread24 as S

H = Path("/mnt/project-files/ratapani/spread/unseen_validation/app_handoff")
OUT = Path(__file__).resolve().parent.parent / "docs/spread24"
COLS = S.COLS
# ---------- Ratapani set: cumulative truth along the nearest-first order, per forecast
M = pickle.load(open(sys.argv[1], "rb"))
RI = pd.read_parquet(H / "u_issues.parquet").set_index(["fire", "k"])
RR = pd.read_csv(H / "area_model.csv")
A = pd.read_csv("/mnt/project-files/research/big-fires/results/fire_alerts.csv", parse_dates=["t"]); A = A[A.sat != "modis"]
X0, Y0 = 737300.0, 2560500.0
CUM = {}
def cache(key, P, xy, truth):
    dd = cKDTree(xy).query(P)[0]; foot = dd <= 265
    order = np.argsort(np.where(foot, -1, dd), kind="stable")
    CUM[key] = (int(foot.sum()), np.cumsum(truth[order]), int(truth.sum()))
for fire, g in RR.groupby("fire"):
    d = A[A.fire == fire].sort_values("t").reset_index(drop=True)
    d["lk"] = (d.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1
    mp = M[fire]; r0, r1, c0, c1 = mp["box"]; Tg = mp["Tg"].ravel(); dom = mp["dom"].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    for it in g.itertuples():
        cache(("R", fire, it.k), P, d[d.lk <= it.k][["x", "y"]].values, dom & (Tg <= RI.loc[(fire, it.k), "th"] + 24))
RR = RR.assign(set="ratapani", key=[("R", f, k) for f, k in zip(RR.fire, RR.k)], division="Ratapani")
print("ratapani cached", flush=True)
# ---------- MP big fires: rebuild each fire's dots exactly as mp_bigfire_apply.py, then the truth from maps/<seed>.npz
from pyproj import Transformer
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
MP = pd.read_csv(H / "mp/mp_rows.csv")
MO = "/mnt/project-files/fire-alert-scars/mp/out"
to43 = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
E = pd.read_csv(f"{MO}/mp_alert_event.csv", usecols=["latitude", "longitude", "acq_date", "acq_time", "instrument", "event_id"])
E = E[E.instrument == "VIIRS"].copy()
E["t"] = pd.to_datetime(E.acq_date + " " + E.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d %H%M")
E["x"], E["y"] = to43(E.longitude.values, E.latitude.values); E = E.reset_index(drop=True); ET = cKDTree(E[["x", "y"]].values)
def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(750.0)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]
bad = 0
for seed, g in MP.groupby("seed"):
    s = E[E.event_id == seed]; x, y, t0 = s.x.mean(), s.y.mean(), s.t.min()
    near = E.iloc[ET.query_ball_point([x, y], 3000)]
    near = near[(near.t >= t0 - pd.Timedelta(days=3)) & (near.t <= t0 + pd.Timedelta(days=10))].reset_index(drop=True)
    lab = clusters(near[["x", "y"]].values); keep = set(lab[(near.event_id == seed).values])
    d = near[np.isin(lab, list(keep))].sort_values("t").reset_index(drop=True)
    d["lk"] = (d.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1
    z = np.load(H / f"mp/maps/{seed}.npz"); x0, y1, W, Hh = z["box"]; W, Hh = int(W), int(Hh)
    rr, cc = np.mgrid[0:Hh, 0:W]; P = np.c_[(x0 + (cc + .5) * 20).ravel(), (y1 - (rr + .5) * 20).ravel()]
    dom = z["dom"].ravel(); Tg = np.nan_to_num(z["Tg"].astype(np.float32).ravel(), nan=np.inf); th = z["th"]
    for it in g.itertuples():
        xy = d[d.lk <= it.k][["x", "y"]].values
        if len(xy) != it.n_dots: bad += 1
        cache(("M", seed, it.k), P, xy, dom & (Tg <= th[it.k] + 24))
MP = MP.assign(set="mp_" + MP.size_class, key=[("M", f, k) for f, k in zip(MP.seed, MP.k)], fire=MP.seed)
print("mp cached, dot-count mismatches:", bad, flush=True)
# ---------- pooled table
D = pd.concat([RR[["set", "key", "fire", "season", "division", "extra_true_ha"] + COLS], MP[["set", "key", "fire", "season", "division", "extra_true_ha"] + COLS]], ignore_index=True)
divs = sorted(D.division[D.set != "ratapani"].unique()); rng = np.random.default_rng(0)
grp = dict(zip(divs, rng.permutation(len(divs)) % 5)); D["dgroup"] = D.division.map(grp).fillna(-1).astype(int)
def dice(key, ha):
    nf, ct, T = CUM[key]; n = min(int(nf + max(ha, 0) / .04), len(ct)); hit = ct[n - 1] if n > 0 else 0
    return 2 * hit / max(n + T, 1)
prm = dict(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=30, verbose=-1, n_jobs=8)
def fit(tr): return lgb.LGBMRegressor(**prm).fit(D.loc[tr, COLS], np.log1p(D.extra_true_ha[tr]))
pred = {}
for name, train_sets in (("ratapani_only", {"ratapani"}), ("mp_only", {"mp_big", "mp_small"}), ("pooled", {"ratapani", "mp_big", "mp_small"}), ("pooled_big_only", {"ratapani", "mp_big"})):
    p = np.zeros(len(D))
    for Y in sorted(D.season.unique()):                    # season held out
        te = D.season == Y; tr = ~te & D.set.isin(train_sets)
        p[te] = np.expm1(fit(tr).predict(D.loc[te, COLS]))
    pred[f"{name}|season"] = p
    if train_sets != {"ratapani"}:                                   # MP division group held out too (and the season)
        p2 = pred[f"{name}|season"].copy()
        for gi in range(5):
            for Y in sorted(D.season.unique()):
                te = (D.dgroup == gi) & (D.season == Y)
                if not te.any(): continue
                tr = D.set.isin(train_sets) & (D.dgroup != gi) & (D.season != Y)
                p2[te] = np.expm1(fit(tr).predict(D.loc[te, COLS]))
        pred[f"{name}|season+division"] = p2
    print(name, "done", flush=True)
pred["ratapani_only|season+division"] = pred["ratapani_only|season"]   # Ratapani never contains MP divisions
pred["rule|"] = S.MED_HA * D.n_act.values
pred["true_area|"] = D.extra_true_ha.values
for k, p in pred.items(): D["s_" + k] = [dice(key, h) for key, h in zip(D.key, p)]
res = {}
for st in ("ratapani", "mp_big", "mp_small"):
    fm = D[D.set == st].groupby("fire")[[c for c in D.columns if c.startswith("s_")]].mean()
    res[st] = dict(fires=len(fm), mean_overlap_per_fire=fm.mean().round(4).to_dict())
    for a in ("pooled|season", "pooled|season+division", "mp_only|season+division", "pooled_big_only|season+division"):
        dl = (fm["s_" + a] - fm["s_ratapani_only|season"]).values
        res[st][f"{a}_minus_ratapani_only"] = dict(mean=round(float(dl.mean()), 4),
            ci=[round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)],
            better_worse=[int((dl > .005).sum()), int((dl < -.005).sum())])
    sub = D[D.set == st]
    res[st]["median_ha"] = {k: round(float(np.median(p[(D.set == st).values])), 1) for k, p in pred.items()}
    res[st]["by_season"] = sub.groupby("season")[["s_ratapani_only|season", "s_pooled|season+division"]].mean().round(3).to_dict("index")
json.dump(res, open(OUT / "mp_retrain.json", "w"), indent=1, default=str)
D.drop(columns="key").to_csv(OUT / "mp_retrain_forecasts.csv", index=False)
print(json.dumps(res, indent=1, default=str))
