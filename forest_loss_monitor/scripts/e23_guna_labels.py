"""Copy the owner's Guna labels (read-only source: E:/e_Netra) into ground_truth/ and score the current map on them.
The blind reference is scored as in e_Netra: stratified weights w_h = A_h / n_h and a cluster bootstrap by beat.
Only the ratio of the stratum areas matters for precision and recall. Usage: e23_guna_labels.py build | score"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

from common import *
from zones import zone as zone_of

SRC = Path("E:/e_Netra/outputs")
GT = ROOT / "ground_truth"
A_H = {"flagged": 651.0, "background": 12887.0}    # r1_rescore_284_bgcomplete.log
N_BOOT = 2000


def to_grid(df):
    g = pd.read_json(WORK / "grid.json", typ="series")
    x, y = Transformer.from_crs("EPSG:4326", PROJ4, always_xy=True).transform(df.lon.values, df.lat.values)
    return df.assign(x=x, y=y, col=((x - g.x0) / RES).astype(int), row=((g.y1 - y) / RES).astype(int))


def polys(path, source, label_fn, year_col=None, cls_col=None):
    g = gpd.read_file(path).to_crs("EPSG:4326")
    p = g.to_crs(PROJ4).representative_point().to_crs("EPSG:4326")
    return pd.DataFrame(dict(source=source, label=label_fn(g), year=g[year_col] if year_col else np.nan, cls=g[cls_col] if cls_col else "",
                             lon=p.x, lat=p.y, beat=g.get("beat", ""), id=g.get("poly_id", g.index.astype(str))))


def build():
    GT.mkdir(exist_ok=True)
    r = pd.read_csv(SRC / "local_detector/reference_sample/reference_worksheet.csv")
    r = r.rename(columns={"is_forest_loss(1/0)": "label", "change_year": "year", "change_type": "cls", "point_id": "id"})
    a = r[r.label.notna()].assign(source="blind_reference")[["source", "label", "year", "cls", "lon", "lat", "beat", "id", "stratum"]]
    b = polys(SRC / "local_detector/felling_kit/felling_alerts_tiered.geojson", "felling_alert_verdict", lambda g: g.verdict.map({"TP": 1, "FP": 0}), "est_year")
    b = b[b.label.notna()]
    f = gpd.read_file(SRC / "local_detector/field_verification/field_labeled_polygons.geojson")
    print("field polygons label values", f.label.value_counts(dropna=False).to_dict(), f.label_source.value_counts(dropna=False).to_dict())
    c = polys(SRC / "local_detector/field_verification/field_labeled_polygons.geojson", "field_labeled", lambda g: pd.to_numeric(g.label, errors="coerce"), None, "ground_cause")
    c = c[c.label.notna()]
    d = polys(SRC / "bamori_alphaearth_v2/FINAL_LABELS/bamori_validated_change_2017_2024.geojson", "bamori_validated", lambda g: pd.Series(1, index=g.index), None, "change_type")
    df = pd.concat([a, b, c, d], ignore_index=True)
    df = to_grid(df)
    df["label"] = df.label.astype(int)
    df["gid"] = np.arange(1, len(df) + 1)
    df.to_csv(GT / "guna_labels.csv", index=False)
    print(df.groupby(["source", "label"]).size().unstack(fill_value=0).to_string())
    print(df[df.source == "bamori_validated"].cls.value_counts().to_dict())
    print("bbox", df[["lon", "lat"]].min().round(3).tolist(), df[["lon", "lat"]].max().round(3).tolist())
    with rasterio.open(WORK / "zone_beat.tif") as s:
        z = s.read(1)
    inside = df.row.between(0, z.shape[0] - 1) & df.col.between(0, z.shape[1] - 1)
    df["zone_id"] = 0
    df.loc[inside, "zone_id"] = z[df.row[inside], df.col[inside]]
    b_ = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    df["Division"] = df.zone_id.map(b_.Division)
    df["Range"] = df.zone_id.map(b_.Range)
    df["forest_zone"] = df.Division.map(lambda n: zone_of(n) if isinstance(n, str) else "outside_beats")
    df.to_csv(GT / "guna_labels.csv", index=False)
    print(df.groupby("source").forest_zone.value_counts().to_string())
    print(df.Division.value_counts(dropna=False).head(8).to_dict())
    print(df[df.source == "blind_reference"].Range.value_counts(dropna=False).to_dict())


def flag(df, arr, box):
    r, c = df.row.values, df.col.values
    if box == 0:
        return arr[r, c]
    out = np.zeros(len(df), bool)
    for dr in range(-box, box + 1):
        for dc in range(-box, box + 1):
            out |= arr[r + dr, c + dc]
    return out


def wpr(y, m, w):
    tp, fp, fn = (w * y * m).sum(), (w * (1 - y) * m).sum(), (w * y * (1 - m)).sum()
    return (tp / (tp + fp) if tp + fp else np.nan), (tp / (tp + fn) if tp + fn else np.nan)


def cluster_ci(d, col):
    rng = np.random.default_rng(1)
    beats = d.beat.unique()
    groups = {b: g for b, g in d.groupby("beat")}
    res = []
    for _ in range(N_BOOT):
        s = pd.concat([groups[b] for b in rng.choice(beats, len(beats))])
        res.append(wpr(s.label.values, s[col].values.astype(int), s._w.values))
    a = np.array(res)
    return np.nanpercentile(a, [2.5, 97.5], axis=0).round(3).T.tolist()


def score_reference(ref, col, name):
    p, r = wpr(ref.label.values, ref[col].values.astype(int), ref._w.values)
    ci = cluster_ci(ref, col)
    tp = int((ref.label & ref[col]).sum())
    print(f"{name:42s} precision {p:.2f} {ci[0]}  recall {r:.2f} {ci[1]}  raw tp {tp} detected {int(ref[col].sum())} of {len(ref)}, real {int(ref.label.sum())}")
    return dict(product=name, precision=round(p, 3), p_ci=ci[0], recall=round(r, 3), r_ci=ci[1])


def score():
    df = pd.read_csv(GT / "guna_labels.csv")
    c = np.load(WORK / "classified.npz")
    main = (c["cls"] == 1) | (c["cls"] == 2)
    anyc = c["cls"] > 0
    ref = df[df.source == "blind_reference"].copy()
    n = ref.stratum.value_counts()
    ref["_w"] = ref.stratum.map(lambda s: A_H[s] / n[s])
    print(ref.groupby(["stratum", "label"]).size().unstack().to_string())
    out = []
    for box, tag in ((0, "exact pixel"), (1, "3x3 box, like e_Netra's 50 m box")):
        ref["m"] = flag(ref, main, box)
        out.append(score_reference(ref, "m", f"Current map, {tag}"))
        ref["m2"] = flag(ref, anyc, box)
        out.append(score_reference(ref, "m2", f"Map + small patches, {tag}"))
    ref["m"] = flag(ref, main, 1)
    ref["yod"] = c["yod"][ref.row, ref.col]
    print("ref flagged by stratum", pd.crosstab(ref.stratum, [ref.label, ref.m]).to_string())
    pd.DataFrame(out).to_csv(GT / "map_vs_guna_reference.csv", index=False)
    o = df[df.source != "blind_reference"].copy()
    o["m"] = flag(o, main, 1)
    o["my"] = c["yod"][o.row, o.col]
    print(o.groupby(["source", "label"]).m.agg(["size", "sum", "mean"]).round(2).to_string())
    print(o[o.source == "bamori_validated"].groupby("cls").m.agg(["size", "sum", "mean"]).round(2).to_string())
    f = o[(o.source == "felling_alert_verdict") & o.year.notna()]
    print("felling by year", f.groupby("year").m.agg(["size", "sum"]).T.to_string())
    y = f[(f.m) & (f.label == 1) & (f.my > 0)]
    print("year agreement within 1 on felling hits", float((np.abs(y.my - y.year) <= 1).mean()) if len(y) else None, len(y))


if __name__ == "__main__":
    {"build": build, "score": score}[sys.argv[1]]()
