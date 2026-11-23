"""Run the ignition estimators on every event scar.

Usage: python -I run.py <prepdir> <out.csv> [firms_only|all] [scar_index_list.txt]
  all         FIRMS + Sentinel-2/Landsat fire pixels (the production run)
  firms_only  FIRMS points only (used to test against fire pixels seen before the first FIRMS point)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from concurrent.futures import ProcessPoolExecutor
import ign

PREP, OUTF = sys.argv[1], sys.argv[2]
MODE = sys.argv[3] if len(sys.argv) > 3 else "all"
SUB = sys.argv[4] if len(sys.argv) > 4 else None
BL = "/mnt/project-files/research/ratapani-burn-labels/"
SD = "/mnt/project-files/ratapani/fsi/scouting/data/daily_dating/soft_dates.csv"
H = 3600.0

S = pd.read_pickle(PREP + "/scars.pkl")
D = pd.read_pickle(PREP + "/dets.pkl")
P = pd.read_pickle(PREP + "/passes.pkl")
Lk = pd.read_pickle(PREP + "/links.pkl")
EP = pd.Timestamp(0, tz="UTC")
D["th"] = (D.t - EP) / pd.Timedelta(hours=1)
P["th"] = (P.t - EP) / pd.Timedelta(hours=1)
PT = np.sort(P.th.values)
if MODE == "firms_only":
    Lk = Lk[Lk.det.map(D.src) == "firms"]
G = {k: v.det.values for k, v in Lk.groupby("scar")}

with rasterio.open(BL + "rasters/burn_2021.tif") as r:
    TR, SHAPE = r.transform, (r.height, r.width)
grid = gpd.read_file("/mnt/project-files/ratapani/grid_500m.geojson").to_crs(32643)
CELL = rasterize(((g, int(c)) for g, c in zip(grid.geometry, grid.cell_id)), out_shape=SHAPE, transform=TR,
                 fill=-1, dtype="int32")
SOFT = pd.read_csv(SD)
SOFT = {(int(a), int(b)): (pd.Timestamp(c), pd.Timestamp(d), pd.Timestamp(e), pd.Timestamp(f))
        for a, b, c, d, e, f in zip(SOFT.cell_id, SOFT.season, SOFT.date_lo, SOFT.date_hi, SOFT.orig_lo, SOFT.orig_hi)}
RAST = {}


def raster(season):
    if season not in RAST:
        f = BL + f"rasters/burn_{season}.tif"
        RAST[season] = rasterio.open(f).read([1, 2]) if os.path.exists(f) else None
    return RAST[season]


def weights_fn(t1h):
    """Candidate weights from optical burn dates: down-weight ground that burned after the first detection,
    up-weight ground already burned at a clear look before the first detection."""
    t1 = pd.Timestamp(t1h * H, unit="s", tz="UTC")
    t1_ist = (t1 + pd.Timedelta(hours=5.5)).tz_localize(None)
    season = t1_ist.year + (1 if t1_ist.month >= 7 else 0)
    jan1 = pd.Timestamp(f"{season}-01-01")
    rb = raster(season)

    def f(xs, ys):
        w = np.ones(len(xs))
        col = ((xs - TR.c) / TR.a).astype(int); row = ((ys - TR.f) / TR.e).astype(int)
        ok = (row >= 0) & (row < SHAPE[0]) & (col >= 0) & (col < SHAPE[1])
        if rb is not None:
            we = np.full(len(xs), -999); ws = np.full(len(xs), -999)
            we[ok] = rb[0][row[ok], col[ok]]; ws[ok] = rb[1][row[ok], col[ok]]
            has = we > -999
            # look times (10:45 IST) as timestamps
            ws_t = jan1 + pd.to_timedelta(ws, unit="D") + pd.Timedelta(hours=10.75)
            we_t = jan1 + pd.to_timedelta(we, unit="D") + pd.Timedelta(hours=10.75)
            w[has & (ws_t > t1_ist)] *= 0.15
            w[has & (we_t < t1_ist)] *= 2.0
        cid = np.full(len(xs), -1); cid[ok] = CELL[row[ok], col[ok]]
        for c in np.unique(cid[cid >= 0]):
            s = SOFT.get((int(c), int(season)))
            if s is None:
                continue
            lo, hi, olo, ohi = s
            if olo <= t1_ist.normalize() <= ohi + pd.Timedelta(days=1) and lo > t1_ist.normalize():
                w[cid == c] *= 0.2
        return w
    return f


def one(i):
    s = S.iloc[i]
    base = dict(scar=i, event_id=s.event_id)
    idx = G.get(i)
    if idx is None or len(idx) == 0:
        base.update(status="no_detection")
        return base
    d = D.loc[idx].sort_values("th")
    d = d.iloc[:60]
    t_pre = (s.t_pre - EP) / pd.Timedelta(hours=1)
    t1 = d.th.iloc[0]
    # a fire pixel on the pre image itself means the fire was already burning at that look
    prev = PT[(PT > t_pre - ign.PRE_SLACK) & (PT < t1 - 0.5)]
    t_lo_soft = prev.max() if len(prev) else t_pre
    try:
        o = ign.estimate(s.geometry, d, t_pre, PT[(PT >= t_pre - ign.PRE_SLACK) & (PT <= t1)], cand_w=weights_fn(t1))
    except Exception as e:
        base.update(status="error:" + str(e)[:60])
        return base
    o.update(base)
    o.update(status="ok", t_pre=t_pre, t_lo_soft=t_lo_soft, first_src=d.src.iloc[0], first_sensor=d.sensor.iloc[0],
             n_af=int((d.src == "af").sum()), n_firms=int((d.src == "firms").sum()),
             n_days=int(np.ptp(np.floor((d.th.values + 5.5) / 24)) + 1),
             n_ign_v150=ign.min_ignitions(d, t_lo_soft, 150.0), n_ign_v60=ign.min_ignitions(d, t_lo_soft, 60.0),
             first_spread_m=float(np.hypot(d[d.th <= t1 + 1].x - d[d.th <= t1 + 1].x.mean(),
                                           d[d.th <= t1 + 1].y - d[d.th <= t1 + 1].y.mean()).max()))
    return o


if __name__ == "__main__":
    ids = range(len(S)) if SUB is None else [int(l) for l in open(SUB)]
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(one, ids, chunksize=8))
    pd.DataFrame(res).to_csv(OUTF, index=False)
    print(pd.DataFrame(res).status.value_counts())
