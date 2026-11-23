"""Held-out check of split_scars: split again WITHOUT fire-pixel seeds, then ask where Sentinel-2/Landsat
fire pixels inside the original scar end up. Pixels burning on the event's own day (or next) should stay;
pixels burning 2+ days apart from it are another fire's front and should be cut."""
import json, numpy as np, pandas as pd
from shapely.geometry import shape, Point
from shapely.ops import transform
from concurrent.futures import ProcessPoolExecutor
import os; os.environ['SPLIT_NO_AF'] = '1'   # no fire-pixel seeds: held out
import split_scars as S
AF = pd.read_csv(S.R + "out/af/af_pixels_clean.csv", usecols=["lon", "lat", "date"])
AF["x"], AF["y"] = S.TO.transform(AF.lon.values, AF.lat.values); AF["d"] = pd.to_datetime(AF.date)
def one(r):
    o = S.one(r)
    if not o or not o["geometry_split"]:
        return []
    r = pd.Series(r)
    g0 = S.tr(r.geometry); g1 = S.tr(o["geometry_split"])
    x0, y0, x1, y1 = g0.bounds
    f = AF[(AF.d >= pd.Timestamp(r.pre_date)) & (AF.d <= pd.Timestamp(r.post_date)) & AF.x.between(x0, x1) & AF.y.between(y0, y1)]
    out = []
    own = S.L[S.L.event_id == r.event_id][["x", "y"]].values
    for p in f.itertuples():
        pt = Point(p.x, p.y)
        if g0.contains(pt):
            out.append(dict(event_id=r.event_id, lag=(p.d - pd.Timestamp(r.date)).days, kept=g1.buffer(20).contains(pt),
                            d_own=float(np.hypot(*(own - [p.x, p.y]).T).min()), area0=g0.area / 1e4))
    return out
if __name__ == "__main__":
    with ProcessPoolExecutor(8) as ex:
        D = pd.DataFrame([x for xs in ex.map(one, S.E.to_dict("records"), chunksize=50) for x in xs])
    D["when"] = np.where(D.lag.between(0, 1) & (D.d_own <= 1000), "own fire: same day/next, <=1 km",
                np.where(D.lag.between(0, 1), "same day, >1 km (other fire)", "2+ days apart (other fire)"))
    print(D.groupby("when").kept.agg(["size", "mean"]).round(3))
    print("by event (share of events):", D.groupby(["when", "event_id"]).kept.mean().groupby("when").mean().round(3).to_dict())
    D.to_csv(S.R + "out/eval_split_af.csv", index=False)
