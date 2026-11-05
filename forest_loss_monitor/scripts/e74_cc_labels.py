"""Change/no-change labels for Guna, from the owner's e_Netra files, read-only. Adds what earlier training left out: the 112 Bamori false alarms the owner marked, the recall kit,
the recent-clearing worksheet, and random Guna forest points that are assumed stable and never scored. Writes ground_truth/guna_cc_labels.csv. Usage: e74_cc_labels.py"""
import sys
sys.path.insert(0, "E:/FIRE/forest_loss_monitor/scripts")
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

from common import *

SRC = Path("E:/e_Netra/outputs")
GT = ROOT / "ground_truth"
LD = SRC / "local_detector"
BV = SRC / "bamori_alphaearth_v2"
LOSS_CLS = {"forest_to_crop", "forest_to_bare", "shrub_to_crop", "unspecified"}      # bare_to_crop is not forest loss: kept in the table, left out of training
N_RANDOM = 400
SEED = 20261106


def rep(path, **kw):
    g = gpd.read_file(path).to_crs(PROJ4)
    p = g.representative_point()
    return g.assign(x=p.x, y=p.y, ha=g.area / 1e4, **kw)


def main():
    t = Transformer.from_crs("EPSG:4326", PROJ4, always_xy=True)
    old = pd.read_csv(GT / "guna_labels.csv")
    r = old[old.source == "blind_reference"]
    rows = [pd.DataFrame(dict(set="reference", id=r.id, y=r.label, cls=r.cls.fillna(""), stratum=r.stratum, year=r.year, x=r.x, y_m=r.y_1 if "y_1" in r else r["y"], beat=r.beat, ha=np.nan))]
    f = rep(LD / "felling_kit/felling_alerts_tiered.geojson")
    f = f[f.verdict.isin(["TP", "FP"])]
    rows.append(pd.DataFrame(dict(set="felling", id=f.poly_id, y=(f.verdict == "TP").astype(int), cls="felling", stratum="", year=f.est_year, x=f.x, y_m=f.y, beat=f.beat, ha=f.ha)))
    k = rep(LD / "felling_recall_kit/recall_kit.geojson")
    w = pd.read_csv(LD / "felling_recall_kit/recall_kit_worksheet.csv").rename(columns={"my_verdict(TP/FP)": "v"})
    w = w[w.v.astype(str).str.strip().isin(["0", "1"])]
    k = k.drop(columns=[c for c in ("beat", "est_year", "area_ha") if c in k]).merge(w, on="poly_id")
    rows.append(pd.DataFrame(dict(set="recall_kit", id=k.poly_id, y=k.v.astype(int), cls="felling", stratum="", year=k.est_year, x=k.x, y_m=k.y, beat=k.beat, ha=k.ha)))
    n = pd.read_csv(LD / "reference_sample/recent_new_worksheet.csv")
    x, y = t.transform(n.lon.values, n.lat.values)
    rows.append(pd.DataFrame(dict(set="recent_new", id=n.poly_id, y=n["is_forest_loss(1/0)"].astype(int), cls="recent", stratum="", year=2024, x=x, y_m=y, beat=n.beat, ha=n.area_ha)))
    b = rep(BV / "FINAL_LABELS/bamori_validated_change_2017_2024.geojson")
    rows.append(pd.DataFrame(dict(set="bamori_tp", id=b.poly_id, y=np.where(b.change_type.isin(LOSS_CLS), 1, -1), cls=b.change_type, stratum="", year=np.nan, x=b.x, y_m=b.y, beat=b.beat, ha=b.ha)))
    v = pd.read_csv(BV / "validation/bamori_change_validation.csv")
    fp = rep(BV / "validation/bamori_change_polygons.geojson").drop(columns="beat").merge(v[v.my_verdict == 0][["poly_id", "beat", "my_notes"]], on="poly_id")
    rows.append(pd.DataFrame(dict(set="bamori_fp", id=fp.poly_id, y=0, cls=fp.my_notes.fillna("false alarm"), stratum="", year=np.nan, x=fp.x, y_m=fp.y, beat=fp.beat, ha=fp.ha)))
    d = pd.concat(rows, ignore_index=True)
    lk = pd.read_csv(OUT / "beat_lookup.csv")
    with rasterio.open(WORK / "zone_beat.tif") as s:
        z, tr = s.read(1), s.transform
    rr, cc = np.nonzero(np.isin(z, lk[lk.Division == "Guna"].zone_id.values))
    xs, ys = tr.c + (cc + .5) * tr.a, tr.f + (rr + .5) * tr.e
    pos = d[d.y != 0][["x", "y_m"]].values
    rng = np.random.default_rng(SEED)
    keep = []
    for i in rng.permutation(len(rr)):
        if ((pos - [xs[i], ys[i]]) ** 2).sum(axis=1).min() >= 300 ** 2:
            keep.append(i)
        if len(keep) == N_RANDOM:
            break
    bl = lk.set_index("zone_id").Beat
    d = pd.concat([d, pd.DataFrame(dict(set="random", id=[f"RND_{i:03d}" for i in range(N_RANDOM)], y=0, cls="assumed stable", stratum="", year=np.nan, x=xs[keep], y_m=ys[keep], beat=bl.reindex(z[rr[keep], cc[keep]]).values, ha=np.nan))], ignore_index=True)
    d.insert(0, "cid", np.arange(len(d)))
    d.to_csv(GT / "guna_cc_labels.csv", index=False)
    print(d.groupby(["set", "y"]).size().unstack(fill_value=0).to_string())
    print(d.beat.nunique(), "beats; span km", round((d.x.max() - d.x.min()) / 1e3), round((d.y_m.max() - d.y_m.min()) / 1e3))


if __name__ == "__main__":
    main()
