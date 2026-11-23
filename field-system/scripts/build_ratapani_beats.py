"""Build approximate Ratapani beat polygons by merging the 500 m grid cells of each beat.

Input:  ratapani/grid_500m.geojson + ratapani/beats/cell_beat.csv + beats_table.csv
Output: field-system/data/beats.geojson (one feature per beat_uid)

These are stand-ins until the real MP beat layer (E:\\MP_Merge) is loaded with
scripts/load_beats.py; edges follow the grid, so points within ~250 m of a beat
edge can land in the neighbouring beat.
"""
import csv, json, sys
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/mnt/project-files")
grid = json.load(open(ROOT / "ratapani/grid_500m.geojson"))
cell_beat = {int(r["cell_id"]): r["beat_uid"] for r in csv.DictReader(open(ROOT / "ratapani/beats/cell_beat.csv"))}
meta = {r["beat_uid"]: r for r in csv.DictReader(open(ROOT / "ratapani/beats/beats_table.csv"))}

cells = {}
for f in grid["features"]:
    b = cell_beat.get(int(f["properties"]["cell_id"]))
    if b:
        cells.setdefault(b, []).append(shape(f["geometry"]).buffer(1e-6))

feats = []
for b, polys in sorted(cells.items()):
    m = meta.get(b, {})
    geom = unary_union(polys).buffer(-1e-6).simplify(1e-5)
    feats.append({"type": "Feature", "properties": {
        "beat_uid": b, "division": m.get("Division", ""), "range": m.get("Range", ""),
        "beat": m.get("Beat", b), "source": "ratapani 500 m grid (approximate)"},
        "geometry": mapping(geom)})
out = Path(__file__).resolve().parent.parent / "data/beats.geojson"
json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
print(f"{len(feats)} beats -> {out}")
