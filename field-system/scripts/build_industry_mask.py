"""Build the non-forest heat-source mask FSI applies (industry, mining, solar, kilns, power plants),
buffered 500 m, from OpenStreetMap via Overpass. Output: data/industry_mask.geojson

  python scripts/build_industry_mask.py [--bbox 21,74,27,83] [--osm saved_overpass.json]
"""
import argparse, json, sys, urllib.parse, urllib.request
from pathlib import Path
from shapely.geometry import Polygon, LineString, mapping, shape
from shapely.ops import unary_union

ap = argparse.ArgumentParser()
ap.add_argument("--bbox", default="21,74,27,83", help="south,west,north,east")
ap.add_argument("--osm", help="use a saved Overpass JSON instead of downloading")
ap.add_argument("--buffer-m", type=float, default=500)
a = ap.parse_args()
b = a.bbox
Q = f"""[out:json][timeout:180];(
way["landuse"~"^(quarry|industrial|landfill)$"]({b});relation["landuse"~"^(quarry|industrial)$"]({b});
way["power"="plant"]({b});relation["power"="plant"]({b});
way["man_made"~"^(works|kiln)$"]({b});way["industrial"~"brick|mine"]({b}););out geom;"""
if a.osm:
    data = json.load(open(a.osm))
else:
    req = urllib.request.Request("https://overpass.private.coffee/api/interpreter",
                                 data=urllib.parse.urlencode({"data": Q}).encode(),
                                 headers={"User-Agent": "vanagni-field-system/0.1"})
    data = json.load(urllib.request.urlopen(req, timeout=600))


def kind(t):
    if t.get("landuse") == "quarry" or "mine" in t.get("industrial", ""):
        return "mine_quarry"
    if t.get("power") == "plant":
        return "solar" if "solar" in (t.get("plant:source", "") + t.get("generator:source", "")) else "power_plant"
    if "brick" in t.get("industrial", "") or t.get("man_made") == "kiln":
        return "kiln"
    if t.get("landuse") == "landfill":
        return "landfill"
    return "industrial"


geoms = {}
for el in data["elements"]:
    rings = []
    if el["type"] == "way" and "geometry" in el:
        rings = [[(p["lon"], p["lat"]) for p in el["geometry"]]]
    elif el["type"] == "relation":
        rings = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in el.get("members", [])
                 if m.get("role") == "outer" and "geometry" in m]
    for r in rings:
        if len(r) < 2:
            continue
        g = Polygon(r) if len(r) >= 4 and r[0] == r[-1] else LineString(r)
        geoms.setdefault(kind(el.get("tags", {})), []).append(g if g.is_valid else g.buffer(0))
deg = a.buffer_m / 111_320
feats = []
for k, gs in geoms.items():
    u = unary_union([g.buffer(deg) for g in gs]).simplify(deg / 20)
    feats.append({"type": "Feature", "properties": {"kind": k, "n_osm": len(gs)}, "geometry": mapping(u)})
    print(k, len(gs), f"{u.area * 111.32**2 * 0.93:.0f} km2 buffered")
out = Path(__file__).resolve().parent.parent / "data/industry_mask.geojson"
json.dump({"type": "FeatureCollection", "features": feats,
           "note": f"OSM via Overpass, buffered {a.buffer_m:.0f} m, timestamp {data.get('osm3s', {}).get('timestamp_osm_base')}"},
          open(out, "w"))
print("->", out)
