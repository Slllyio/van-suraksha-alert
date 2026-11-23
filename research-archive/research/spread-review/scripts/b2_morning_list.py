"""Morning check list from night detections, replayed on 2025-26 (fire season 15 Feb-15 Jun).
After each 01:30 look with dots inside the 94 Ratapani beats, every beat with a night dot within 5 km gets 3 spots
(300 m squares, >= 450 m apart, inside the beat). A spot is 'hit' if a VIIRS dot lands within 300 m at the next two looks
(13:30 the same day or 01:30 the next night). Separately: hits by NEW fires (dot > 1 km from every dot of the previous 2 days).
Spot pickers:
  closest      - nearest to tonight's dots (spread)
  ring_1_2km   - 1-2 km from tonight's dots, most fire-prone first (2017-24 dot history)
  mixed        - 2 closest + 1 from the 1-2 km ring
  history      - most fire-prone squares within 5 km, ignoring distance
  random       - random squares within 5 km
Out: morning_list/summary.json"""
import pandas as pd, numpy as np, geopandas as gpd, json, os, sys
from scipy.spatial import cKDTree
S = sys.argv[1]; O = '/mnt/project-files/research/spread-review/morning_list/'; os.makedirs(O, exist_ok=True)
A = pd.read_parquet(S + '/tracks.parquet'); P = pd.read_parquet(S + '/passes.parquet')
slots = pd.DataFrame({'look': sorted(set(P.look) | set(A.look))})
slots['t'] = slots.look.map(P.groupby('look').t.min()).fillna(slots.look.map(A.groupby('look').t.min()))
slots = slots.sort_values('t').reset_index(drop=True); sidx = dict(zip(slots.look, slots.index)); A['si'] = A.look.map(sidx); A['yr'] = A.t.dt.year
B = gpd.read_file('/mnt/project-files/field-system/data/beats.geojson').to_crs(32643)[['beat_uid', 'geometry']]
H = A[A.yr <= 2024]; Ht = cKDTree(H[['x', 'y']].values)
xmin, ymin, xmax, ymax = B.total_bounds
gx, gy = np.meshgrid(np.arange(xmin, xmax, 300) + 150, np.arange(ymin, ymax, 300) + 150)
G = gpd.GeoDataFrame(dict(x=gx.ravel(), y=gy.ravel()), geometry=gpd.points_from_xy(gx.ravel(), gy.ravel()), crs=32643)
G = gpd.sjoin(G, B, predicate='within').drop(columns=['geometry', 'index_right']).reset_index(drop=True)
G['hn'] = [len(v) for v in Ht.query_ball_point(G[['x', 'y']].values, 500)]
GX = G[['x', 'y']].values; At = A.si.values; AX = A[['x', 'y']].values
rng = np.random.default_rng(0)
def pick(q, order, n=3):
    q = q.iloc[order]; ch = []
    for r in q.itertuples():
        if all((r.x - c.x) ** 2 + (r.y - c.y) ** 2 >= 450 ** 2 for c in ch): ch.append(r)
        if len(ch) == n: break
    return ch
night = [s for s in range(len(slots)) if slots.look[s].endswith('N') and slots.t[s].year >= 2025 and '02-15' <= slots.t[s].strftime('%m-%d') <= '06-15']
recs = []
for s in night:
    nd = A[A.si == s]
    if not len(nd): continue
    d = cKDTree(nd[['x', 'y']].values).query(GX)[0]; near = d <= 5000
    if not near.any(): continue
    fut = np.where((At > s) & (At <= s + 2))[0]
    hit = np.isfinite(cKDTree(AX[fut]).query(GX, distance_upper_bound=300)[0]) if len(fut) else np.zeros(len(G), bool)
    prev = np.where((At >= s - 4) & (At <= s))[0]                                   # dots of the previous 2 days incl. tonight
    if len(fut):
        newf = np.isinf(cKDTree(AX[prev]).query(AX[fut], distance_upper_bound=1000)[0])
        nh = np.isfinite(cKDTree(AX[fut][newf]).query(GX, distance_upper_bound=300)[0]) if newf.any() else np.zeros(len(G), bool)
    else: nh = np.zeros(len(G), bool)
    Q = G.assign(d=d, hit=hit, newhit=nh)[near]
    for beat, q in Q.groupby('beat_uid'):
        ring = (q.d >= 1000) & (q.d <= 2000)
        orders = dict(closest=np.argsort(q.d.values, kind='stable'),
                      ring_1_2km=np.lexsort((-q.hn.values, ~ring.values)),
                      history=np.argsort(-q.hn.values, kind='stable'),
                      random=rng.permutation(len(q)))
        res = {k: pick(q, o) for k, o in orders.items()}
        rr = pick(q, orders['ring_1_2km'], 1); cl = [c for c in pick(q, orders['closest']) if all((c.x - r.x) ** 2 + (c.y - r.y) ** 2 >= 450 ** 2 for r in rr)][:2]
        res['mixed'] = cl + rr
        for k, ch in res.items():
            recs.append(dict(s=s, beat=beat, method=k, n=len(ch), hits=sum(c.hit for c in ch), any=any(c.hit for c in ch),
                             newhits=sum(c.newhit for c in ch), anynew=any(c.newhit for c in ch), beat_has_night_dot=bool((q.d < 300).any())))
R = pd.DataFrame(recs); out = dict(nights=int(R.s.nunique()), lists_per_method=int(len(R) // R.method.nunique()))
for part, q in (('all beats within 5 km of a night dot', R), ('beats with a night dot inside', R[R.beat_has_night_dot])):
    out[part] = {k: dict(lists=len(g), lists_with_a_hit=round(float(g['any'].mean()), 3), spots_hit=round(float(g.hits.sum() / g.n.sum()), 3),
                         lists_with_a_new_fire_hit=round(float(g.anynew.mean()), 3)) for k, g in q.groupby('method')}
json.dump(out, open(O + 'summary.json', 'w'), indent=1); print(json.dumps(out, indent=1))
