"""Per-cell access features -> E:/FIRE/ratapani/ee/proximity.csv (distances in metres, UTM 43N).
OSM (Overpass) roads + settlements within 10 km of the AOI; AOI boundary; WorldCover-derived edges on the 500 m grid."""
import json, urllib.request, urllib.parse
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point
from scipy.ndimage import distance_transform_edt

R = Path(r"E:\FIRE\ratapani")
grid = gpd.read_file(R / "grid_500m.geojson")
aoi = gpd.read_file(R / "ratapani_aoi.geojson").to_crs(32643)
cent = grid.to_crs(32643).centroid
x0, y0, x1, y1 = aoi.buffer(10000).to_crs(4326).total_bounds
bbox = f"{y0},{x0},{y1},{x1}"
q = f"""[out:json][timeout:180];
(way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential|track"]({bbox});
 node["place"~"village|hamlet|town|city"]({bbox}););
out geom;"""
els = None
for url in ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter", "https://overpass-api.de/api/interpreter"]:
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                     headers={"User-Agent": "ratapani-fire-research"})
        els = json.load(urllib.request.urlopen(req, timeout=300))["elements"]
        print("overpass ok:", url)
        break
    except Exception as e:
        print("overpass failed:", url, e)
if els is None:
    raise SystemExit("all Overpass mirrors failed")
roads, tracks, places = [], [], []
for e in els:
    if e["type"] == "way" and len(e.get("geometry", [])) > 1:
        line = LineString([(p["lon"], p["lat"]) for p in e["geometry"]])
        (tracks if e["tags"].get("highway") == "track" else roads).append(line)
    elif e["type"] == "node":
        places.append(Point(e["lon"], e["lat"]))
print("osm roads", len(roads), "tracks", len(tracks), "places", len(places))


def dist_to(geoms):
    if not geoms:
        return np.full(len(grid), np.nan)
    g = gpd.GeoSeries(geoms, crs=4326).to_crs(32643)
    j = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=cent), gpd.GeoDataFrame(geometry=g), distance_col="d")
    return j.groupby(level=0).d.min().reindex(cent.index).to_numpy()


out = pd.DataFrame({"cell_id": grid.cell_id,
                    "dist_road": dist_to(roads), "dist_track": dist_to(tracks), "dist_village": dist_to(places),
                    "dist_boundary": cent.distance(aoi.boundary.iloc[0]).to_numpy()})

# grid-based edges from WorldCover fractions
wc = pd.read_csv(R / "ee" / "worldcover.csv").set_index("cell_id").reindex(grid.cell_id)
NI, NJ = grid.i.max() + 1, grid.j.max() + 1
def grid_dist(mask):
    r = np.zeros((NI, NJ), bool)  # EDT = distance to nearest False; outside AOI counts as "not forest"
    r[grid.i, grid.j] = mask
    return distance_transform_edt(r)[grid.i, grid.j] * 500
out["depth_in_forest"] = np.where(wc.wc_10.to_numpy() >= 0.5, grid_dist(wc.wc_10.to_numpy() >= 0.5), 0)
crop = (wc.wc_40.to_numpy() >= 0.2)
r = np.ones((NI, NJ), bool); r[grid.i[crop], grid.j[crop]] = False
out["dist_crop_cell"] = distance_transform_edt(r)[grid.i, grid.j] * 500
out.to_csv(R / "ee" / "proximity.csv", index=False)
print(out.describe().round(0).to_string())
