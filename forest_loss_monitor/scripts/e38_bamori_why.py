"""Why does the rule miss the Bamori polygons? Annual DW trees, crops and shrub and annual NDVI at polygon points; which condition fails."""
from concurrent.futures import ThreadPoolExecutor

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

from common import *
from e32_enetra10m import dw_mean, ndvi_mean

YS = list(range(2017, 2026))
GT = ROOT / "ground_truth"


def run(part):
    p = ee.Projection(WKT)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x - 25, y - 25, x + 25, y + 25], p, False), dict(id=i)) for x, y, i in zip(part.x, part.y, part.id)])
    a = fc.geometry().bounds(100, "EPSG:4326")
    bands = []
    for y in YS:
        d = dw_mean(a, y, y)
        bands += [d.select("trees").rename(f"t{y}"), d.select("crops").rename(f"c{y}"), d.select("shrub_and_scrub").rename(f"s{y}"), ndvi_mean(a, y, y).rename(f"n{y}")]
    return [f["properties"] for f in ee.Image.cat(bands).reduceRegions(fc, ee.Reducer.mean(), scale=10, tileScale=8).getInfo()["features"]]


def main():
    init()
    g = gpd.read_file("E:/e_Netra/outputs/bamori_alphaearth_v2/FINAL_LABELS/bamori_validated_change_2017_2024.geojson").to_crs(PROJ4)
    pt = g.representative_point()
    d = pd.DataFrame(dict(id=g.poly_id, cls=g.change_type, x=pt.x, y=pt.y))
    parts = [d.iloc[i:i + 20] for i in range(0, len(d), 20)]
    with ThreadPoolExecutor(4) as ex:
        t = pd.DataFrame([r for x in ex.map(run, parts) for r in x])
    t = d.merge(t, on="id")
    t.to_csv(GT / "bamori_annual_dw.csv", index=False)
    mean = lambda ys, k: t[[f"{k}{y}" for y in ys]].mean(axis=1)
    t["e_t"], t["l_t"] = mean((2017, 2018, 2019), "t"), mean((2022, 2023, 2024), "t")
    t["e_n"], t["l_n"] = mean((2017, 2018, 2019), "n"), mean((2022, 2023, 2024), "n")
    t["forest"] = t.e_t >= .30
    t["tdrop"] = (t.e_t - t.l_t) >= .12
    t["ndrop"] = (t.e_n - t.l_n) >= .08
    t["woody"] = (mean((2017, 2018, 2019), "t") + mean((2017, 2018, 2019), "s")) >= .40
    t["crop_rise"] = (mean((2022, 2023, 2024), "c") - mean((2017, 2018, 2019), "c")) >= .15
    print(t.groupby("cls")[["forest", "tdrop", "ndrop", "woody", "crop_rise"]].mean().round(2).assign(n=t.groupby("cls").size()).to_string())
    print(t.groupby("cls")[["e_t", "l_t", "e_n", "l_n"]].median().round(2).to_string())
    for k, nm in (("t", "trees"), ("c", "crops"), ("n", "NDVI")):
        print(nm, t.groupby("cls")[[f"{k}{y}" for y in YS]].median().round(2).rename(columns=lambda c: c[1:]).to_string())
    # largest year-on-year style fall across all windows, to test if earlier change is the cause
    f = t[t.cls.isin(["forest_to_crop", "forest_to_bare"])]
    print("forest polygons: trees in 2017 >= .3:", int((f.t2017 >= .3).sum()), "of", len(f), "; median trees 2017", round(f.t2017.median(), 2))
    print("best split year for tree fall, forest polygons", f[[f"t{y}" for y in YS]].diff(axis=1).idxmin(axis=1).value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main()
