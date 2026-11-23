"""January test: does a per-pixel "normal year" baseline separate burns from leaf fall better?

In January teak sheds leaves, so NBR drops over deciduous crowns even without fire; the chip-median
correction in alert_scar.py removes the average drop but not its patchiness (deciduous vs green crowns).
Here, for each Jan-Feb alert (and each control point moved 3 km into forest, no alert within 1.5 km /
15 days), the same pre/post image dates are repeated in up to 4 other years; the per-pixel median of
those drops is the baseline. A pixel burned when its drop beats the chip AND its own normal drop.

Scores per point, core test (>= 0.5 ha connected, touching the 200 m disk, NIR also darkens):
  orig_015  as alert_scar.py in January: rel. drop >= 0.15
  orig_010  same with the Feb-Jun threshold 0.10
  base_010 / base_015 / base_007: drop minus baseline >= 0.10 / 0.15 / 0.07
Out: out/jan_baseline.csv
"""
import os, sys, json, datetime as dt
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from scipy.ndimage import label
import rasterio
from pyproj import Transformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alert_scar as A

R = "/mnt/project-files/fire-alert-scars/"
CRS, RES = A.CRS, A.RES


def chip(lat, lon):
    x, y = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(lon, lat)
    half = A.P["half_km"] * 1000
    x0, y1 = np.floor((x - half) / RES) * RES, np.ceil((y + half) / RES) * RES
    n = int(2 * half / RES)
    tr = rasterio.transform.from_origin(x0, y1, RES, RES)
    yy, xx = np.mgrid[0:n, 0:n]
    cx, cy = (x - x0) / RES - 0.5, (y1 - y) / RES - 0.5
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= (200 / RES) ** 2
    bbox = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform_bounds(x0, y1 - n * RES, x0 + n * RES, y1)
    return tr, n, disk, bbox


def best_look(bbox, tr, n, disk, t, win=8):
    """Clearest look over the disk within +-win days of t (nearest first)."""
    groups = {}
    rng = f"{t - dt.timedelta(win)}/{t + dt.timedelta(win)}"
    for col, s in (("sentinel-2-l2a", "s2"), ("landsat-c2-l2", "ls")):
        q = {"eo:cloud_cover": {"lt": 60}}
        if s == "ls":
            q["platform"] = {"in": ["landsat-8", "landsat-9"]}
        for it in A.catalog().search(collections=[col], bbox=bbox, datetime=rng, query=q).items():
            groups.setdefault((it.datetime.date(), s), []).append(it)
    for k in sorted(groups, key=lambda k: abs((k[0] - t).days)):
        nb, ni = A.look(groups[k], k[1], tr, n)
        if (~np.isnan(nb))[disk].mean() >= A.P["disk_clear"]:
            return nb, ni, k[0]
    return None


def hit(score, nir_ok, ok, disk, thr):
    m = ok & nir_ok & (score >= thr)
    lab, _ = label(m, structure=np.ones((3, 3)))
    sizes = np.bincount(lab.ravel())
    big = np.where(sizes * RES * RES / 1e4 >= A.P["min_ha"])[0]
    big = big[big > 0]
    h = np.intersect1d(np.unique(lab[disk]), big)
    return bool(len(h)), round(float(np.isin(lab, h).sum() * RES * RES / 1e4), 2)


def one(row):
    try:
        tr, n, disk, bbox = chip(row["latitude"], row["longitude"])
        t0, t1 = dt.date.fromisoformat(row["pre_date"]), dt.date.fromisoformat(row["post_date"])
        a, b = best_look(bbox, tr, n, disk, t0, 0), best_look(bbox, tr, n, disk, t1, 0)
        if not a or not b:
            return dict(row, err="no looks")
        ok = ~np.isnan(a[0]) & ~np.isnan(b[0])
        rdn, rdr = A.rel(a[0] - b[0], ok), A.rel(a[1] - b[1], ok)
        drops, yrs = [], []
        for dy in (-1, 1, -2, 2, -3, 3, -4, 4):
            Y = t0.year + dy
            if Y < 2017 or Y > 2026 or len(drops) >= 4:
                continue
            try:
                s0, s1 = t0.replace(year=Y), t1.replace(year=Y + (t1.year - t0.year))
            except ValueError:
                continue
            p, q = best_look(bbox, tr, n, disk, s0), best_look(bbox, tr, n, disk, s1)
            if p and q and 0 < (q[2] - p[2]).days <= 2 * (t1 - t0).days + 10:
                okY = ~np.isnan(p[0]) & ~np.isnan(q[0])
                drops.append(A.rel(p[0] - q[0], okY)); yrs.append(Y)
        out = dict(row, n_base_years=len(drops), base_years=",".join(map(str, yrs)))
        nir_ok = rdr >= A.P["dnir"]
        for name, thr in (("orig_015", 0.15), ("orig_010", 0.10)):
            out[name], out[name + "_ha"] = hit(rdn, nir_ok, ok, disk, thr)
        if len(drops) >= 2:
            B = np.nanmedian(np.stack(drops), axis=0)
            an = rdn - np.where(np.isnan(B), 0, B)
            for name, thr in (("base_015", 0.15), ("base_010", 0.10), ("base_007", 0.07)):
                out[name], out[name + "_ha"] = hit(an, nir_ok, ok, disk, thr)
            out["base_drop_disk"] = round(float(np.nanmedian(B[disk])), 3)
        out["rdn_disk_p90"] = round(float(np.nanpercentile(rdn[disk], 90)), 3)
        return out
    except Exception as ex:
        return dict(row, err=str(ex)[:150])


if __name__ == "__main__":
    import eval_chip
    L = pd.read_csv(R + "alert_scar_lookup.csv")
    L = L[L.scar_found.isin(["yes", "faint", "none_visible"]) & L.pre_date.notna() & L.post_date.notna()]
    L["m"] = pd.to_datetime(L.acq_date).dt.month
    J = L[(L.m == 1) & (L.acq_date < "2026-01-01")].drop_duplicates("event_id")
    rng = np.random.default_rng(7)
    S = pd.concat([g.sample(min(len(g), 45), random_state=7) for _, g in J.groupby("scar_found")])
    S = S.assign(kind="alert")
    # controls: same dates, moved 3 km into forest; they borrow the alert's image pair
    Rall = L.rename(columns={"alert_id": "alert_id"})
    Rall["x"], Rall["y"] = eval_chip.TO.transform(Rall.longitude.values, Rall.latitude.values)
    Jx = J.copy(); Jx["x"], Jx["y"] = eval_chip.TO.transform(Jx.longitude.values, Jx.latitude.values)
    C = eval_chip.controls(Jx, Rall, 90, rng)
    C = C.merge(Jx[["alert_id", "pre_date", "post_date"]].assign(alert_id=lambda d: "C" + d.alert_id), on="alert_id")
    C["scar_found"] = "control"
    rows = pd.concat([S[["alert_id", "event_id", "latitude", "longitude", "acq_date", "scar_found", "pre_date", "post_date", "kind"]],
                      C[["alert_id", "latitude", "longitude", "acq_date", "scar_found", "pre_date", "post_date", "kind"]]], ignore_index=True)
    print(rows.scar_found.value_counts().to_dict(), flush=True)
    with ProcessPoolExecutor(6) as ex:
        out = pd.DataFrame(list(ex.map(one, rows.to_dict("records"))))
    out.to_csv(R + "out/jan_baseline.csv", index=False)
    v = out[out.get("n_base_years", 0).fillna(0) >= 2]
    print(len(out), "points,", len(v), "with a baseline")
    print(v.groupby("scar_found")[["orig_015", "orig_010", "base_015", "base_010", "base_007"]].mean().round(3))
