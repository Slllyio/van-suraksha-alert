"""Daily input tables for the PC's division models (pc_models/live_score.py), built without the PC (pc_models/CLOUD_PLAN.md).

Part 1, fire history: the definitions of van-suraksha-alert mp/scripts/mp_features.py and mp_seasonal.py, on the shared MP
500 m grid (EPSG:32643, X0 399000, Y1 2996000), computed over each division's bounding box so neighbourhood and distance
inputs also see fires just outside the division (as on the PC). Days are IST dates; inputs for issue day t use fires up to
and including day t. Detections are VIIRS type 0 (all three satellites) from the FIRMS archive (fire-alert-scars/alerts_mp)
and, in season, the app's own alerts. Checked against the PC's own tables once it sends them (CLOUD_PLAN.md item 3).
Weather, MODIS, HLS and the static table are later parts."""
import json
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

X0, Y1, S, W = 399000.0, 2996000.0, 500.0, 1829
ARCHIVE = Path("/mnt/project-files/fire-alert-scars/alerts_mp")          # FIRMS archive, Jan-Jun of each year
BACKFILL = Path(__file__).resolve().parent.parent / "data/viirs_backfill"
IST = pd.Timedelta(hours=5, minutes=30)


def archive_points(seasons):
    """VIIRS type-0 points of the given seasons from the FIRMS archive: col, row (mp_grid) and IST date."""
    from pyproj import Transformer
    fr = []
    for y in seasons:
        for sat in ("viirs-snpp", "viirs-jpss1", "viirs-noaa21"):
            f = ARCHIVE / f"{sat}_{y}.csv"
            if f.exists():
                fr.append(pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "type"]))
    for f in BACKFILL.glob("viirs_*.csv"):                                      # Oct-Dec from NASA granules (scripts/viirs_backfill_laads.py)
        fr.append(pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "type"]))
    v = pd.concat(fr, ignore_index=True)
    v = v[v.type == 0]
    x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform(v.longitude.values, v.latitude.values)
    utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, "h") + pd.to_timedelta(v.acq_time % 100, "m")
    return pd.DataFrame({"col": np.floor((x - X0) / S).astype(int), "row": np.floor((Y1 - y) / S).astype(int),
                         "d": (utc + IST).dt.normalize().values})


def fire_history(pts, cells, day, clim_seasons=None):
    """Fire-history inputs of one division for issue day `day` (date). cells: mp_grid cell ids of the division.
    pts: archive_points() (+ live alerts in the same form). Returns a DataFrame indexed like `cells`."""
    from scipy.ndimage import uniform_filter, distance_transform_edt
    cells = np.asarray(cells)
    row, col = cells // W, cells % W
    c0, r0 = col.min(), row.min()
    NI, NJ = col.max() - c0 + 1, row.max() - r0 + 1
    gi, gj = col - c0, row - r0
    t = pd.Timestamp(day)
    days = pd.date_range(t - pd.Timedelta(days=29), t, freq="D")                # 30 days up to t
    P = 10                                                                      # pad for the 5 km quiet box
    p = pts[(pts.col >= c0 - P) & (pts.col < c0 + NI + P) & (pts.row >= r0 - P) & (pts.row < r0 + NJ + P)]
    win = p[p.d.isin(days)]
    FRp = np.zeros((len(days), NI + 2 * P, NJ + 2 * P), bool)
    FRp[days.get_indexer(win.d), win.col - c0 + P, win.row - r0 + P] = True
    FR = FRp[:, P:-P, P:-P]
    fire = FR[:, gi, gj]
    out = {}
    for k in (1, 3, 7, 30):
        out[f"cell_d{k}"] = fire[-k:].sum(0)
    for w in (3, 7):
        for k in (1, 3, 7):
            out[f"nb{w}_d{k}"] = uniform_filter(FR[-k:].astype(np.float32).sum(0), w, mode="constant")[gi, gj] * w * w
    for k in (1, 3, 7):
        out[f"aoi_d{k}"] = np.full(len(cells), fire[-k:].sum())
    for k in (3, 7, 30):
        m = FR[-k:].any(0)
        out[f"fdist_d{k}"] = (np.minimum(distance_transform_edt(~m)[gi, gj] * 0.5, 30) if m.any() else np.full(len(cells), 30.0))
    # days since the cell last burned (capped 400), from the whole archive before t
    q = pts[(pts.d <= t) & ~pts.d.dt.month.isin([6, 7, 8, 9])]                  # the PC keeps Oct-May detections only
    last = q.assign(cell=q.row * W + q.col).groupby("cell").d.max()
    ls = pd.Series(cells).map(last)
    out["dsl"] = np.minimum((t - ls).dt.days.fillna(400).to_numpy(), 400)
    # fire climate of earlier seasons (Jan-May fire-days per season, cell and 7x7)
    if clim_seasons:
        cp = pts[pts.d.dt.year.isin(clim_seasons) & pts.d.dt.month.isin([1, 2, 3, 4, 5])
                 & (pts.col >= c0) & (pts.col < c0 + NI) & (pts.row >= r0) & (pts.row < r0 + NJ)].drop_duplicates(["col", "row", "d"])
        allc = np.zeros((NI, NJ), np.float32)
        np.add.at(allc, (cp.col - c0, cp.row - r0), 1)
        rc = np.zeros((NI, NJ), np.float32)                                     # as the PC: division squares only
        rc[gi, gj] = allc[gi, gj] / len(clim_seasons)
        out["clim_cell"] = rc[gi, gj]
        out["clim_nb7"] = uniform_filter(rc, 7, mode="constant")[gi, gj] * 49
    # burned early this season (mp_seasonal.py): fire-days 1 Oct .. min(t, 14 Feb), cell / 3x3 / 7x7, fires over the bbox
    s0 = pd.Timestamp(t.year - (0 if t.month >= 10 else 1), 10, 1)
    s1 = min(t, pd.Timestamp(s0.year + 1, 2, 14))
    ep = pts[(pts.d >= s0) & (pts.d <= s1) & (pts.col >= c0) & (pts.col < c0 + NI) & (pts.row >= r0)
             & (pts.row < r0 + NJ)].drop_duplicates(["col", "row", "d"])
    ef = np.zeros((NI, NJ), np.float32)
    np.add.at(ef, (ep.col - c0, ep.row - r0), 1)
    out["early_cell"] = ef[gi, gj]
    out["early_nb3"] = uniform_filter(ef, 3, mode="constant")[gi, gj] * 9
    out["early_nb7"] = uniform_filter(ef, 7, mode="constant")[gi, gj] * 49
    # quiet: no type-0 detection within +-10 cells on days t-6..t
    from scipy.ndimage import maximum_filter
    out["quiet"] = (~maximum_filter(FRp[-7:].any(0), size=21, mode="constant")[gi + P, gj + P]).astype(np.uint8)
    out["doy"] = np.full(len(cells), t.dayofyear)
    return pd.DataFrame({k: np.asarray(v, np.float32) if k != "quiet" else v for k, v in out.items()}, index=cells)
