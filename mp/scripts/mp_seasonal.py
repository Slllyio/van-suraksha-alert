"""MP scoring under the seasonal rules (usage: python mp_seasonal.py <feats_dir> <tag> <archive.parquet>[;<archive2>...]).
  - Targets: only fires from 15 Feb to 31 May. Issue days 13 Feb .. 30 May (forecast for the next 1-2 days).
  - Fires from 1 Oct to 14 Feb are a 'burned early this season' input, never a target:
      early_cell / early_nb3 / early_nb7 = early fire-days in the cell / 3x3 / 7x7 block from 1 Oct to min(t, 14 Feb).
  - On 15-28 Feb, likely control burns are dropped from the targets: a same-day cluster of detections (linked within
    1 km) that is day-only, has at most 2 points, max FRP <= 5 MW, and has no other detection within 1 km from 2 days
    before to 3 days after. (They stay in the fire-history inputs: they did burn.)
Everything else as mp_officer_eval.py (own / neighbour-borrow models, train 2019-2021, test 2022-2024, strict 'first
day' and loose 'any part' fire-event and beat-episode scores, ground covered). Writes results_officer/seasonal_<tag>.csv."""
import json, sys, time, zlib
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from scipy.ndimage import uniform_filter
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix

FEATS, TAG, SOURCES = sys.argv[1], sys.argv[2], sys.argv[3].split(";")
SCR = Path(__file__).parent
_src = (SCR / "mp_officer_eval.py").read_text(encoding="utf-8")
sys.argv = ["mp_officer_eval.py", FEATS, TAG]
exec(_src.split("divs = sorted(")[0])        # shared: dryness/add_dry/metrics/lagged, constants, NB, P, FUT
X0, Y1, S = 399000.0, 2996000.0, 500.0
EARLY = ["early_cell", "early_nb3", "early_nb7"]
OUTF = MP / "results_officer" / f"seasonal_{TAG}.csv"


def season_of(d):
    return np.where(d.month >= 10, d.year + 1, d.year)


# ---- detections (all sources), local IST date, UTM position, control-burn flag ----
def load_detections():
    cols = ["latitude", "longitude", "acq_date", "acq_time", "type", "daynight", "frp"]
    v = pd.concat([pd.read_parquet(p, columns=cols) for p in SOURCES], ignore_index=True)
    v = v[v.type == 0].copy()
    v["acq_date"] = pd.to_datetime(v.acq_date)
    utc = v.acq_date + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m")
    v["d"] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
    v = v[(v.d >= "2018-10-01") & (v.d <= "2024-05-31")]
    v = v[(v.d.dt.month >= 10) | (v.d.dt.month <= 5)].reset_index(drop=True)
    xy = gpd.GeoSeries(gpd.points_from_xy(v.longitude, v.latitude), crs=4326).to_crs(32643)
    v["x"], v["y"] = xy.x.to_numpy(), xy.y.to_numpy()
    v["col"] = np.floor((v.x - X0) / S).astype(int); v["row"] = np.floor((Y1 - v.y) / S).astype(int)
    v["season"] = season_of(v.d.dt)
    v["control"] = False
    feb = v[(v.d.dt.month == 2) & (v.d.dt.day >= 15)]
    tree_all = cKDTree(v[["x", "y"]].to_numpy())
    dnum = (v.d - pd.Timestamp("2018-01-01")).dt.days.to_numpy()
    n_ctrl = 0
    for day, g in feb.groupby("d"):
        idx = g.index.to_numpy()
        t = cKDTree(g[["x", "y"]].to_numpy())
        pairs = t.query_pairs(1000.0, output_type="ndarray")
        n = len(idx)
        m = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n)) if len(pairs) else coo_matrix((n, n))
        _, lab = connected_components(m, directed=False)
        d0 = (day - pd.Timestamp("2018-01-01")).days
        for k in np.unique(lab):
            members = idx[lab == k]
            if len(members) > 2 or (v.daynight[members] != "D").any() or v.frp[members].max() > 5:
                continue
            near = set()
            for mbr in members:
                near.update(tree_all.query_ball_point([v.x[mbr], v.y[mbr]], 1000.0))
            near -= set(members)
            near = np.fromiter(near, int) if near else np.array([], int)
            if len(near) and ((dnum[near] >= d0 - 2) & (dnum[near] <= d0 + 3)).any():
                continue
            v.loc[members, "control"] = True; n_ctrl += 1
    print(f"{TAG}: detections {len(v)}, likely control-burn clusters dropped (15-28 Feb): {n_ctrl} "
          f"({int(v.control.sum())} points)", flush=True)
    return v


DET = load_detections()
pd.Series(dict(clusters_points=int(DET.control.sum()))).to_csv(MP / "results_officer" / f"control_burns_{TAG}.csv")
ALLDAYS = pd.date_range("2018-10-01", "2024-06-02")
DI = pd.Series(np.arange(len(ALLDAYS)), index=ALLDAYS)


def division_layers(dv, grid):
    """target raster TF (15 Feb-31 May, controls dropped) and early raster EF (1 Oct-14 Feb) over the division bbox."""
    c0, r0 = grid.col.min(), grid.row.min()
    NI, NJ = grid.col.max() - c0 + 1, grid.row.max() - r0 + 1
    v = DET[(DET.col >= c0) & (DET.col < c0 + NI) & (DET.row >= r0) & (DET.row < r0 + NJ)]
    md = v.d.dt.month * 100 + v.d.dt.day
    tgt = v[(md >= 215) & (md <= 531) & ~v.control]
    early = v[(md >= 1001) | (md <= 214)]
    TF = np.zeros((len(ALLDAYS), NI, NJ), bool); EF = np.zeros_like(TF)
    TF[DI[tgt.d].to_numpy(), tgt.col - c0, tgt.row - r0] = True
    EF[DI[early.d].to_numpy(), early.col - c0, early.row - r0] = True
    return TF, EF, c0, r0


def seasonal_rows(dv, grid, years, sample=False, rng=None):
    TF, EF, c0, r0 = division_layers(dv, grid)
    gi, gj = (grid.col - c0).to_numpy(), (grid.row - r0).to_numpy()
    pos = pd.Series(np.arange(len(grid)), index=grid.cell_id)
    out = []
    for yr in years:
        x = pd.read_parquet(MP / dv / FEATS / f"season_{yr}.parquet")
        md = x.date.dt.month * 100 + x.date.dt.day
        x = x[(md >= 213) & (md <= 530)].reset_index(drop=True)
        dix = DI[x.date].to_numpy(); p = pos[x.cell_id].to_numpy()
        x["y"] = (TF[dix + 1, gi[p], gj[p]] | TF[dix + 2, gi[p], gj[p]]).astype(np.uint8)
        x["fire_t"] = TF[dix, gi[p], gj[p]].astype(np.uint8)
        # early-season burns: cumulative fire-days from 1 Oct to min(t, 14 Feb)
        a, b = DI[pd.Timestamp(f"{yr - 1}-10-01")], DI[pd.Timestamp(f"{yr}-02-14")]
        cum = np.cumsum(EF[a:b + 1], axis=0, dtype=np.float32)
        k = np.clip(dix - a, 0, b - a)                       # index of min(t, 14 Feb) within the early window
        days_u = np.unique(k)
        e_cell = np.zeros(len(x), np.float32); e3 = np.zeros_like(e_cell); e7 = np.zeros_like(e_cell)
        for kk in days_u:
            m = k == kk
            layer = cum[kk]
            e_cell[m] = layer[gi[p[m]], gj[p[m]]]
            e3[m] = (uniform_filter(layer, 3, mode="constant") * 9)[gi[p[m]], gj[p[m]]]
            e7[m] = (uniform_filter(layer, 7, mode="constant") * 49)[gi[p[m]], gj[p[m]]]
        x["early_cell"], x["early_nb3"], x["early_nb7"] = e_cell, e3, e7
        if sample:
            x = x[(x.y == 1) | (rng.random(len(x)) < 0.03)]
        out.append(add_dry(x, grid, yr))
    return pd.concat(out, ignore_index=True)


def train_seasonal(dv):
    f = MP / dv / f"train_season_{TAG}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    x = seasonal_rows(dv, grid_of(dv), TRAIN_Y, sample=True, rng=np.random.default_rng(zlib.crc32(dv.encode())))
    x.to_parquet(f, index=False)
    return x


divs = sorted(p.parent.name for p in MP.glob("*/grid_500m.geojson")
              if len(list((p.parent / FEATS).glob("season_*.parquet"))) >= 6)
t0 = time.time()
for dv in divs:
    train_seasonal(dv)
print(TAG, "seasonal training samples ready", f"{time.time() - t0:.0f}s", flush=True)
rows = pd.read_csv(OUTF).to_dict("records") if OUTF.exists() else []
done = {r["division"] for r in rows}
for dv in divs:
    if dv in done:
        continue
    t0 = time.time()
    own = train_seasonal(dv)
    nbrs = [n for n in NB.get(dv, []) if n in divs]
    pool = pd.concat([own.assign(_w=3.0)] + [train_seasonal(n).assign(_w=1.0) for n in nbrs], ignore_index=True)
    cols = sorted(set(pool.columns) - {"date", "cell_id", "i", "j", "y", "y3", "_w", "fire_t"} - FUT)
    grid = grid_of(dv)
    te = seasonal_rows(dv, grid, TEST_Y)
    bm = pd.read_csv(MP / dv / "beat_map.csv")[["cell_id", "Range", "beat_id"]]
    weak = int(own.y.sum()) < WEAK_FIRES
    base = dict(division=dv, label_set=TAG, rules="seasonal", train_fires=int(own.y.sum()), weak=weak, neighbours=len(nbrs))
    X = te.reindex(columns=cols)
    for model, data in (("own", own.assign(_w=1.0)), ("borrow", pool)):
        if data.y.sum() < 20 or te.y.sum() == 0:
            rows.append(dict(base, model=model, note="too few fires")); continue
        m = lgb.train(P, lgb.Dataset(data.reindex(columns=cols), data.y, weight=data._w), 600)
        rows.append(dict(base, model=model, recommended=(model == ("borrow" if weak else "own")),
                         **metrics(te, m.predict(X), bm, fire_col="fire_t")))
    pd.DataFrame(rows).to_csv(OUTF, index=False)
    print(TAG, "seasonal", dv, f"{time.time() - t0:.0f}s", flush=True)
print(TAG, "seasonal done", len(rows), "rows")
