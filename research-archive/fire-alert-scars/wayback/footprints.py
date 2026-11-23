# Wayback (Esri World Imagery archive) acquisitions over Ratapani: one footprint per (release, layer, acquisition),
# from each release's metadata service (30 cm, 60 cm, 1.2 m layers). f=json (f=geojson and count queries get 403).
# Out: footprints.geojson
import json, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
D = "/mnt/project-files/fire-alert-scars/wayback/"
cfg = json.load(open(D + "config.json"))
BB = "77.30,22.78,78.10,23.14"
def get(u):
    for k in range(5):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=180))
        except Exception:
            time.sleep(4 * (k + 1))
    return None
def q(args):
    rel, lay = args; c = cfg[rel]; out = []; off = 0
    while True:
        u = c["metadataLayerUrl"] + f"/{lay}/query?" + urllib.parse.urlencode(dict(
            geometry=BB, geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects",
            outFields="SRC_DATE,SRC_RES,SRC_DESC,MinMapLevel,MaxMapLevel", returnGeometry="true", outSR=4326,
            resultOffset=off, resultRecordCount=200, f="json"))
        d = get(u)
        if not d or "features" not in d:
            print("FAILED", rel, lay, off); return out
        for f in d["features"]:
            p = f["attributes"]; p.update(release=int(rel), title=c["itemTitle"], layer=lay)
            out.append({"type": "Feature", "properties": p, "geometry": {"type": "Polygon", "coordinates": f["geometry"]["rings"]}})
        if not d.get("exceededTransferLimit") or not d["features"]:
            return out
        off += len(d["features"])
jobs = [(r, l) for r in cfg for l in (4, 5, 6)]
with ThreadPoolExecutor(3) as ex:
    feats = [f for fs in ex.map(q, jobs) for f in fs]
json.dump({"type": "FeatureCollection", "features": feats}, open(D + "footprints_raw.geojson", "w"))
print("features", len(feats))
