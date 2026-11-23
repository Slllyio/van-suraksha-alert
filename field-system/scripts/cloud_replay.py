"""Statewide replay of the PC's 5 check days with cloud weather and MODIS (pc_models/cloud_series) instead of the PC's
Earth Engine inputs. Everything else is the PC's: build_day_features.py, fire_celldays.parquet, the HLS npz, static
tables, models, calibration. The rule is live_score.py's, with each division's own_count taken from the PC's
pc_check/division_counts.csv, so the comparison isolates what the cloud inputs change.
Usage: [CR_NPZ=cloud_dry_2026.npz CR_TAG=all_cloud] python cloud_replay.py  -> docs/cloud_scoring/replay.json, replay_days.csv"""
import json, lzma, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb

FS = Path(__file__).resolve().parent.parent
P = FS / "pc_models"; sys.path.insert(0, str(P)); sys.path.insert(0, str(FS))
import build_day_features as B, gfs_features as G
from app.cloud_inputs import modis_frames
CK = FS / "pc_check"; OUT = FS / "docs/cloud_scoring" / os.environ.get("CR_TAG", ""); TMP = Path(os.environ.get("CR_TMP", "/tmp/cloud_replay")); TMP.mkdir(exist_ok=True, parents=True)
DAYS = ["2026-03-12", "2026-03-17", "2026-04-05", "2026-04-22", "2026-05-10"]
meta = json.loads((P / "meta.json").read_text()); rule = meta["live_rule"]
static = pd.read_parquet(P / "static_inputs.parquet"); clim = pd.read_parquet(P / "modis_clim.parquet")
gis = pd.read_parquet("/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet")
fires = pd.read_parquet(P / "fire_celldays.parquet"); fires["date"] = pd.to_datetime(fires.date)
npz = dict(np.load(os.environ.get("CR_NPZ", "/mnt/project-files/ratapani/mp_grid/dryness/mp_dry_2026.npz")))   # CR_NPZ = cloud HLS
gfs = pd.read_csv(P / "cloud_series/gfs_daily_2026.csv", parse_dates=["date"])
sw = pd.read_csv(P / "cloud_series/swvl1_2026.csv", parse_dates=["date"])
if os.environ.get("CR_SOILMAP"):                                           # PIPELINE's ERA5 -> ERA5-Land quantile map
    sys.path.insert(0, str(P / "soil_map")); import soil_map as SM
    _M = SM.load()
    for dv, i in sw.groupby("division").groups.items():
        sw.loc[i, "swvl1"] = SM.apply(_M, dv, sw.loc[i, "swvl1"].to_numpy())
MZ = dict(np.load(P / "cloud_series/modis_2026.npz"))
counts = pd.read_csv(CK / "division_counts.csv", parse_dates=["date"])


def scores(t):
    f = TMP / f"scores_{t.date()}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    parts = []
    for dv, info in sorted(meta["divisions"].items()):
        div = B.Division(dv, static.loc[static.division == dv, "cell"].to_numpy())
        w = G.weather_table(gfs[gfs.division == dv].set_index("date"), sw[sw.division == dv].set_index("date").swvl1)
        sr, lst = modis_frames(MZ, div.cells, 2026)
        X = B.build(div, t, static, gis, fires, sr, lst, clim[clim.division == dv], npz, w.loc[t], info["features"])
        m = lgb.Booster(model_str=lzma.decompress((P / "models" / f"{dv}.txt.xz").read_bytes()).decode())
        s = m.predict(X.reindex(columns=info["features"])).astype(np.float32)
        cal = json.loads((P / "calibration" / f"{dv}.json").read_text())
        parts.append(pd.DataFrame({"cell": X.cell, "division": dv, "score": s, "pct": 100 * np.interp(s, cal["x"], cal["y"]),
                                   "quiet": X.quiet.astype(np.uint8)}))
        print(t.date(), dv, flush=True)
    D = pd.concat(parts, ignore_index=True); D.to_parquet(f); return D


def apply_rule(D, own):
    """live_score.py's floor + quiet + statewide pool, with own_count per division given."""
    k, floor_f, quiet_f = rule["k"], rule["floor"], rule["quiet"]
    D = D.sort_values(["division", "cell"]).reset_index(drop=True)
    flag = np.zeros(len(D), bool)
    for dv, idx in D.groupby("division").indices.items():
        s = D.score.to_numpy()[idx]; q = D.quiet.to_numpy()[idx].astype(bool)
        fl = int(round(floor_f * own[dv]))
        nq = min(int(round(quiet_f * fl)), int(q.sum())); no = min(fl - nq, int((~q).sum())); nq = min(fl - no, int(q.sum()))
        for grp, n in ((q, nq), (~q, no)):
            g = np.flatnonzero(grp)
            if n > 0:
                flag[idx[g[np.argsort(-s[g], kind="stable")[:n]]]] = True
    rest = max(sum(own.values()) - int(flag.sum()), 0)
    order = np.argsort(-D.pct.to_numpy(), kind="stable")
    fq = ~flag & (D.quiet.to_numpy() == 1); fo = ~flag & (D.quiet.to_numpy() == 0)
    rq = min(int(round(quiet_f * rest)), int(fq.sum()))
    for grp, n in ((fq, rq), (fo, rest - rq)):
        o = order[grp[order]]; flag[o[:n]] = True
    return D.assign(flag=flag)


rows = []
for d in DAYS:
    t = pd.Timestamp(d)
    pc = pd.read_parquet(CK / f"live_flags_{d}.parquet")
    own = counts[counts.date == t].set_index("division").own_count.to_dict()
    me = apply_rule(scores(t), own)
    m = pc.merge(me, on=["cell", "division"], suffixes=("_pc", "_cl"))
    # fires on day +1 or +2, per square (statewide, a square counts once)
    nxt = fires[(fires.date > t) & (fires.date <= t + pd.Timedelta(days=2))]
    fc = set(nxt.row * 1829 + nxt.col)
    sq = m.groupby("cell").agg(pc=("flag_pc", "max"), cl=("flag_cl", "max"))
    sq["fire"] = sq.index.isin(fc)
    r = dict(date=d, squares=len(sq), flags_pc=int(sq.pc.sum()), flags_cloud=int(sq.cl.sum()),
             same_flags=round(float((sq.pc & sq.cl).sum() / max(sq.pc.sum(), 1)), 3),
             score_r=round(float(np.corrcoef(m.score_pc, m.score_cl)[0, 1]), 4),
             fire_squares=int(sq.fire.sum()), caught_pc=round(float(sq.pc[sq.fire].mean()), 3), caught_cloud=round(float(sq.cl[sq.fire].mean()), 3))
    rows.append(r); print(r, flush=True)
R = pd.DataFrame(rows); OUT.mkdir(parents=True, exist_ok=True); R.to_csv(OUT / "replay_days.csv", index=False)
tot = dict(fire_squares=int(R.fire_squares.sum()), caught_pc=round(float((R.caught_pc * R.fire_squares).sum() / R.fire_squares.sum()), 3),
           caught_cloud=round(float((R.caught_cloud * R.fire_squares).sum() / R.fire_squares.sum()), 3),
           same_flags=round(float((R.same_flags * R.flags_pc).sum() / R.flags_pc.sum()), 3))
json.dump(dict(days=rows, total=tot), open(OUT / "replay.json", "w"), indent=1); print(tot)
