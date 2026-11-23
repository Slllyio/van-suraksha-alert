"""FSI thread's barrier layer (fsi/scouting/data/barriers_ratapani.geojson, Oct 15) + scar thread's event polygons -> data/barriers2.npz
on the 20 m model grid:
  seg_id      int32  index of the line segment through the pixel (-1 none; recurrent_scar_edge class left out: it is built from all seasons)
  seg_p       float32 per segment stop probability (all fires), seg_p_far: fires that started > 1 km from the line (falls back to seg_p)
  seg_cls     per segment class name
  pstop       float32 max stop probability of the lines through the pixel, pstop_d: same after a 3x3 max filter (sampling tolerance)
  road_any    bool  OSM / TomTom / Microsoft roads + rail;  stream_big: DEM streams >= 5 km2;  stream_small: 0.25-5 km2
  recur_c_<s> uint8 seasons other than s (2017-2026, Jan-Jun event scars) in which the pixel was an in-forest scar edge (1 px registration)
  recur_n_<s> uint8 seasons other than s in which the pixel lay unburned within 100 m of a scar
  pday_<s>    int16 earliest day-of-year (Oct of s-1 = negative) by which an event polygon covering the pixel was KNOWN (persistence check or first post-fire look), -999 none
"""
import numpy as np, json, time
from scipy import ndimage
from rasterio import features
from rasterio.transform import Affine
from pyproj import Transformer
from shapely.geometry import shape, LineString
from shapely.ops import transform as sh_transform
D = '/tmp/claude-0/spread/data'
G = np.load(f'{D}/grid20.npz'); H, W = G['shape']; a = G['transform']; T = Affine(a[0], a[1], a[2], a[3], a[4], a[5])
WC = G['wc']; burnable = np.isin(WC, [10, 20, 30])
tr = Transformer.from_crs(4326, 32643, always_xy=True).transform
t0 = time.time()
g = json.load(open('/mnt/project-files/ratapani/fsi/scouting/data/barriers_ratapani.geojson'))
segs, P, PF, CLS = [], [], [], []
for f in g['features']:
    p = f['properties']
    if p['cls'] == 'recurrent_scar_edge':
        continue
    geom = sh_transform(tr, shape(f['geometry']))
    if geom.is_empty:
        continue
    segs.append(geom); P.append(float(p['p_stop'] or 0)); PF.append(float(p['p_stop_far'] if p['p_stop_far'] is not None else (p['p_stop'] or 0))); CLS.append(p['cls'])
# FSI thread's administrative boundary lines (fire_barrier_maps.md addendum, Oct 15 12:00Z): division/district, range and beat boundaries
# from the MP beat map, weak stops measured with the same 60 m hold test (0.16 / 0.14 / 0.08; roads 0.37 and rail 0.75 in the same run)
for fn, cls, pst in [('div_line', 'admin_division', 0.16), ('range_line', 'admin_range', 0.14), ('beat_line', 'admin_beat', 0.08)]:
    ga = json.load(open(f'/mnt/project-files/ratapani/fsi/scouting/data/admin_lines/{fn}.geojson'))
    for f in ga['features']:
        geom = sh_transform(tr, shape(f['geometry']))
        for part in (list(geom.geoms) if hasattr(geom, 'geoms') else [geom]):
            if not part.is_empty:
                segs.append(part); P.append(pst); PF.append(pst); CLS.append(cls)
P, PF, CLS = np.array(P, np.float32), np.array(PF, np.float32), np.array(CLS)
# rasterise highest stop probability last so it wins where lines cross
order = np.argsort(P, kind='stable')
seg_id = features.rasterize(((segs[i], int(i)) for i in order), out_shape=(H, W), transform=T, fill=-1, all_touched=True, dtype='int32')
pstop = np.where(seg_id >= 0, P[np.maximum(seg_id, 0)], 0).astype(np.float32)
pstop_d = ndimage.maximum_filter(pstop, size=3)
def cls_mask(names):
    ids = np.nonzero(np.isin(CLS, names))[0]
    return features.rasterize(((segs[i], 1) for i in ids), out_shape=(H, W), transform=T, fill=0, all_touched=True, dtype='uint8').astype(bool)
road_any = cls_mask(['road_osm', 'road_tomtom', 'road_ms_ge10m', 'road_ms_7_10m', 'rail'])
stream_big = cls_mask(['stream_dem_5_25km2', 'stream_dem_ge25km2']); stream_small = cls_mask(['stream_dem_0.25_1km2', 'stream_dem_1_5km2'])
print(f'{len(segs)} segments; pixels on a line {int((seg_id >= 0).sum())}, road {int(road_any.sum())}, big stream {int(stream_big.sum())}, small stream {int(stream_small.sum())}; {time.time() - t0:.0f}s', flush=True)
for c in np.unique(CLS):
    print(f'  {c:22s} n={int((CLS == c).sum()):6d} p_stop={P[CLS == c][0]:.2f} far={PF[CLS == c][0]:.2f} km={sum(s.length for s, k in zip(segs, CLS) if k == c) / 1000:.0f}')
# event polygons by season
e = json.load(open('/mnt/project-files/fire-alert-scars/event_scars.geojson'))
polys = []
for f in e['features']:
    p = f['properties']; d = np.datetime64(p['date']); y = int(p['date'][:4]); m = int(p['date'][5:7])
    s = y if m <= 6 else (y + 1 if m >= 10 else None)
    if s is None:
        continue
    # the day the scar was KNOWN (audit item 2): the persistence check if done, else the first clear post-fire look, never before the alert
    kd = p.get('check_date') if p.get('persist_checked') else p.get('post_date')
    kd = np.datetime64(kd) if kd else d
    doy = int((max(d, kd) - np.datetime64(f'{s}-01-01')).astype(int)) + 1
    polys.append((s, m, doy, sh_transform(tr, shape(f['geometry']))))
print('polygons', len(polys), f'{time.time() - t0:.0f}s', flush=True)
seasons = list(range(2017, 2027))
reg, near, pday = {}, {}, {}
k3 = np.ones((3, 3), bool); k100 = ndimage.iterate_structure(ndimage.generate_binary_structure(2, 1), 5)   # ~100 m
for s in seasons:
    ps = [(g_, 1) for (ss, m, doy, g_) in polys if ss == s and m <= 6]
    U = features.rasterize(ps, out_shape=(H, W), transform=T, fill=0, all_touched=False, dtype='uint8').astype(bool) if ps else np.zeros((H, W), bool)
    edge = burnable & ~U & ndimage.binary_dilation(U, k3)
    reg[s] = ndimage.binary_dilation(edge, k3)
    near[s] = ~U & ndimage.binary_dilation(U, k100)
    # earliest alert day per pixel over Oct(s-1)-Jun(s) polygons
    pd_ = np.full((H, W), 32767, np.int16)
    for (ss, m, doy, g_) in sorted([q for q in polys if q[0] == s], key=lambda q: -q[2]):
        mm = features.rasterize([(g_, 1)], out_shape=(H, W), transform=T, fill=0, all_touched=False, dtype='uint8').astype(bool)
        pd_[mm] = np.minimum(pd_[mm], doy)
    pd_[pd_ == 32767] = -999; pday[s] = pd_
    print(s, 'polygons', len(ps), 'scar px', int(U.sum()), 'edge px', int(edge.sum()), f'{time.time() - t0:.0f}s', flush=True)
out = dict(seg_id=seg_id, seg_p=P, seg_p_far=PF, seg_cls=CLS, pstop=pstop, pstop_d=pstop_d, road_any=road_any, stream_big=stream_big, stream_small=stream_small)
for s in range(2017, 2025):
    out[f'recur_c_{s}'] = sum(reg[t].astype(np.uint8) for t in seasons if t != s).astype(np.uint8)
    out[f'recur_n_{s}'] = sum(near[t].astype(np.uint8) for t in seasons if t != s).astype(np.uint8)
    out[f'pday_{s}'] = pday[s]
    c, n = out[f'recur_c_{s}'], out[f'recur_n_{s}']
    r5 = (c >= 5) & (c >= 0.5 * np.maximum(n, 1))
    print(s, 'recurrent-edge pixels (>=5 of 9 other seasons, ratio >= 0.5):', int(r5.sum()), f'= {r5.sum() * 0.02 * 1.0:.0f} km-ish of 20 m pixels', flush=True)
np.savez_compressed(f'{D}/barriers2_tmp.npz', **out)
print('saved', f'{time.time() - t0:.0f}s')
import os; os.replace(f'{D}/barriers2_tmp.npz', f'{D}/barriers2.npz')
