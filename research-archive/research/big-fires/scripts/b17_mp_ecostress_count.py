"""How many ECOSTRESS 70 m passes fall on fires across all of Madhya Pradesh (Akkshay 17 Oct 11:46Z "do this on all-over MP fires").
No login needed: lists every ECO_L2T_LSTE granule over the MP box in the fire season (15 Feb-15 Jun, 2018-25) from the NASA catalogue,
then matches each granule to all-MP forest fire events (fire-alert-scars/mp/out) by tile footprint and time:
a VIIRS alert of the event within +-1 h of the ECOSTRESS pass (the same rule as section 14b/14c on Ratapani).
Output: results/mp_ecostress_count.json, results/mp_ecostress_pairs.csv (event, granule, gap). The fetch needs EARTHDATA_TOKEN (b17b)."""
import os, json, urllib.request, urllib.parse, pandas as pd, numpy as np
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree
R = '/mnt/project-files/research/big-fires/results'; M = '/mnt/project-files/fire-alert-scars/mp/out'
SC = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/mp_eco'
gpath = f'{SC}/mp_granules.csv'
if not os.path.exists(gpath):
    rows = []
    for yr in range(2018, 2026):
        for sn, ver in [('ECO_L2T_LSTE', '002'), ('ECO_L2T_LSTE', '003')]:
            page = 1
            while True:
                q = urllib.parse.urlencode({'short_name': sn, 'version': ver, 'bounding_box': '74.0,21.0,82.9,26.9',
                                            'temporal': f'{yr}-02-15T00:00:00Z,{yr}-06-15T23:59:59Z', 'page_size': 2000, 'page_num': page})
                d = json.load(urllib.request.urlopen(f'https://cmr.earthdata.nasa.gov/search/granules.json?{q}', timeout=120)); e = d['feed']['entry']
                for g in e:
                    poly = None
                    if 'polygons' in g: poly = g['polygons'][0][0]
                    rows.append(dict(product=sn, ver=ver, id=g['title'], t0=g.get('time_start'), day=g.get('day_night_flag'), poly=poly, boxes=g.get('boxes', [None])[0]))
                print(yr, ver, page, len(e), flush=True)
                if len(e) < 2000: break
                page += 1
    pd.DataFrame(rows).to_csv(gpath, index=False)
E = pd.read_csv(gpath); E['t0'] = pd.to_datetime(E.t0).dt.tz_localize(None); E['tile'] = E.id.str.split('_').str[5]
E = E.drop_duplicates(['tile', 't0'])          # v002 and v003 of the same pass count once
print('granules', len(E), 'tiles', E.tile.nunique(), 'day', (E.day == 'DAY').sum())
def footprint(r):
    if isinstance(r.poly, str):
        v = [float(x) for x in r.poly.split()]; return Polygon([(v[i+1], v[i]) for i in range(0, len(v), 2)])
    s, w, n, e = [float(x) for x in r.boxes.split()]; return Polygon([(w, s), (e, s), (e, n), (w, n)])
E['geom'] = E.apply(footprint, axis=1)
# tile footprint = union over granules of the tile (should be one square)
tiles = {t: g.geom.iloc[0] for t, g in E.groupby('tile')}
A = pd.read_csv(f'{M}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'event_id'])
A = A[A.instrument == 'VIIRS']
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
ev = pd.read_csv(f'{M}/mp_events.csv', usecols=['event_id', 'forest']); A = A[A.event_id.isin(ev[ev.forest].event_id)]
print('VIIRS alerts on forest events', len(A), 'events', A.event_id.nunique())
# per event: one point (first alert) and the set of alert times
pt = A.groupby('event_id').agg(lat=('latitude', 'first'), lon=('longitude', 'first')).reset_index()
tnames = list(tiles); tree = STRtree([tiles[t] for t in tnames])
pt['tiles'] = [[tnames[i] for i in tree.query(Point(lo, la), predicate='within')] for lo, la in zip(pt.lon, pt.lat)]
pt = pt.explode('tiles').dropna(subset=['tiles']).rename(columns={'tiles': 'tile'})
T = A.groupby('event_id').t.apply(lambda s: sorted(set(s.round('min')))).to_dict()
pairs = []
for tile, g in pt.groupby('tile'):
    Eg = E[E.tile == tile]
    if Eg.empty: continue
    et = Eg.t0.values
    for eid in g.event_id:
        for ta in T[eid]:
            dt = np.abs((et - np.datetime64(ta)) / np.timedelta64(1, 'm'))
            for j in np.where(dt <= 60)[0]:
                pairs.append(dict(event_id=eid, granule=Eg.id.iloc[j], tile=tile, t0=Eg.t0.iloc[j], day=Eg.day.iloc[j], gap_min=float(dt[j])))
PR = pd.DataFrame(pairs).drop_duplicates(['event_id', 'granule'])
PR = PR.sort_values('gap_min').drop_duplicates(['event_id', 't0'])
PR.to_csv(f'{R}/mp_ecostress_pairs.csv', index=False)
out = dict(granules=int(len(E)), tiles=int(E.tile.nunique()), forest_events_viirs=int(A.event_id.nunique()),
           event_passes_within_1h=int(len(PR)), events=int(PR.event_id.nunique()), day_passes=int((PR.day == 'DAY').sum()),
           by_year=PR.groupby(PR.t0.dt.year).size().to_dict(),
           expected_visible_at_ratapani_rate=dict(usable_share=262 / 520, visible_share_of_usable=30 / 262,
                                                  est_usable=int(len(PR) * 262 / 520), est_visible=int(len(PR) * 30 / 520)))
json.dump(out, open(f'{R}/mp_ecostress_count.json', 'w'), indent=1, default=str); print(json.dumps(out, indent=1, default=str))
