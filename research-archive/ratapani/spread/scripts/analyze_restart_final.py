import pandas as pd, numpy as np, sys, glob
for v in ['point', 'fp', 'snap']:
    fs = sorted(glob.glob(f'/tmp/claude-0/spread/data/restart_final_{v}_*.parquet'))
    if len(fs) < 4: continue
    d = pd.concat([pd.read_parquet(f) for f in fs]); n = d.n_target.sum(); nn = d.n_new.sum()
    out = {nm: round(100 * d[f'hit_{nm}'].sum() / n, 1) for nm in ['free', 'rs', 'cfree', 'crs', 'pers']}
    outn = {nm: round(100 * d[f'hitnew_{nm}'].sum() / max(nn, 1), 1) for nm in ['free', 'rs', 'cfree', 'crs', 'pers']}
    e = d.dropna(subset=['sor_rs_end'])
    print(f'{v:6s} steps {len(d)} fires {d.event.nunique()} | hits % {out} | new ground % {outn} | area rs/pers {d.area_rs.sum() / d.area_pers.sum():.2f} | end Sorensen free {e.sor_free_end.mean():.3f} rs {e.sor_rs_end.mean():.3f}')
