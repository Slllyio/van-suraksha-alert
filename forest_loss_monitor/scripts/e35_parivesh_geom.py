"""Turn Parivesh KMLs into labelled geometries. A report's map links say what each KML shows, so compensatory afforestation land is kept out of the loss labels.
Earliest possible loss year = year of the Stage-II approval (Stage-I if that is all there is). Approval is not proof of felling."""
from defusedxml import ElementTree as ET
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from common import *
from e29_parivesh_kml import GT, KML

MP_BOX = (74.0, 21.0, 83.0, 27.0)


def coords(s):
    out = []
    for t in s.split():
        v = t.split(",")
        if len(v) >= 2:
            try:
                out.append((float(v[0]), float(v[1])))
            except ValueError:
                pass
    return out


def parse(path):
    """Polygons, lines and points in lon/lat from one KML or KMZ; empty on bad files."""
    try:
        raw = zipfile.ZipFile(path).read([n for n in zipfile.ZipFile(path).namelist() if n.lower().endswith(".kml")][0]) if str(path).lower().endswith("kmz") else open(path, "rb").read()
        root = ET.fromstring(raw)
    except Exception:
        return []
    geoms = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("Polygon", "LineString", "Point"):
            continue
        c = None
        for x in el.iter():
            if x.tag.split("}")[-1] == "coordinates" and x.text:
                c = coords(x.text)
                break
        if not c:
            continue
        try:
            g = Polygon(c) if tag == "Polygon" and len(c) >= 4 else LineString(c) if tag == "LineString" and len(c) >= 2 else Point(c[0]) if tag == "Point" else None
        except Exception:
            g = None
        if g is not None and not g.is_empty:
            geoms.append(g.buffer(0) if g.geom_type == "Polygon" else g)
    return geoms


def build():
    t = pd.read_csv(GT / "parivesh_kml_manifest.csv")
    print("files by type", t.type.value_counts(dropna=False).to_dict(), "saved as valid KML", int(t.ok.sum()))
    d = pd.read_csv(GT / "parivesh_mp_proposals.csv").rename(columns={"Proposal No.": "proposal"})
    ds = d["Related Documents"].astype(str)
    d["stage2"] = pd.to_numeric(ds.str.extract(r"Stage-II:\s*\d\d/\d\d/(\d{4})")[0], errors="coerce")
    d["stage1"] = pd.to_numeric(ds.str.extract(r"Stage-I\s*:\s*\d\d/\d\d/(\d{4})")[0], errors="coerce")
    d["earliest"] = d.stage2.fillna(d.stage1)
    rows = []
    for r in t[t.ok == 1].itertuples():
        path = KML / r.saved
        is_ca = False     # afforestation patches (type cak) were never downloaded
        for g in (x for x in parse(path) if not x.is_empty):
            rp = g.representative_point()
            if rp.is_empty:
                continue
            lon, lat = rp.x, rp.y
            if not (MP_BOX[0] <= lon <= MP_BOX[2] and MP_BOX[1] <= lat <= MP_BOX[3]):
                continue
            rows.append(dict(proposal=r.proposal, file=path.name, kml_type=r.type, is_ca=is_ca, geom_type=g.geom_type, geometry=g))
    gg = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    print("parsed geometries", len(gg), gg.geom_type.value_counts().to_dict(), "CA share", round(float(gg.is_ca.mean()), 3))
    m = gg[~gg.is_ca]
    per = m.groupby("proposal").geom_type.agg(lambda s: "polygon" if "Polygon" in set(s) else "line" if "LineString" in set(s) else "point")
    d["geom"] = d.proposal.map(per).fillna("none")
    print("proposals", len(d), "usable location", d.geom.value_counts().to_dict())
    print("with earliest year 2018-2025", int(d.earliest.between(2018, 2025).sum()), "and a polygon", int((d.earliest.between(2018, 2025) & (d.geom == "polygon")).sum()), "and a polygon or line", int((d.earliest.between(2018, 2025) & d.geom.isin(["polygon", "line"])).sum()))
    d.drop(columns=["page", "View Report of Part-I", "View Report of PartII", "View TimeLine Details"], errors="ignore").to_csv(GT / "parivesh_mp_proposals_located.csv", index=False)
    u = m[m.geom_type == "Polygon"].merge(d[["proposal", "Proposal Name", "Category", "Area (ha.)", "earliest"]], on="proposal")
    u = u.to_crs(PROJ4)
    u["poly_ha"] = u.area / 1e4
    prop = u.dissolve("proposal", aggfunc={"Category": "first", "Area (ha.)": "first", "earliest": "first", "Proposal Name": "first", "poly_ha": "sum"})
    prop["kml_ha"] = prop.area / 1e4
    prop["approved_ha"] = pd.to_numeric(prop["Area (ha.)"], errors="coerce")
    prop["ratio"] = prop.kml_ha / prop.approved_ha
    prop.to_crs("EPSG:4326").reset_index().to_file(GT / "parivesh_polygons.gpkg", driver="GPKG")
    print("polygon proposals", len(prop), "ratio KML/approved quantiles", prop.ratio.quantile([.1, .25, .5, .75, .9]).round(2).to_dict())
    print(prop.Category.value_counts().head(8).to_dict())
    beats = gpd.read_parquet(WORK / "beats_albers.parquet")[["Division", "geometry"]]
    good = prop[prop.ratio.between(.5, 2)].reset_index()
    j = gpd.sjoin(good.assign(geometry=good.representative_point()), beats, predicate="within", how="left")
    print("ratio 0.5-2:", len(good), "ha", round(good.kml_ha.sum()), "inside recorded forest", int(j.Division.notna().sum()))
    good.to_crs("EPSG:4326").to_file(GT / "parivesh_polygons_good.gpkg", driver="GPKG")


if __name__ == "__main__":
    build()
