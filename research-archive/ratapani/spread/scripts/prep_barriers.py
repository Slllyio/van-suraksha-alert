"""Microsoft road detections (scouting/data/ms_roads_rata.tsv) -> 20 m barrier mask on the model grid."""
import numpy as np, json, rasterio
from rasterio import features
from rasterio.transform import Affine
from pyproj import Transformer
from shapely.geometry import LineString
G = np.load('/tmp/claude-0/spread/data/grid20.npz'); H, W = G['shape']; a = G['transform']
T = Affine(a[0], a[1], a[2], a[3], a[4], a[5])
tr = Transformer.from_crs(4326, 32643, always_xy=True)
lines, km, widths = [], 0.0, []
for ln in open('/mnt/project-files/ratapani/fsi/scouting/data/ms_roads_rata.tsv'):
    p = ln.rstrip('\n').split('\t')
    if len(p) < 2:
        continue
    f = json.loads(p[1]); c = f['geometry']['coordinates']
    x, y = tr.transform([q[0] for q in c], [q[1] for q in c])
    g = LineString(zip(x, y)); lines.append(g); km += g.length / 1000; widths.append(float(f['properties'].get('WidthMeters', 0)))
road = features.rasterize(((g, 1) for g in lines), out_shape=(H, W), transform=T, all_touched=True, dtype=np.uint8).astype(bool)
inside = np.isin(G['wc'], [10, 20, 30])
print(f'{len(lines)} road segments, {km:.0f} km, median width {np.median(widths):.1f} m; road pixels {road.sum()} ({road.sum()*0.04:.0f} ha), of which in forest/shrub/grass {(road & inside).sum()}')
np.savez_compressed('/tmp/claude-0/spread/data/barriers.npz', road=road)
