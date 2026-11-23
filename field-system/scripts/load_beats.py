"""Convert a beat shapefile (e.g. the MP beat layer in E:\\MP_Merge) to data/beats.geojson.

  python scripts/load_beats.py E:\\MP_Merge\\beats.shp --uid DID,RID,BID --beat Beat --range Range --division Division

Reprojects to WGS84 using the .prj next to the .shp. --uid joins fields with '-'
(zero-padded to 3 digits when numeric), matching ratapani/beats beat_uid.
"""
import argparse, json, sys
from pathlib import Path
import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform  # noqa

ap = argparse.ArgumentParser()
ap.add_argument("shp")
ap.add_argument("--uid", required=True)
ap.add_argument("--beat", required=True)
ap.add_argument("--range", required=True)
ap.add_argument("--division", default=None)
ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data/beats.geojson"))
a = ap.parse_args()
prj = Path(a.shp).with_suffix(".prj")
src = CRS.from_wkt(prj.read_text()) if prj.exists() else CRS.from_epsg(4326)
tf = Transformer.from_crs(src, 4326, always_xy=True).transform
r = shapefile.Reader(a.shp)
names = [f[0] for f in r.fields[1:]]


def pad(v):
    s = str(v).strip()
    return s.split(".")[0].zfill(3) if s.replace(".", "").isdigit() else s


feats, seen = [], {}
for sr in r.iterShapeRecords():
    rec = dict(zip(names, sr.record))
    g = shape(sr.shape.__geo_interface__)
    if not src.equals(CRS.from_epsg(4326)):
        g = transform(tf, g)
    uid = "-".join(pad(rec[k]) for k in a.uid.split(","))
    if uid in seen:
        uid = f"{uid}#{seen[uid]}"
    seen[uid.split('#')[0]] = seen.get(uid.split('#')[0], 0) + 1
    feats.append({"type": "Feature", "geometry": mapping(g.buffer(0).simplify(0.0001)),
                  "properties": {"beat_uid": uid, "beat": str(rec[a.beat]), "range": str(rec[a.range]),
                                 "division": str(rec[a.division]) if a.division else "", "source": Path(a.shp).name}})
json.dump({"type": "FeatureCollection", "features": feats}, open(a.out, "w"))
print(f"{len(feats)} beats -> {a.out}  (fields available: {names})")
