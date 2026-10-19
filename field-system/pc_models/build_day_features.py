"""Standalone daily feature builder for the live division models (same definitions and float32 arithmetic as the PC
pipeline: mp/scripts/mp_features.py, mp_seasonal.py, mp_officer_eval.py, mp_forward.py). Needs numpy, pandas, scipy.

Per division and issue day it writes the table live_score.py scores: `cell`, `quiet` and every model feature.

Inputs (all on the MP 500 m grid, cell = row*1829 + col, EPSG:32643, X0 399000, Y1 2996000):
  static_inputs.parquet   cell, division, ae00-ae15, terrain, WorldCover, population, proximity, forest_frac
  static_gis_v1.parquet   cell + the 33 GIS columns
  fire cell-days          date (IST), row, col: one row per cell-day with >= 1 VIIRS type-0 detection, all satellites.
                          fire_celldays.parquet holds the history the models saw (2014 .. 2026-06); append new days with
                          make_fire_celldays.to_celldays(firms_rows). History from 2014-01-01 is needed: the burn
                          climatology uses every Jan-May since 2014, days-since-last-fire looks back 400 days.
  MODIS composites        per division: date (composite start), cell, ndvi, ndmi (MOD09A1) and date, cell, lst_k (MOD11A2),
                          covering at least 1 Sep of the previous year .. the issue day (mp/scripts/mp_ee.py pulls them)
  modis_clim.parquet      per division and cell: the as-of climatology (2013-12 .. 2024) per 14-day bin (doy // 14) for
                          ndvi, ndmi, lst_k (bins 3-10 cover the 13 Feb - 30 May issue days)
  mp_dry_<season>.npz     HLS 10-day dryness (cells, steps, X[step, cell, ndvi/ndmi/nbr x 1e4, clear %])
  weather                 the gfs_features.weather_table() row of the issue day
"""
import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter, distance_transform_edt, maximum_filter

NCOL = 1829
HIST0 = pd.Timestamp("2013-12-01")             # start of the pipeline's day index (fires start 2014-01-01)
MODIS_LAG, MODIS_FFILL = 9, 40                  # composite usable 9 days after its start date; carried up to 40 days
DRY = ["hls_ndvi", "hls_ndmi", "hls_nbr", "hls_clear", "hls_ndvi_d10", "hls_ndmi_d10", "hls_nbr_d10",
       "hls_ndvi_d30", "hls_ndmi_d30", "hls_nbr_d30"]


class Division:
    """grid geometry of one division: its cells and bounding box on the MP grid."""

    def __init__(self, name, cells):
        self.name = name
        self.cells = np.sort(np.asarray(cells))
        self.row, self.col = self.cells // NCOL, self.cells % NCOL
        self.r0, self.c0 = self.row.min(), self.col.min()
        self.NI, self.NJ = self.col.max() - self.c0 + 1, self.row.max() - self.r0 + 1   # raster axis0 = col, axis1 = row
        self.gi, self.gj = self.col - self.c0, self.row - self.r0
        self.n = len(self.cells)


def fire_raster(div, fires, d0, d1, pad=0):
    """bool [days, NI+2pad, NJ+2pad] of fire cell-days over the bbox (+pad cells), days d0..d1."""
    days = pd.date_range(d0, d1)
    c0, r0 = div.c0 - pad, div.r0 - pad
    NI, NJ = div.NI + 2 * pad, div.NJ + 2 * pad
    v = fires[(fires.date >= d0) & (fires.date <= d1) & (fires.col >= c0) & (fires.col < c0 + NI) &
              (fires.row >= r0) & (fires.row < r0 + NJ)]
    FR = np.zeros((len(days), NI, NJ), bool)
    FR[(v.date - d0).dt.days.to_numpy(), v.col - c0, v.row - r0] = True
    return days, FR


def fire_history(div, fires, t):
    """cell_d*, nb3/nb7_d*, aoi_d*, dsl, fdist_d*, clim_cell, clim_nb7 for issue day t (pipeline float32 arithmetic)."""
    days, FR = fire_raster(div, fires, HIST0, t)
    T = len(days) - 1                                            # index of t
    fire = FR[:, div.gi, div.gj]
    out = {}
    # neighbourhood sums: per-day uniform filter (float32), running float32 cumsum from the start of the history
    for w in (3, 7):
        c = np.zeros(div.n, np.float32); keep = {}
        for d in range(T + 1):
            if FR[d].any():
                c = c + uniform_filter(FR[d].astype(np.float32), size=w, mode="constant")[div.gi, div.gj]
            if d >= T - 7:
                keep[d] = c.copy()
        for k in (1, 3, 7):
            out[f"nb{w}_d{k}"] = (keep[T] - keep[T - k]) * w * w
    cf = fire.astype(np.float32)
    for k in (1, 3, 7, 30):
        out[f"cell_d{k}"] = cf[T - k + 1:T + 1].sum(0, dtype=np.float32)
    tot = fire.sum(1).astype(np.float32)
    for k in (1, 3, 7):
        out[f"aoi_d{k}"] = np.repeat(np.float32(tot[T - k + 1:T + 1].sum()), div.n)
    last = np.where(fire.any(0), T - np.argmax(fire[::-1], axis=0), -10_000)
    out["dsl"] = np.minimum(T - last, 400).astype(np.float32)
    for k in (3, 7, 30):
        win = FR[T - k + 1:T + 1].any(0)
        out[f"fdist_d{k}"] = (np.minimum(distance_transform_edt(~win)[div.gi, div.gj] * 0.5, 30).astype(np.float32)
                              if win.any() else np.full(div.n, 30, np.float32))
    prev = (days.year < t.year) & days.month.isin([1, 2, 3, 4, 5])
    nyrs = max(1, len(set(days.year[prev])))
    clim = fire[prev].sum(0) / nyrs
    rc = np.zeros((div.NI, div.NJ), np.float32); rc[div.gi, div.gj] = clim
    out["clim_cell"] = clim.astype(np.float32)
    out["clim_nb7"] = (uniform_filter(rc, 7, mode="constant")[div.gi, div.gj] * 49).astype(np.float32)
    return out


def early_burns(div, fires, t):
    """early_cell / early_nb3 / early_nb7: fire-days from 1 Oct to min(t, 14 Feb) of the season (Oct-May detections)."""
    a, b = pd.Timestamp(f"{t.year - 1}-10-01"), pd.Timestamp(f"{t.year}-02-14")
    days, EF = fire_raster(div, fires, a, b)
    kk = int(np.clip((t - a).days, 0, (b - a).days))
    layer = np.cumsum(EF, axis=0, dtype=np.float32)[kk]
    return {"early_cell": layer[div.gi, div.gj].astype(np.float32),
            "early_nb3": (uniform_filter(layer, 3, mode="constant") * 9)[div.gi, div.gj].astype(np.float32),
            "early_nb7": (uniform_filter(layer, 7, mode="constant") * 49)[div.gi, div.gj].astype(np.float32)}


def quiet(div, fires, t):
    """1 = no fire cell-day within +-10 cells (5 km box) on days t-6..t."""
    _, A = fire_raster(div, fires, t - pd.Timedelta(days=6), t, pad=10)
    busy = maximum_filter(A.any(0), size=21)
    return (~busy[div.gi + 10, div.gj + 10]).astype(np.uint8)


def modis_asof(comp, col, cells, d0, d1):
    """daily as-of value [days, cells] (float32): latest composite (usable from start + 9 days) within the last 40 days."""
    m = comp.dropna(subset=["date"]).assign(avail=lambda x: pd.to_datetime(x.date) + pd.Timedelta(days=MODIS_LAG))
    p = m.pivot(index="avail", columns="cell", values=col).reindex(columns=cells)
    # daily rows from well before d0, so the 40-row carry limit counts days exactly as on the pipeline's daily index
    days = pd.date_range(d0 - pd.Timedelta(days=MODIS_FFILL + 5), d1)
    out = p.reindex(p.index.union(days)).sort_index().ffill(limit=MODIS_FFILL).reindex(days).to_numpy(np.float32)
    return out[-((d1 - d0).days + 1):]


def modis(div, comp_sr, comp_lst, clim, t):
    """ndvi, ndmi, lst_k (as of t), their anomalies, ndmi_d16, ndvi/ndmi_chg16/32, ndvi_peak, leaf_loss."""
    d0 = t - pd.Timedelta(days=32)
    out = {}
    s = {c: modis_asof(comp_sr, c, div.cells, d0, t) for c in ("ndvi", "ndmi")}
    s["lst_k"] = modis_asof(comp_lst, "lst_k", div.cells, d0, t)
    b = t.dayofyear // 14
    cl = clim.set_index("cell").reindex(div.cells)
    for c in ("ndvi", "ndmi", "lst_k"):
        out[c] = s[c][-1]
        out[f"{c}_anom"] = (s[c][-1] - cl[f"{c}_b{b}"].to_numpy()).astype(np.float32)
    out["ndmi_d16"] = s["ndmi"][-1] - s["ndmi"][-17]
    for k in (16, 32):
        out[f"ndvi_chg{k}"] = s["ndvi"][-1] - s["ndvi"][-1 - k]
        out[f"ndmi_chg{k}"] = s["ndmi"][-1] - s["ndmi"][-1 - k]
    r = comp_sr.assign(date=pd.to_datetime(comp_sr.date))
    r = r[(r.date.dt.year == t.year - 1) & (r.date.dt.month >= 9)]
    pk = r.groupby("cell").ndvi.quantile(0.9).reindex(div.cells).to_numpy(np.float32)
    out["ndvi_peak"] = pk
    out["leaf_loss"] = 1 - out["ndvi"] / pk
    return out


def hls_dryness(div, npz, t):
    """hls_* from the season's 10-day dryness file (as mp_officer_eval.dryness / add_dry)."""
    dates = pd.to_datetime(npz["steps"]); pos = pd.Series(np.arange(len(npz["cells"])), index=npz["cells"])
    d = np.full((len(dates), div.n, 4), np.nan, np.float32)
    have = np.isin(div.cells, pos.index)
    if have.any():
        v = npz["X"][:, pos[div.cells[have]].to_numpy()].astype(np.float32)
        idx = v[..., :3]; idx[(idx < -10000) | (idx > 10000)] = np.nan
        v[..., 3][(v[..., 3] < 0) | (v[..., 3] > 100)] = np.nan
        v[..., :3] = idx / 10000.0
        d[:, have] = v
    k = int(np.searchsorted(dates.values, np.datetime64(t), side="right") - 1)
    vals = np.full((div.n, len(DRY)), np.nan, np.float32)
    if k >= 0:
        kk = max(k, 0)
        cur, p1, p3 = d[kk], d[max(kk - 1, 0)], d[max(kk - 3, 0)]
        vals[:, 0:4] = cur
        if kk - 1 >= 0:
            vals[:, 4:7] = cur[:, :3] - p1[:, :3]
        if kk - 3 >= 0:
            vals[:, 7:10] = cur[:, :3] - p3[:, :3]
    return {c: vals[:, j] for j, c in enumerate(DRY)}


def build(div, t, static, gis, fires, comp_sr, comp_lst, clim, npz, weather_row, features):
    """the full feature table of one division for issue day t, columns = ['cell', 'quiet'] + features."""
    t = pd.Timestamp(t)
    f = {"cell": div.cells, "quiet": quiet(div, fires, t), "doy": np.full(div.n, t.dayofyear, np.float32)}
    f.update(fire_history(div, fires, t)); f.update(early_burns(div, fires, t))
    f.update(modis(div, comp_sr, comp_lst, clim, t)); f.update(hls_dryness(div, npz, t))
    for c, v in weather_row.items():
        f[c] = np.repeat(np.float32(v), div.n)
    df = pd.DataFrame(f)
    st = static[static.division == div.name].drop(columns="division").set_index("cell").reindex(div.cells)
    g = gis.set_index("cell").reindex(div.cells)
    for c in st.columns:
        df[c] = st[c].to_numpy()
    for c in g.columns:
        if c not in ("row", "col"):
            df[c] = g[c].to_numpy(np.float32)
    df["spread_vpd"] = (df.nb7_d3 * df.vpd_max).astype(np.float32)
    slope = st["slope_deg_mean_f64"].to_numpy(np.float64) if "slope_deg_mean_f64" in st else df.get("slope_deg_mean", np.nan)
    df["spread_slope"] = (df.nb3_d3.to_numpy(np.float64) * slope).astype(np.float32)   # float64 product, as the pipeline
    df["dry_nearfire"] = (df.dry_days / (1 + df.fdist_d7)).astype(np.float32)
    return df.reindex(columns=["cell", "quiet"] + list(features))
