# Replay check of app/spread24.py on the spread thread's 818 unseen Ratapani fires (2,246 forecasts), same truth as
# ratapani/spread/unseen_validation/README.md sections 17-18: scar pixels burned by the look + 24 h.
#   gunzip -c <app_handoff>/u_maps.pkl.gz > <scratch>/u_maps.pkl && python scripts/spread24_replay.py <scratch>/u_maps.pkl
import json, pickle, sys
from pathlib import Path
import numpy as np, pandas as pd, shapely
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import spread24 as S

H = Path("/mnt/project-files/ratapani/spread/unseen_validation/app_handoff")
M = pickle.load(open(sys.argv[1], "rb"))
I = pd.read_parquet(H / "u_issues.parquet").set_index(["fire", "k"])
R = pd.read_csv(H / "area_model.csv")
A = pd.read_csv("/mnt/project-files/research/big-fires/results/fire_alerts.csv", parse_dates=["t"]); A = A[A.sat != "modis"]
X0, Y0 = 737300.0, 2560500.0
rows, diff = [], []
for fire, g in R.groupby("fire"):
    d = A[A.fire == fire].sort_values("t").reset_index(drop=True)
    d["lk"] = (d.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1
    mp = M[fire]; r0, r1, c0, c1 = mp["box"]; Tg = mp["Tg"].ravel(); dom = mp["dom"].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; px, py = (X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()
    first_doy = d.t.min().dayofyear
    for it in g.itertuples():
        kn = d[d.lk <= it.k]
        dots = [dict(t=r.t.to_pydatetime(), x=r.x, y=r.y, frp=r.frp, sat=r.sat, day=r.daynight == "D") for r in kn.itertuples()]
        f, xy, blocks = S.features(dots)
        diff.append({c: f[c] - getattr(it, c) for c in S.COLS})
        truth = dom & (Tg <= I.loc[(fire, it.k), "th"] + 24)
        o = dict(fire=fire, k=it.k, season=it.season, from_15feb=first_doy >= 46)
        for name, ex in (("rule", S.MED_HA * f["n_act"]), ("loso", it._fields and it.mean), ("app", S.extra_ha(f, "ratapani"))):
            shp, _ = S.fill(xy, blocks, ex)
            m = shapely.contains_xy(shp, px, py)
            hit = (m & truth).sum()
            o[name] = 2 * hit / max(m.sum() + truth.sum(), 1)
            o[name + "_prec"] = hit / max(m.sum(), 1); o[name + "_rec"] = hit / max(truth.sum(), 1)
        rows.append(o)
O = pd.DataFrame(rows); D = pd.DataFrame(diff)
fm = O.groupby("fire").agg({**{c: "mean" for c in O.columns if c.split("_")[0] in ("rule", "loso", "app")}, "from_15feb": "first", "season": "first"})
res = dict(forecasts=len(O), fires=len(fm),
           feature_max_abs_diff=D.abs().max().round(3).to_dict(),
           mean_overlap_per_fire={k: round(float(fm[k].mean()), 4) for k in ("rule", "loso", "app")},
           from_15feb={k: round(float(fm[fm.from_15feb][k].mean()), 4) for k in ("rule", "loso")} | {"fires": int(fm.from_15feb.sum())},
           precision={k: round(float(fm[k + "_prec"].mean()), 3) for k in ("rule", "loso")},
           recall={k: round(float(fm[k + "_rec"].mean()), 3) for k in ("rule", "loso")},
           loso_vs_rule_better_worse=[int(((fm.loso - fm.rule) > .005).sum()), int(((fm.loso - fm.rule) < -.005).sum())],
           by_season=fm.groupby("season")[["rule", "loso"]].mean().round(3).to_dict("index"),
           research={"s17_rule": 0.447, "s17_learned": 0.460, "s18_rule_759": 0.448, "s18_area_rule_order_759": 0.462})
out = Path(__file__).resolve().parent.parent / "docs/spread24/replay.json"
json.dump(res, open(out, "w"), indent=1, default=str); O.to_csv(out.with_name("replay_forecasts.csv"), index=False)
print(json.dumps(res, indent=1, default=str))
