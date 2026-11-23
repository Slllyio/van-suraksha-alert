# Stream the raw footprints (whole-region polygons, 2 GB) and keep each clipped to the Ratapani box,
# merged per (release, layer, acquisition date). Out: footprints_clip.geojson
import ijson, json
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union
D = "/mnt/project-files/fire-alert-scars/wayback/"
BB = box(77.30, 22.78, 78.10, 23.14)
acc = {}
with open(D + "footprints.geojson", "rb") as f:
    for ft in ijson.items(f, "features.item", use_float=True):
        p = ft["properties"]
        try:
            g = shape(ft["geometry"]).buffer(0).intersection(BB)
        except Exception:
            continue
        if g.is_empty:
            continue
        k = (p["release"], p["layer"], p["SRC_DATE"])
        acc.setdefault(k, [p, []])[1].append(g)
out = [{"type": "Feature", "properties": p, "geometry": mapping(unary_union(gs).simplify(0.0002))} for p, gs in acc.values()]
json.dump({"type": "FeatureCollection", "features": out}, open(D + "footprints_clip.geojson", "w"))
print("kept", len(out))
