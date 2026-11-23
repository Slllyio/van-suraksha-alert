"""Turn the 24 h chance map into a per-beat check list and replay 2025-26 (forward test: models trained on 2017-24 only).
At each afternoon (13:30 IST) satellite look, every beat with forecast cells gets its top 3 spots (150 m cells, at least
450 m apart). A spot 'pays off' if it burns in the next 24 h (dated truth = arrival maps), and separately if any VIIRS dot
lands within 300 m in the next 24 h (raw truth). Compared with picking spots by the 600 m ring and by 'next to the latest dot'.
Out: beat_checklist/summary.json"""
import pandas as pd, numpy as np, geopandas as gpd, json, sys
OUT = '/mnt/project-files/research/spread-review/beat_checklist/'
B = gpd.read_file('/mnt/project-files/field-system/data/beats.geojson').to_crs(32643)[['beat_uid', 'beat', 'geometry']]
S = sys.argv[1]
slots = None
res = {}
for tag, path in (('dated_truth', '/mnt/project-files/research/spread-review/forecast_burn/preds.parquet'),
                  ('raw_dots', '/mnt/project-files/research/spread-review/forecast/preds.parquet')):
    P = pd.read_parquet(path, columns=['fire', 'yr', 's', 'x', 'y', 'd_all', 'd_last', 'y24', 'cal_y24', 'ring_y24', 'split'])
    P = P[P.split == 'fwd']
    if slots is None:
        A = pd.read_parquet(S + '/passes.parquet'); T = pd.read_parquet(S + '/tracks.parquet')
        sl = pd.DataFrame({'look': sorted(set(A.look) | set(T.look))}); sl['t'] = sl.look.map(A.groupby('look').t.min()).fillna(sl.look.map(T.groupby('look').t.min()))
        slots = sl.sort_values('t').reset_index(drop=True)
    P = P[slots.look.values[P.s.values].astype(str).astype(object) == slots.look.values[P.s.values]]  # no-op guard
    P = P[pd.Series(slots.look.values[P.s.values]).str.endswith('D').values]             # afternoon issues only
    g = gpd.GeoDataFrame(P, geometry=gpd.points_from_xy(P.x, P.y), crs=32643)
    g = gpd.sjoin(g, B, predicate='within', how='inner').drop(columns=['geometry', 'index_right'])
    # pool all fires per beat and day (several fires can share a beat): keep the best score per cell
    g['day'] = slots.look.values[g.s.values]
    g = g.sort_values('cal_y24', ascending=False).drop_duplicates(['day', 'beat_uid', 'x', 'y'])
    scores = dict(chance_map=g.cal_y24.values, ring_600m=g.ring_y24.values, next_to_latest_dot=-g.d_last.values)
    out = {}
    for name, sc in scores.items():
        g['sc'] = sc; picks = []
        for (day, beat), q in g.groupby(['day', 'beat_uid']):
            q = q.sort_values('sc', ascending=False); chosen = []
            for r in q.itertuples():
                if all((r.x - c.x) ** 2 + (r.y - c.y) ** 2 >= 450 ** 2 for c in chosen): chosen.append(r)
                if len(chosen) == 3: break
            picks.append(dict(day=day, beat=beat, any_hit=any(c.y24 for c in chosen), hits=sum(c.y24 for c in chosen), n=len(chosen)))
        pk = pd.DataFrame(picks)
        out[name] = dict(checklists=len(pk), share_lists_with_a_burning_spot=round(float(pk.any_hit.mean()), 3),
                         share_spots_that_burn=round(float(pk.hits.sum() / pk.n.sum()), 3))
    res[tag] = out
json.dump(res, open(OUT + 'summary.json', 'w'), indent=1); print(json.dumps(res, indent=1))
