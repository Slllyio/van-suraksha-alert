"""Head-to-head scoring of the survey-calibrated state models (A Prithvi, B AlphaEarth MLP, C GBM on HLS) against the current rule (v1 tree loss + new-crop map).
Change codes on the 10 m Guna grid: 1 forest -> open (tree loss), 2 forest -> farm (tree loss, now cropped), 3 non-forest -> farm (new farm).
State-model rule (fixed before scoring): forest in 2015 (B: 2017 proxy) and non-forest in >= 2 of 2023-25 = loss; farm in >= 2 of 2023-25 and not farm in 2015 = farm;
loss year = first year from 2017 that is non-forest and stays non-forest the next year (2025 alone if last). Patches >= 2 px at 30 m (0.18 ha); 0.5 ha view also kept.
Label sets: 284 reference points (area-weighted, any loss), 222 Bamori polygons, 155 land-cover polygons (interior), 51 fellings (recall, year),
304-spot blind sample (stratified weights), Bamori and Fatehgarh range rasters (tree loss vs their confirmed loss). Writes outputs/final/survey_model/. Usage: e110_survey_score.py"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely import wkt

from common import *
from e23_guna_labels import A_H, wpr
from e48_tests import GT
from e69_rule_sweep import boot
from e97_guna_eval import ENETRA, GD, SH, box_codes, grid, rd
from e102_guna_sample import SD as SAMPLE, newcrop
from e106_survey_data import SM

OD = OUT / "final" / "survey_model"
MIN30, VIEW30 = 2, 6
LATE = (2023, 2024, 2025)
YS = list(range(2017, 2026))


def from_states(st):
    s15 = st["s2015"]
    late = np.stack([st[f"s{y}"] for y in LATE])
    nonf = ((late != 1) & (late > 0)).sum(0) >= 2
    farm = (late == 3).sum(0) >= 2
    loss = (s15 == 1) & nonf
    code = np.where(loss & farm, 2, np.where(loss, 1, np.where((s15 > 0) & (s15 != 3) & farm, 3, 0))).astype("uint8")
    S = np.stack([st[f"s{y}"] for y in YS])
    nf = (S != 1) & (S > 0)
    run = nf & np.concatenate([nf[1:], np.ones_like(nf[:1])], 0)
    first = np.where(run.any(0), np.array(YS)[run.argmax(0)], 0)
    yr = np.where(code > 0, first, 0).astype("int16")
    return code, yr


def sieve(code, n):
    lab, k = ndimage.label(code > 0, structure=np.ones((3, 3), bool))
    size = np.bincount(lab.ravel())
    keep = size[lab] >= n
    keep[lab == 0] = False
    return np.where(keep, code, 0).astype("uint8")


def up(a, shp):
    return np.repeat(np.repeat(a, 3, 0), 3, 1)[:shp[0], :shp[1]]


def current_rule(tr, shp):
    a = rd("guna_default")
    tree = (a == 1) | (a == 2)
    nc = newcrop(tr, shp)
    code = np.where(tree & nc, 2, np.where(tree, 1, np.where(nc, 3, 0))).astype("uint8")
    return code, rd("guna_year")


def score(name, code, yr, tr, shp, ctx):
    res = []
    det = code > 0
    tree = (code == 1) | (code == 2)
    # 284 reference points
    g = ctx["g"]
    rows = []
    for q in g.itertuples():
        b = box_codes(code, tr, q.x, q.y)
        if b is None:
            continue
        yy = box_codes(yr, tr, q.x, q.y)
        rows.append(dict(pid=q.pid, source=q.source, label=q.label, stratum=q.stratum, beat=q.beat, true_year=q.year, flag=int((b > 0).any()),
                         map_year=int(np.median(yy[b > 0])) if (b > 0).any() else 0))
    d = pd.DataFrame(rows)
    ref = d[d.source == "blind_reference"].copy()
    n_ = ref.stratum.value_counts()
    ref["w"] = ref.stratum.map(lambda s: A_H[s] / n_[s])
    p, r = wpr(ref.label.values, ref.flag.values, ref.w.values)
    ci = boot(ref.label.values.astype(float), ref.w.values, ref.flag.values.astype(bool), ref.beat.values)
    res.append(dict(label_set="284 reference points (area-weighted, any loss)", metric="precision", value=round(p, 3), range=ci[0]))
    res.append(dict(label_set="284 reference points (area-weighted, any loss)", metric="recall", value=round(r, 3), range=ci[1]))
    fe = d[(d.source == "felling_alert_verdict") & (d.label == 1)]
    e = (fe.map_year - fe.true_year)[(fe.flag == 1) & fe.true_year.notna() & (fe.map_year > 0)]
    res.append(dict(label_set="51 dated fellings", metric="recall", value=round(float(fe.flag.mean()), 3)))
    res.append(dict(label_set="51 dated fellings", metric="year exact / within 1", value=f"{int((e == 0).sum())} / {int((e.abs() <= 1).sum())} of {len(e)}"))
    bm = d[d.source == "bamori_validated"]
    res.append(dict(label_set="222 Bamori polygons (centre 5x5)", metric="recall", value=round(float(bm.flag.mean()), 3)))
    # polygons by area
    for nm, polys, key in (("222 Bamori polygons", ctx["bp"], None), ("155 land-cover polygons, interior", ctx["lc"], "cls")):
        o = []
        for gg, k in zip(polys.geometry, polys[key] if key else [None] * len(polys)):
            m = rasterize([(gg, 1)], out_shape=shp, transform=tr, fill=0, dtype="uint8").astype(bool) if gg is not None and not gg.is_empty else None
            if m is None or not m.any():
                continue
            o.append(dict(k=k, flagged=bool((det & m).any()), share=float((det & m).sum() / m.sum())))
        o = pd.DataFrame(o)
        if key is None:
            res.append(dict(label_set=nm, metric="polygons flagged / area flagged", value=f"{o.flagged.mean():.3f} / {o.share.mean():.3f}"))
        else:
            for grp, ks in (("crop (c, c2)", ("c", "c2")), ("forest (f, df)", ("f", "df")), ("bare (b)", ("b",))):
                q = o[o.k.isin(ks)]
                res.append(dict(label_set=nm, metric=f"{grp}: polygons flagged / area flagged", value=f"{q.flagged.mean():.3f} / {q.share.mean():.3f}"))
    # 304-spot blind sample, stratified weights
    sp = ctx["sp"]
    sp = sp.assign(flag=[int((code[r - 1:r + 2, c - 1:c + 2] > 0).any()) for r, c in zip(sp.row, sp.col)], tflag=[int(((code[r - 1:r + 2, c - 1:c + 2] == 1) | (code[r - 1:r + 2, c - 1:c + 2] == 2)).any()) for r, c in zip(sp.row, sp.col)])
    w = sp.w.values
    for nm, f, y in (("any loss", sp.flag.values, sp.loss.values), ("tree loss (my clearing labels)", sp.tflag.values, sp.tree.values)):
        prec = float((w * f * y).sum() / max((w * f).sum(), 1e-9))
        rec = float((w * f * y).sum() / max((w * y).sum(), 1e-9))
        res.append(dict(label_set="304-spot blind sample (stratified weights)", metric=f"{nm}: precision / recall", value=f"{prec:.3f} / {rec:.3f}"))
    # range rasters: tree loss vs their confirmed loss
    for rg, ly in ctx["ranges"].items():
        inr = ctx["rmask"][rg]
        th = inr & (ly > 0) & (ly <= 2024)
        ours = inr & tree
        res.append(dict(label_set=f"{rg} range raster (their confirmed 2019-24)", metric="tree loss: agreement (ours in theirs) / recall",
                        value=f"{(ours & (inr & (ly > 0))).sum() / max(ours.sum(), 1):.3f} / {(ours & th).sum() / max(th.sum(), 1):.3f}"))
    # Guna totals by range (map area)
    bz = ctx["beat_range"]
    t = pd.DataFrame(dict(rg=bz[ctx["gm"]], code=code[ctx["gm"]]))
    tot = t[t.code > 0].groupby(["rg", "code"]).size().unstack(fill_value=0).reindex(columns=[1, 2, 3], fill_value=0) * .01
    tot.columns = ["forest_to_open_ha", "forest_to_farm_ha", "nonforest_to_farm_ha"]
    tot["tree_loss_ha"] = tot.forest_to_open_ha + tot.forest_to_farm_ha
    tot["new_farm_ha"] = tot.forest_to_farm_ha + tot.nonforest_to_farm_ha
    tot["combined_ha"] = tot.tree_loss_ha + tot.nonforest_to_farm_ha
    tot.loc["Guna"] = tot.sum()
    tot = tot.round(0).assign(method=name)
    return pd.DataFrame(res).assign(method=name), tot


def context(tr, shp):
    g = pd.read_csv(GT / "guna_labels.csv").assign(pid=lambda d: d.gid + 500000)
    bp = gpd.read_file(f"{ENETRA}/bamori_alphaearth_v2/FINAL_LABELS/bamori_validated_change_2017_2024.geojson").to_crs(PROJ4)
    lc = pd.DataFrame(json.load(open(SH / "bamori-polygons" / "polys.json")))
    lc = gpd.GeoDataFrame(lc, geometry=lc.wkt.map(wkt.loads), crs=PROJ4)
    lc["geometry"] = lc.geometry.buffer(-25)
    fr = pd.read_csv(SAMPLE / "sample_frame.csv")
    sp = pd.read_csv(SAMPLE / "sample_points.csv").merge(pd.read_csv(SAMPLE / "labels.csv"), on="sid")
    sp["tree"] = ((sp.loss == 1) & (sp.kind == "clear")).astype(int)
    nh = sp.stratum.value_counts()
    sp["w"] = sp.stratum.map(lambda h: fr.set_index("stratum").ha[h] / nh[h])
    beat = np.load(GD / "guna_beat.npy")
    lk = pd.read_csv(OUT / "beat_lookup.csv").set_index("zone_id")
    gm = beat > 0
    br = np.full(beat.shape, "", object)
    br[gm] = pd.Series(beat[gm]).map(lk.Range).values
    ranges, rmask = {}, {}
    base = WORK.parent / "ground_truth" / "shared"
    for rg, f in (("Bamori", base / "bamori-polygons" / "range" / "bamori_loss_year.tif"), ("Fatehgarh", base / "fatehgarh" / "fatehgarh_loss_year.tif")):
        out = np.zeros(shp, "int16")
        with rasterio.open(f) as s:
            reproject(s.read(1).astype("int16"), out, src_transform=s.transform, src_crs=s.crs, dst_transform=tr, dst_crs=PROJ4, resampling=Resampling.nearest)
        ranges[rg] = out
        rmask[rg] = np.isin(beat, lk[(lk.Division == "Guna") & (lk.Range == rg)].index.values)
    return dict(g=g, bp=bp, lc=lc, sp=sp, beat_range=br, gm=gm, ranges=ranges, rmask=rmask)


def main():
    OD.mkdir(parents=True, exist_ok=True)
    tr, shp = grid()
    ctx = context(tr, shp)
    out, tots = [], []
    methods = [("current rule (v1 tree loss + new-crop map)", *current_rule(tr, shp))]
    for k, nm in (("A", "A Prithvi 300M, last 4 blocks fine-tuned (bilinear fixed)"), ("Aa", "a Prithvi frozen + linear head"), ("Ab", "b Prithvi fine-tune, fixed recipe"),
                  ("Ac", "c Prithvi fine-tune, cleaned labels"), ("Ae", "e Prithvi frozen token probe"), ("B", "B AlphaEarth MLP (2017 as 2015 proxy)"),
                  ("C", "C LightGBM on HLS"), ("Cc", "d LightGBM on cleaned labels")):
        f = SM / f"states_{k}.npz"
        if not f.exists():
            print("missing", f.name)
            continue
        code, yr = from_states(dict(np.load(f)))
        code = sieve(code, MIN30)
        methods.append((nm, up(code, shp), up(yr, shp)))
        methods.append((nm + ", 0.5 ha view", up(sieve(code, VIEW30), shp), up(yr, shp)))
    for nm, code, yr in methods:
        r, t = score(nm, code, yr, tr, shp, ctx)
        out.append(r)
        tots.append(t)
        print("scored", nm, flush=True)
    R = pd.concat(out)
    W_ = R.pivot_table(index=["label_set", "metric"], columns="method", values="value", aggfunc="first", sort=False)
    W_.to_csv(OD / "head_to_head.csv")
    T_ = pd.concat(tots)
    T_.to_csv(OD / "guna_totals_by_method.csv")
    pd.set_option("display.width", 300)
    pd.set_option("display.max_colwidth", 30)
    print(W_.to_string())
    print(T_.loc["Guna"].to_string())


if __name__ == "__main__":
    main()
