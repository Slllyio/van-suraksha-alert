"""Per-look fire-front forecast (Oct 17): what the multi-front work recommends issuing after every VIIRS look.
Input: a CSV of the VIIRS detections of ONE fire seen so far (columns latitude, longitude, t (UTC), frp [, scan, track]), and the issue
time (default: the latest detection). Output GeoJSON (WGS84) with:
  - one feature per front: status (continuing / new front / separate start / old), dots, expected new burning in 24 h (ha, with a
    rough 2x band), chance it stops (adds < 2 ha in 24 h)
  - 'burned_so_far': the 375 m blocks seen so far
  - 'forecast_24h': blocks + each active front grown by its expected area, nearest ground first (the honest distance rule; physics
    and direction add nothing on these fires)
  - 'new_front_band': 1-3 km band around active fronts where new fronts appear (34% of next-day new burning lies > 1 km out; no input
    beats distance inside it). Scaled risk = expected growth of the fire.
Models: multi_front/models/growth24_all.txt, stop24_all.txt (146 big Ratapani fires, 2017-26). Research use; not checked live.
  python3 forecast_fronts.py detections.csv out.geojson [issue_time_utc]
"""
import sys, json, numpy as np, pandas as pd, lightgbm as lgb, pyproj
from scipy.spatial import cKDTree
from shapely.geometry import Point, mapping
from shapely.ops import unary_union, transform
sys.path.insert(0, '/tmp/claude-0/spread/scripts'); sys.path.insert(0, '/mnt/project-files/ratapani/spread/scripts')
from mf_tracker_lib import clusters
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
MD = '/mnt/project-files/ratapani/spread/multi_front/models'
GM, SM = lgb.Booster(model_file=f'{MD}/growth24_all.txt'), lgb.Booster(model_file=f'{MD}/stop24_all.txt')
FE = GM.feature_name(); LINK = 750.0; FOOT = 265.0; IST = pd.Timedelta(hours=5, minutes=30)
fwd = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform; back = pyproj.Transformer.from_crs(32643, 4326, always_xy=True).transform

def forecast(d, tiss=None, models=None):
    """d: detections (latitude, longitude, t, frp). Returns (d with looks/fronts, k, feats, foot, fc, band) in UTM 43N."""
    tiss = d.t.max() if tiss is None else tiss
    GM_, SM_ = models if models is not None else (GM, SM)
    d = d[d.t <= tiss].copy(); d['x'], d['y'] = fwd(d.longitude.values, d.latitude.values)
    d = C.viirs_looks(d).reset_index(drop=True); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    k = int(d.lk.max()); xy = d[['x', 'y']].values; lab = clusters(xy); d['front'] = lab
    recent = set(d[d.lk >= k - 1].front); prev = d[d.lk < k][['x', 'y']].values; tk = d.th.max()
    hour = int((d[d.lk == k].t.max() + IST).hour)
    feats = []
    for f in np.unique(lab):
        g = d[d.front == f]; gx = g[['x', 'y']].values
        dprev = cKDTree(prev).query(gx)[0].min() if len(prev) else np.inf
        kind = 'first' if k == 0 else ('old' if g.lk.max() < k else ('continuing' if dprev <= LINK else ('separate' if dprev <= 3000 else 'independent')))
        r, c = C.rc_of(gx[:, 0], gx[:, 1]); wc = C.WC[np.clip(r, 0, C.NR - 1), np.clip(c, 0, C.NC - 1)]
        row = dict(age_h=tk - g.th.min(), n_dots=len(g), n_dots_last=int((g.lk == k).sum()), n_dots_last2=int((g.lk >= k - 1).sum()),
                   frp_last=float(g[g.lk == k].frp.sum()), frp_all=float(g.frp.sum()), night=int(hour < 6 or hour >= 18),
                   extent_m=float(np.ptp(gx[:, 0]) + np.ptp(gx[:, 1])), foot_ha=unary_union([Point(p).buffer(FOOT) for p in gx]).area / 1e4, forest_share=float((wc == 10).mean()),
                   grass_share=float((wc == 30).mean()), n_fronts=int(lab.max() + 1), n_active=len(recent), fire_dots=len(xy),
                   doy=int(t0.dayofyear), th=tk, k=k, kind_c={'first': 0, 'continuing': 1, 'separate': 2, 'independent': 3, 'old': 4}[kind])
        act = f in recent
        grow = float(np.expm1(GM_.predict(pd.DataFrame([row])[FE])[0])) if act else 0.0
        pstop = float(SM_.predict(pd.DataFrame([row])[FE])[0]) if act else 1.0
        feats.append((f, kind, act, gx, max(grow, 0.0), pstop))
    foot = unary_union([Point(p).buffer(FOOT) for p in xy])
    grown = [foot]
    for f, kind, act, gx, grow, pstop in feats:
        if act and grow > 0:
            own = unary_union([Point(p).buffer(FOOT) for p in gx]); lo, hi = 0.0, 3000.0
            for _ in range(25):                     # bisect the buffer distance so the front adds its expected new area (to ~0.01 ha)
                r = (lo + hi) / 2
                if own.buffer(r).difference(foot).area / 1e4 >= grow:
                    hi = r
                else:
                    lo = r
            r = hi
            grown.append(own.buffer(r))
    fc = unary_union(grown); act_pts = unary_union([Point(p).buffer(1) for f, kind, act, gx, g_, ps in feats if act for p in gx])
    band = act_pts.buffer(3000).difference(act_pts.buffer(1000)) if not act_pts.is_empty else None
    return d, k, feats, foot, fc, band


if __name__ == '__main__':
    d = pd.read_csv(sys.argv[1], parse_dates=['t']); out = sys.argv[2]
    d, k, feats, foot, fc, band = forecast(d, pd.Timestamp(sys.argv[3]) if len(sys.argv) > 3 else None)
    names = {'first': 'first look', 'continuing': 'continuing', 'separate': 'new front (0.75-3 km)', 'independent': 'separate start (>3 km)', 'old': 'old (no recent dots)'}
    F = [dict(type='Feature', geometry=mapping(transform(back, unary_union([Point(p).buffer(FOOT) for p in gx]))),
              properties=dict(layer='front', front=int(f), status=('seen at the previous look' if kind == 'old' and act else names[kind]), dots=len(gx), expected_new_ha_24h=round(grow, 1),
                              band_ha_24h=[round(grow / 2, 1), round(grow * 2, 1)], chance_stops_24h=round(pstop, 2)))
         for f, kind, act, gx, grow, pstop in feats]
    F.append(dict(type='Feature', geometry=mapping(transform(back, foot)), properties=dict(layer='burned_so_far', ha=round(foot.area / 1e4, 1))))
    F.append(dict(type='Feature', geometry=mapping(transform(back, fc)), properties=dict(layer='forecast_24h', ha=round(fc.area / 1e4, 1), new_ha=round((fc.area - foot.area) / 1e4, 1),
                                                                                       note='new_ha = sum of active fronts expected_new_ha_24h, less any overlap between fronts',
                                                                                           valid_until_ist=str(d.t.max() + IST + pd.Timedelta(hours=24)))))
    if band is not None:
        F.append(dict(type='Feature', geometry=mapping(transform(back, band)), properties=dict(layer='new_front_band', note='1-3 km; closer is likelier')))
    json.dump(dict(type='FeatureCollection', issued_ist=str(d.t.max() + IST), looks=k + 1, features=F), open(out, 'w'))
    print(f'{len(feats)} fronts, {sum(a for _, _, a, *_ in feats)} active; forecast {fc.area / 1e4:.0f} ha; written {out}')
