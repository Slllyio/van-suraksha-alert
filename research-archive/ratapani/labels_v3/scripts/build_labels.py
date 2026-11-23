"""Label variants for the 2-day Ratapani target (labels_v3). Issue days Feb 1 - Jun 20, seasons 2017-2026, 3,614 cells.
Every variant keeps SCORING.md's frame: issue day t is positive when the cell burns on t+1 or t+2; negatives need
t+2 <= the cell's last clear look that season; only the first burn per cell-season counts, later days are masked.

Burn evidence per cell-season:
  season windows : research thread's burn_windows.csv (burned=1), fire in (ws, we]
  event windows  : per-alert event scars (fire-alert-scars), cell overlap >= 0.5 ha and cell centre within 1.5 km of the
                   event's alert point; fire in (pre_date, post_date]
  dated          : a VIIRS alert point within 400 m of the cell centre (FIRMS 2017-26 + FSI's own 2025-26 points) on day d,
                   with scar evidence in that cell (event scar >= 0.5 ha, or a season/event window with ws-1 <= d <= we+1)
First burn = earliest of: dated days and windows (a window counts at its end; a dated day inside/before it dates it).
Variants (columns pos_<v>, valid_<v>):
  main      : SCORING.md rule (season windows only, window days positive)
  union     : season + event windows, window days positive (more scars found, no better dating)
  dstrict   : union evidence; dated first burns positive on d-2, d-1 only, rest of their window masked;
              undated first burns masked entirely
  dlenient  : as dstrict, but undated first burns keep the window rule
Output: labels_v3.parquet (season, date, cell_id, pos_*, valid_*, first_kind, fire_day)."""
import json, numpy as np, pandas as pd, pyproj
from shapely.geometry import shape, box
import warnings; warnings.filterwarnings('ignore', category=DeprecationWarning)
from shapely.ops import transform as stransform
from shapely.strtree import STRtree
LAB = '/mnt/project-files/research/ratapani-burn-labels/'; RP = '/mnt/project-files/ratapani/'; FA = '/mnt/project-files/fire-alert-scars/'
OUT = RP + 'labels_v3/'; H = 2; n = 3614; SEAS = list(range(2017, 2027))
G = json.load(open(RP + 'grid_500m.geojson'))['features']
xy = np.zeros((n, 2)); cells = [None] * n
for f in G:
    p = f['properties']; c = p['cell_id']; xy[c] = (p['x0'] + 250, p['y0'] + 250); cells[c] = box(p['x0'], p['y0'], p['x0'] + 500, p['y0'] + 500)
tree = STRtree(cells)
utm = pyproj.Transformer.from_crs(4326, 32643, always_xy=True)
def season_of(d): return np.where(d.dt.month >= 8, d.dt.year + 1, d.dt.year)
# ---- event windows ----
ev = [(f['properties'], f['geometry']) for f in json.load(open(FA + 'event_scars.geojson'))['features']]
fe = pd.read_csv(FA + 'fsi/fsi_alert_events.csv'); fe = fe[fe.status.isin(['scar', 'scar_faint']) & fe.geometry.notna()]
ev += [(r._asdict(), json.loads(r.geometry)) for r in fe.itertuples()]
rows = []
for p, g in ev:
    if p.get('status') not in ('scar', 'scar_faint') or not isinstance(p.get('pre_date'), str): continue
    g = stransform(utm.transform, shape(g)); ex, ey = utm.transform(p['lon'], p['lat'])
    for j in tree.query(g):
        a = g.intersection(cells[j]).area / 1e4
        if a >= 0.5 and np.hypot(*(xy[j] - (ex, ey))) <= 1500:
            rows.append((p['event_id'], int(j), a, pd.Timestamp(p['pre_date']), pd.Timestamp(p['post_date']), pd.Timestamp(p['date'])))
ew = pd.DataFrame(rows, columns=['event_id', 'cell_id', 'ha', 'ws', 'we', 'alert_day']).drop_duplicates(['event_id', 'cell_id'])
ew['season'] = season_of(ew.alert_day); ew['src'] = 'event'
print('event-scar cell links', len(ew), flush=True)
# ---- season windows ----
bw = pd.read_csv(LAB + 'burn_windows.csv', parse_dates=['window_start', 'window_end']); bw = bw[bw.burned == 1]
sw = bw.rename(columns={'window_start': 'ws', 'window_end': 'we'})[['season', 'cell_id', 'ws', 'we']].assign(src='season')
win = pd.concat([sw, ew[['season', 'cell_id', 'ws', 'we', 'src']]], ignore_index=True)
# ---- dating points: VIIRS alerts ----
al = pd.read_csv(FA + 'alert_scar_lookup.csv', parse_dates=['acq_date']); al = al[al.sensor.str.startswith('viirs')][['latitude', 'longitude', 'acq_date', 'event_id']]
fa = pd.read_csv(FA + 'fsi/fsi_alert_scar_lookup.csv', parse_dates=['acq_date']); fa = fa[fa.sensor.astype(str).str.lower().str.contains('viirs')][['latitude', 'longitude', 'acq_date', 'event_id']]
pts = pd.concat([al, fa], ignore_index=True)
px, py = utm.transform(pts.longitude.values, pts.latitude.values)
from scipy.spatial import cKDTree
kd = cKDTree(xy); near = kd.query_ball_point(np.c_[px, py], 400)
dp = pd.DataFrame([(i, c) for i, cs in enumerate(near) for c in cs], columns=['i', 'cell_id'])
dp['d'] = pts.acq_date.values[dp.i]; dp['event_id'] = pts.event_id.values[dp.i]; dp['season'] = season_of(dp.d)
# scar evidence in the cell: own event scar in the cell, or any window bracketing d (+-1 day)
own = dp.merge(ew[['event_id', 'cell_id']].assign(own=1), on=['event_id', 'cell_id'], how='left').own.fillna(0).values > 0
wm = dp[['i', 'cell_id', 'season', 'd']].merge(win[['season', 'cell_id', 'ws', 'we']], on=['season', 'cell_id'])
br = wm[(wm.d >= wm.ws - pd.Timedelta(days=1)) & (wm.d <= wm.we + pd.Timedelta(days=1))][['i', 'cell_id']].drop_duplicates().assign(br=1)
dp = dp.merge(br, on=['i', 'cell_id'], how='left'); dp['ok'] = own | (dp.br.fillna(0).values > 0)
dated = dp[dp.ok].groupby(['season', 'cell_id']).d.min().rename('d').reset_index()
print('dated cell-seasons', len(dated), flush=True)
ew.to_csv(OUT + 'event_windows.csv', index=False); sw.to_csv(OUT + 'season_windows.csv', index=False); dated.to_csv(OUT + 'dated_cells.csv', index=False)
cc = pd.read_parquet(LAB + 'clear_calendar.parquet'); cc['date'] = pd.to_datetime(cc['date'])
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days); d0 = days[0]
    last = cc[(cc.season == Y) & (cc.clear_frac >= 0.5)].groupby('cell_id').date.max().reindex(range(n))
    lim = ((last - d0).dt.days - H).values
    base_valid = np.zeros((T, n), bool)
    for c in range(n):
        if np.isfinite(lim[c]) and lim[c] >= 0: base_valid[:int(min(lim[c], T - 1)) + 1, c] = True
    V = {v: base_valid.copy() for v in ('main', 'union', 'dstrict', 'dlenient')}; P = {v: np.zeros((T, n), bool) for v in V}
    kind = np.zeros(n, np.int8); fday = np.full(n, np.datetime64('NaT', 'ns'))   # 0 none, 1 dated, 2 undated window
    wY = win[win.season == Y]; dY = dated[dated.season == Y].set_index('cell_id').d
    def window_rule(v, c, s, e, positive):
        a, b = (s - d0).days - H + 1, (e - d0).days - 1
        a0, b0 = max(a, 0), min(b, T - 1)
        if b0 >= a0: P[v][a0:b0 + 1, c] = positive; V[v][a0:b0 + 1, c] = positive
        ei = (e - d0).days
        if ei <= T - 1: V[v][max(ei, 0):, c] = False; P[v][max(ei, 0):, c] = False
    def dated_rule(v, c, d, s=None, e=None):
        if s is not None:   # mask the rest of the dated window
            a, b = max((s - d0).days - H + 1, 0), min((e - d0).days - 1, T - 1)
            if b >= a: V[v][a:b + 1, c] = False
        fi = (d - d0).days
        if fi <= T - 1: V[v][max(fi, 0):, c] = False
        a0, b0 = max(fi - H, 0), min(fi - 1, T - 1)
        if b0 >= a0: P[v][a0:b0 + 1, c] = True; V[v][a0:b0 + 1, c] = True
    for c, g in wY.groupby('cell_id'):
        gs = g[g.src == 'season'].sort_values('we')
        if len(gs): window_rule('main', c, gs.ws.iloc[0], gs.we.iloc[0], True)
        g = g.sort_values('we'); s, e = g.ws.iloc[0], g.we.iloc[0]
        window_rule('union', c, s, e, True)
        d = dY.get(c)
        if d is not None and d <= e + pd.Timedelta(days=1):
            kind[c] = 1; fday[c] = d
            for v in ('dstrict', 'dlenient'): dated_rule(v, c, d, s if d > s else None, e if d > s else None)
        else:
            kind[c] = 2
            window_rule('dstrict', c, s, e, False); window_rule('dlenient', c, s, e, True)
    for c, d in dY.items():          # dated but no window at all (should be rare: dated needs scar evidence)
        if kind[c] == 0:
            kind[c] = 1; fday[c] = d
            for v in ('dstrict', 'dlenient'): dated_rule(v, c, d)
    allv = np.zeros((T, n), bool)
    for v in V: allv |= V[v]
    ti, ci = np.nonzero(allv)
    df = pd.DataFrame(dict(season=Y, date=days[ti], cell_id=ci))
    for v in V: df['pos_' + v] = P[v][ti, ci]; df['valid_' + v] = V[v][ti, ci]
    df['first_kind'] = kind[ci]; df['fire_day'] = fday[ci]
    frames.append(df)
    msg = ' '.join(f"{v}: pos {int((P[v] & V[v]).sum())} valid {int(V[v].sum())}" for v in V)
    print(Y, 'dated', int((kind == 1).sum()), 'undated', int((kind == 2).sum()), '|', msg, flush=True)
lab = pd.concat(frames, ignore_index=True)
lab.to_parquet(OUT + 'labels_v3.parquet', index=False); print('saved', len(lab))
