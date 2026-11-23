"""FSI large-forest-fire archive (fsi_portal/lff_mp.csv): growth of the detection bounding box over the
event's duration, for events inside our Ratapani grid; and a match to our VIIRS S-NPP events.
Usage: fsi_growth.py [out.parquet]"""
import numpy as np, pandas as pd, sys
from pyproj import Transformer
import sim
f = pd.read_csv('/mnt/project-files/ratapani/fsi/fsi_portal/lff_mp.csv')
for c in ('F_T_D', 'L_T_D'):
    f[c] = pd.to_datetime(f[c], format='%Y%m%d_%H%M')
tr = Transformer.from_crs(4326, 32643, always_xy=True)
x0, y0 = tr.transform(f.EXT_MIN_X.values, f.EXT_MIN_Y.values); x1, y1 = tr.transform(f.EXT_MAX_X.values, f.EXT_MAX_Y.values)
f['x0'], f['y0'], f['x1'], f['y1'] = x0, y0, x1, y1
f['ix'], f['iy'] = tr.transform(f.INSIDE_X.values, f.INSIDE_Y.values)
f['dur_h'] = (f.L_T_D - f.F_T_D).dt.total_seconds() / 3600
f['w_m'], f['h_m'] = f.x1 - f.x0, f.y1 - f.y0
f['ext_m'] = np.hypot(f.w_m, f.h_m)            # bbox diagonal
f['bbox_ha'] = f.w_m * f.h_m / 1e4
f['season'] = np.where(f.F_T_D.dt.month >= 11, f.F_T_D.dt.year + 1, f.F_T_D.dt.year)
X0, Y0 = sim.X0, sim.Y0; X1, Y1 = X0 + sim.WC.shape[1] * sim.RES, Y0 - sim.WC.shape[0] * sim.RES
r = f[(f.ix > X0) & (f.ix < X1) & (f.iy < Y0) & (f.iy > Y1)].copy()
print(f'FSI large fires in MP {len(f)}; inside our Ratapani grid {len(r)} ({r.season.min()}-{r.season.max()}); divisions: {r.DIVISION.value_counts().head(4).to_dict()}')
q = lambda s: ' / '.join(f'{v:.0f}' for v in s.quantile([.25, .5, .75]))
print(f'  duration h (q25/50/75): {q(r.dur_h)}; bbox diagonal m: {q(r.ext_m)}; bbox ha: {q(r.bbox_ha)}')
print(f'  fires with duration >= 12 h: {(r.dur_h >= 12).mean():.0%}; >= 24 h: {(r.dur_h >= 24).mean():.0%}; >= 48 h: {(r.dur_h >= 48).mean():.0%}')
m = r[r.dur_h >= 6]
print(f'  bbox diagonal growth, fires lasting >= 6 h (n={len(m)}): median {np.median(m.ext_m / m.dur_h):.0f} m per h of duration; q25-q75 {q(m.ext_m / m.dur_h)}')
for lo, hi in [(6, 18), (18, 36), (36, 72), (72, 400)]:
    s = r[(r.dur_h >= lo) & (r.dur_h < hi)]
    print(f'    duration {lo}-{hi} h (n={len(s)}): bbox diagonal median {s.ext_m.median():.0f} m, bbox {s.bbox_ha.median():.0f} ha')
# match to our S-NPP events: FSI bbox (buffered 1 km) contains the event centroid and times overlap (+-12 h)
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet')
g = v.groupby('event').agg(x=('x', 'mean'), y=('y', 'mean'), t0=('t', 'min'), t1=('t', 'max'), n=('x', 'size'), p=('overpass', 'nunique'),
                           ex=('x', lambda s: s.max() - s.min()), ey=('y', lambda s: s.max() - s.min()))
g['ext_m'] = np.hypot(g.ex, g.ey)
rows = []
for e, ge in g.iterrows():
    c = r[(r.x0 - 1000 < ge.x) & (r.x1 + 1000 > ge.x) & (r.y0 - 1000 < ge.y) & (r.y1 + 1000 > ge.y) &
          (r.F_T_D < ge.t1 + pd.Timedelta(hours=12)) & (r.L_T_D > ge.t0 - pd.Timedelta(hours=12))]
    if len(c):
        c = c.iloc[(np.hypot(c.ix - ge.x, c.iy - ge.y)).argmin()]
        rows.append(dict(event=e, fsi_name=c.N_F_Name, fsi_first=c.F_T_D, fsi_last=c.L_T_D, fsi_dur_h=c.dur_h, fsi_ext_m=c.ext_m, fsi_bbox_ha=c.bbox_ha,
                         our_t0=ge.t0, our_t1=ge.t1, our_dur_h=(ge.t1 - ge.t0).total_seconds() / 3600, our_ext_m=ge.ext_m, our_n=ge.n, our_p=ge.p))
mt = pd.DataFrame(rows)
print(f'matched {len(mt)} of our {len(g)} S-NPP events (2019+ only possible: {len(g[g.t0.dt.year >= 2019])}) to FSI large fires')
print(f'  FSI duration vs ours (h), median: {mt.fsi_dur_h.median():.0f} vs {mt.our_dur_h.median():.0f}; FSI first detection earlier than ours by median {((mt.our_t0 - mt.fsi_first).dt.total_seconds() / 3600).median():.1f} h')
print(f'  FSI bbox diagonal vs our detection extent (m), median: {mt.fsi_ext_m.median():.0f} vs {mt.our_ext_m.median():.0f}')
mt.to_parquet(sys.argv[1] if len(sys.argv) > 1 else f'{sim.DATA}/fsi_match.parquet')
