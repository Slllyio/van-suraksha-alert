import pandas as pd, numpy as np, glob, sys
d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f'/tmp/claude-0/spread/data/{sys.argv[1]}_[0-9].parquet'))])
print(f'{len(d)} forecast steps in {d.event.nunique()} fires; median lead {d.lead_h.median():.1f} h; target detections {d.n_target.sum()}, on new ground {d.n_new.sum()}')
for lab, col, n in [('all target detections', 'hit', 'n_target'), ('new ground only (>400 m from earlier detections)', 'hitnew', 'n_new')]:
    N = d[n].sum()
    print(f'  {lab}: free run {d[col+"_free"].sum()/N:.1%} | circle (free) {d[col+"_cfree"].sum()/N:.1%} | restart {d[col+"_rs"].sum()/N:.1%} | circle (restart) {d[col+"_crs"].sum()/N:.1%} | persistence 375 m {d[col+"_pers"].sum()/N:.1%}')
print(f'  forecast area (ha) median: free {d.area_free.median()*0.04:.0f}, restart {d.area_rs.median()*0.04:.0f}, persistence {d.area_pers.median()*0.04:.0f}')
e = d.dropna(subset=['sor_free_end'])
print(f'  end footprint vs scar (n={len(e)}): Sorensen free {e.sor_free_end.mean():.3f} vs restart-all {e.sor_rs_end.mean():.3f}; area ratio free {np.median(e.area_free_end/e.scar_px):.2f} vs restart {np.median(e.area_rs_end/e.scar_px):.2f}')
# by lead time to the next pass (multi-sensor passes give short leads where persistence is trivial)
d['lead_bin'] = pd.cut(d.lead_h, [0, 3, 9, 18, 100], labels=['<3 h', '3-9 h', '9-18 h', '>18 h'])
for b, s in d.groupby('lead_bin', observed=True):
    N = s.n_target.sum(); Nn = s.n_new.sum()
    print(f'  lead {b} (steps {len(s)}, targets {N}): free {s.hit_free.sum()/N:.1%} | circle {s.hit_cfree.sum()/N:.1%} | restart {s.hit_rs.sum()/N:.1%} | circle-rs {s.hit_crs.sum()/N:.1%} | persist {s.hit_pers.sum()/N:.1%}'
          + (f' || new ground ({Nn}): restart {s.hitnew_rs.sum()/Nn:.1%} | circle-rs {s.hitnew_crs.sum()/Nn:.1%} | persist {s.hitnew_pers.sum()/Nn:.1%}' if Nn else ''))
