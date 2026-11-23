"""Check the per-alert scar finder (alert_scar.py) on historic Ratapani alerts against
(a) the season scar maps (research thread labels) and (b) control points: the same dates, moved 3 km
to forest with no alert within 1.5 km and 15 days, where a "scar" is most likely a false alarm.

Usage: python eval_chip.py <n_events> <n_controls> <workers>   -> out/eval_chip.csv
"""
import os, sys, json, warnings
from multiprocessing import Pool
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import shape, Point, box
from scipy.spatial import cKDTree
from pyproj import Transformer

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = "/mnt/project-files/fire-alert-scars/out/"
TO = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def events(R):
    """One seed per fire event: alerts on the same day within 1 km collapse to the first one."""
    R = R.copy()
    R["x"], R["y"] = TO.transform(R.longitude.values, R.latitude.values)
    keep = []
    for _, g in R.groupby("acq_date"):
        t = cKDTree(g[["x", "y"]].values)
        taken = np.zeros(len(g), bool)
        for i in range(len(g)):
            if taken[i]:
                continue
            taken[t.query_ball_point(g[["x", "y"]].values[i], 1000)] = True
            keep.append(g.index[i])
    return R.loc[keep]


def controls(E, R, n, rng):
    aoi = gpd.read_file("/mnt/project-files/ratapani/ratapani_aoi.geojson").to_crs(32643).union_all()
    grid = gpd.read_file("/mnt/project-files/ratapani/grid_500m.geojson").to_crs(32643)
    forest = grid[grid.forest_frac >= 0.7]
    ft = cKDTree(np.c_[forest.geometry.centroid.x, forest.geometry.centroid.y])
    R = R.assign(t=pd.to_datetime(R.acq_date))
    R["x"], R["y"] = TO.transform(R.longitude.values, R.latitude.values)
    out = []
    for e in E.sample(frac=1, random_state=1).itertuples():
        th = rng.uniform(0, 2 * np.pi)
        x, y = e.x + 3000 * np.cos(th), e.y + 3000 * np.sin(th)
        if not aoi.contains(Point(x, y)) or ft.query([x, y])[0] > 250:
            continue
        t = pd.Timestamp(e.acq_date)
        near = R[(R.t - t).abs() <= pd.Timedelta("15D")]
        if len(near) and np.hypot(near.x - x, near.y - y).min() < 1500:
            continue
        lon, lat = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform(x, y)
        out.append(dict(kind="control", alert_id="C" + e.alert_id, latitude=lat, longitude=lon, acq_date=e.acq_date,
                        sensor="viirs-snpp", scan=1.0, track=1.0, status=None, scar_id=None, scar_ha=np.nan))
        if len(out) >= n:
            break
    return pd.DataFrame(out)


def run(row):
    import alert_scar
    try:
        r = alert_scar.alert_scar(row["latitude"], row["longitude"], row["acq_date"],
                                  "modis" if row["sensor"] == "modis" else "viirs", row["scan"], row["track"])
    except Exception as ex:
        r = dict(status="error", error=str(ex)[:200])
    g = r.pop("geometry", None)
    r["chip_geom"] = json.dumps(g) if g else None
    return {**{f"in_{k}": v for k, v in row.items()}, **{f"chip_{k}": v for k, v in r.items()}}


def main(n_ev, n_ctl, workers):
    R = pd.read_csv(OUT + "alert_scars.csv")
    R = R[R.in_aoi & R.status.isin(["scar", "no_scar_seen"]) & (R.season <= 2025)]
    E = events(R)
    rng = np.random.default_rng(0)
    # stratify: half events the season maps call scar, half they call no scar
    s = pd.concat([E[E.status == "scar"].sample(n_ev // 2, random_state=0),
                   E[E.status == "no_scar_seen"].sample(n_ev // 2, random_state=0)]).assign(kind="alert")
    C = controls(E, R, n_ctl, rng)
    cols = ["kind", "alert_id", "latitude", "longitude", "acq_date", "sensor", "scan", "track", "status", "scar_id", "scar_ha"]
    jobs = pd.concat([s[cols], C[cols]]).to_dict("records")
    with Pool(workers) as p:
        res = p.map(run, jobs, chunksize=1)
    D = pd.DataFrame(res)
    # overlap with the season-map scar, inside the chip
    S = gpd.read_file(OUT + "scars.geojson").to_crs(32643).set_index("scar_id")
    iou, cov = [], []
    for r in D.itertuples():
        if r.in_status == "scar" and r.chip_status == "scar" and r.in_scar_id in S.index:
            x, y = TO.transform(r.in_longitude, r.in_latitude)
            chip = box(x - 1500, y - 1500, x + 1500, y + 1500)
            a = S.loc[r.in_scar_id].geometry.intersection(chip)
            b = gpd.GeoSeries([shape(json.loads(r.chip_chip_geom))], crs=4326).to_crs(32643).iloc[0]
            iou.append(a.intersection(b).area / a.union(b).area)
            cov.append(a.intersection(b).area / a.area)
        else:
            iou.append(np.nan); cov.append(np.nan)
    D["iou_season_map"], D["share_of_map_scar_found"] = iou, cov
    D.to_csv(OUT + "eval_chip.csv", index=False)
    D["found"] = D.chip_status == "scar"
    print(D.groupby(["in_kind", "in_status"]).chip_status.value_counts().unstack(fill_value=0))
    print(D[D.chip_status.isin(["scar", "no_scar_seen"])].groupby(["in_kind", "in_status"]).found.mean().round(3))
    print(D[["iou_season_map", "share_of_map_scar_found"]].describe().round(2))


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
