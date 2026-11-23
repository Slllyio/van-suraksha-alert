"""Pilot: date every 20 m pixel of a scar from all clear Sentinel-2 + Landsat 8/9 looks, then check against VIIRS.
For a sample of 2025 scars (>= 20 ha, 15 Feb-15 Jun): chip = outline box + 300 m; looks from 20 days before to 30 days
after the event's first alert. Per pixel inside the outline: drop = NBR minus its own pre-fire median (looks 1-20 days
before), relative to the same drop outside the outline (clear pixels in the chip). Burn window = (last clear look with
drop < 0.10, first clear look with drop >= 0.10] and the drop still >= 0.06 at the next clear look, if any.
VIIRS check: S-NPP + NOAA-20 + NOAA-21 points (type 0) from 1 day before to 30 days after; a pixel is "seen" when a point
lies within 300 m; its VIIRS date = earliest such point (IST date). Agreement = VIIRS date inside the window (+-1 day).
Out: pixel_dating/events.csv (one row per event), pixels.parquet. Usage: python pixel_dating.py [n_events]"""
import os, sys, datetime as dt, numpy as np, pandas as pd, geopandas as gpd, shapely, rasterio
from concurrent.futures import ThreadPoolExecutor
from rasterio.features import rasterize
from scipy.spatial import cKDTree
from pyproj import Transformer
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alert_scar as A
import weekly_report as W
OUT = "/mnt/project-files/fire-alert-scars/mp/pixel_dating/"
RES, BUF, DROP, KEEP = 20.0, 300.0, 0.10, 0.06
T = Transformer.from_crs(4326, 32643, always_xy=True)


def viirs(year):
    fs = [f"/mnt/project-files/fire-alert-scars/alerts_mp/viirs-{s}_{year}.csv" for s in ("snpp", "jpss1", "noaa21")]
    v = pd.concat([pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "type"]) for f in fs if os.path.exists(f)])
    v = v[v.type == 0]
    t = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m") + pd.Timedelta("5h30m")
    x, y = T.transform(v.longitude.values, v.latitude.values)
    return pd.DataFrame(dict(x=x, y=y, day=t.dt.normalize().values))


def one(ev, geom, V):
    d = pd.Timestamp(ev.acq_date).normalize()
    g = shapely.transform(geom, lambda xy: np.column_stack(T.transform(xy[:, 0], xy[:, 1])))
    x0, y0, x1, y1 = g.bounds
    x0, y1 = np.floor((x0 - BUF) / RES) * RES, np.ceil((y1 + BUF) / RES) * RES
    nx, ny = int(np.ceil((x1 + BUF - x0) / RES)), int(np.ceil((y1 - (y0 - BUF)) / RES))
    n = max(nx, ny)
    tr = rasterio.transform.from_origin(x0, y1, RES, RES)
    inside = rasterize([(g, 1)], out_shape=(n, n), transform=tr, fill=0, dtype="uint8").astype(bool)
    bbox = Transformer.from_crs(32643, 4326, always_xy=True).transform_bounds(x0, y1 - n * RES, x0 + n * RES, y1)
    rng = f"{(d - pd.Timedelta(days=20)).date()}/{(d + pd.Timedelta(days=30)).date()}"
    groups = {}
    for col, s in (("sentinel-2-l2a", "s2"), ("landsat-c2-l2", "ls")):
        q = {"eo:cloud_cover": {"lt": 80}}
        if s == "ls": q["platform"] = {"in": ["landsat-8", "landsat-9"]}
        for it in A.catalog().search(collections=[col], bbox=bbox, datetime=rng, query=q).items():
            groups.setdefault((it.datetime.date(), s), []).append(it)
    keys = sorted(groups)
    with ThreadPoolExecutor(6) as ex:
        stack = list(ex.map(lambda k: A.look(groups[k], k[1], tr, n), keys))
    looks = {}
    for (dd, s), (nb, ni) in zip(keys, stack):
        c = (~np.isnan(nb))[inside].mean()
        if c > 0 and (dd not in looks or c > looks[dd][1]):
            looks[dd] = (nb, c)
    dates = sorted(looks)
    pre = [t for t in dates if (d - pd.Timestamp(t)).days >= 1]
    if len(pre) < 1 or not any(pd.Timestamp(t) >= d for t in dates):
        return dict(event_id=ev.event_id, status="too_few_looks", n_looks=len(dates)), None
    N = np.stack([looks[t][0] for t in dates])                     # looks x n x n
    base = np.nanmedian(np.stack([looks[t][0] for t in pre]), 0)
    dr = base[None] - N                                            # positive = darker than before
    out_ok = ~inside
    ref = np.array([np.nanmedian(dr[k][out_ok & ~np.isnan(dr[k])]) if (out_ok & ~np.isnan(dr[k])).sum() > 200 else np.nan for k in range(len(dates))])
    dr = dr - ref[:, None, None]
    days = np.array([(pd.Timestamp(t) - d).days for t in dates])   # relative to first alert day
    clear = ~np.isnan(dr)
    burnt = clear & (dr >= DROP)
    # first burnt look with persistence
    k_first = np.full((n, n), -1)
    for k in range(len(dates)):
        if days[k] < -1: continue
        nxt = np.full((n, n), True)
        later = clear[k + 1:]
        if len(later):
            idx = np.argmax(later, 0); has = later.any(0)
            v = np.take_along_axis(dr[k + 1:], idx[None], 0)[0]
            nxt = ~has | (v >= KEEP)
        m = burnt[k] & nxt & (k_first < 0)
        k_first[m] = k
    k_prev = np.full((n, n), -1)
    for k in range(len(dates)):
        m = clear[k] & (k < k_first) & ~burnt[k]
        k_prev[m] = k
    pix = inside & ~np.isnan(base)
    yy, xx = np.nonzero(pix)
    kf, kp = k_first[yy, xx], k_prev[yy, xx]
    dated = (kf >= 0) & (kp >= 0)
    lo = np.where(dated, days[np.maximum(kp, 0)], np.nan); hi = np.where(kf >= 0, days[np.maximum(kf, 0)], np.nan)
    px, py = x0 + (xx + 0.5) * RES, y1 - (yy + 0.5) * RES
    vv = V[(V.x > x0 - 400) & (V.x < x0 + n * RES + 400) & (V.y > y1 - n * RES - 400) & (V.y < y1 + 400)]
    vv = vv[(vv.day >= d - pd.Timedelta(days=1)) & (vv.day <= d + pd.Timedelta(days=30))]
    vday = np.full(len(px), np.nan)
    if len(vv):
        tree = cKDTree(np.c_[vv.x, vv.y]); vd = ((vv.day - d).dt.days).values
        for i, nb in enumerate(tree.query_ball_point(np.c_[px, py], 300.0)):
            if nb: vday[i] = vd[nb].min()
    P = pd.DataFrame(dict(event_id=ev.event_id, lo=lo, hi=hi, vday=vday))
    seen, dt_ = ~np.isnan(vday), dated
    both = seen & dt_
    agree = (vday[both] >= lo[both]) & (vday[both] <= hi[both] + 1) if both.any() else np.array([])
    w = hi - lo
    r = dict(event_id=ev.event_id, status="ok", scar_ha=ev.scar_ha, n_looks=len(dates), pixels=len(px),
             dated=round(dt_.mean(), 3), win_med=np.nanmedian(w[dt_]) if dt_.any() else np.nan,
             win_le3=round(((w <= 3) & dt_).mean(), 3), win_le5=round(((w <= 5) & dt_).mean(), 3),
             viirs_seen=round(seen.mean(), 3), unseen_dated_le3=round((~seen & dt_ & (w <= 3)).mean(), 3),
             agree=round(agree.mean(), 3) if len(agree) else np.nan, n_both=int(both.sum()),
             spread_days=np.nanpercentile(hi[dt_], 90) - np.nanpercentile(hi[dt_], 10) if dt_.sum() > 10 else np.nan)
    return r, P


def main():
    nev = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    H = W.history(); H = H[(H.status == "scar") & (H.scar_ha >= 20)]
    H = H[[d.year == 2025 and ((d.month, d.day) >= (2, 15)) and ((d.month, d.day) <= (6, 15)) for d in H.acq_date]]
    G = W.history_geoms()
    H = H[H.event_id.isin(G.index)].sample(nev, random_state=1)
    V = viirs(2025)
    rows, pix = [], []
    for i, ev in enumerate(H.itertuples()):
        try:
            r, P = one(ev, G[ev.event_id], V)
        except Exception as e:
            r, P = dict(event_id=ev.event_id, status="error", error=str(e)[:150]), None
        rows.append(r)
        if P is not None: pix.append(P)
        print(i, r, flush=True)
        if i % 10 == 9 or i == len(H) - 1:
            pd.DataFrame(rows).to_csv(OUT + "events.csv.tmp", index=False); os.replace(OUT + "events.csv.tmp", OUT + "events.csv")
    pd.concat(pix).to_parquet(OUT + "pixels.parquet.tmp", index=False); os.replace(OUT + "pixels.parquet.tmp", OUT + "pixels.parquet")
    E = pd.DataFrame(rows); ok = E[E.status == "ok"]
    print(E.status.value_counts().to_string()); print(ok.describe().T.to_string())


if __name__ == "__main__":
    main()
