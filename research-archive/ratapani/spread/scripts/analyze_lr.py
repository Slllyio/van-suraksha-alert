"""Summarise the learned restart (foot_restart.py score output) -> data/lr_stats.json and a printed table."""
import pandas as pd, numpy as np, glob, json, sys
D = '/tmp/claude-0/spread/data'
d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f'{D}/lr_score_[0-3].parquet'))], ignore_index=True)
st = d[d.lead_h.notna()].copy(); end = d[d.lead_h.isna() & d.scar_px.ge(25)].copy()
out = dict(n_fires=int(d.event.nunique()), n_steps=len(st), n_end=len(end), median_lead_h=float(st.lead_h.median()),
           median_area_pers_ha=float(st.area_pers.median() * 0.04), median_area_exp_ha=float(st.area_exp.median() * 0.04))
def rates(s):
    r = {}
    for nm in ['pers', 'learn', 'lscar', 'dist', 'learn_h', 'dist_h', 'learn_e', 'dist_e']:
        r[nm] = round(100 * s[f'hit_{nm}'].sum() / s.n_target.sum(), 1)
        r[f'new_{nm}'] = round(100 * s[f'hitnew_{nm}'].sum() / max(s.n_new.sum(), 1), 1)
    r['n_target'] = int(s.n_target.sum()); r['n_new'] = int(s.n_new.sum()); r['steps'] = len(s)
    r['auc_next'] = round(float(s.auc_next.mean()), 3); r['auc_dist'] = round(float(s.auc_dist.mean()), 3)
    return r
out['all'] = rates(st)
st['band'] = pd.cut(st.lead_h, [0, 3, 9, 18, 72], labels=['<3 h', '3-9 h', '9-18 h', '>18 h'])
out['by_lead'] = {str(b): rates(g) for b, g in st.groupby('band', observed=True)}
out['by_k'] = {int(k): rates(g) for k, g in st.groupby(st.k.clip(upper=4))}
out['end'] = dict(n=len(end), sor_learn=round(float(end.sor_learn_end.mean()), 3), sor_dist=round(float(end.sor_dist_end.mean()), 3), sor_pers=round(float(end.sor_pers_end.mean()), 3),
                  sor_learn_free=round(float(end.sor_learn_free.mean()), 3), sor_dist_free=round(float(end.sor_dist_free.mean()), 3),
                  learn_better_share=round(float((end.sor_learn_end > end.sor_dist_end).mean()), 3), auc_scar=round(float(end.auc_scar.mean()), 3),
                  median_area_exp_ha=float(end.area_exp_scar.median() * 0.04), median_scar_ha=float(end.scar_px.median() * 0.04), median_area_pers_ha=float(end.area_pers_end.median() * 0.04))
out['end_by_season'] = {int(s): dict(n=len(g), learn=round(float(g.sor_learn_end.mean()), 3), dist=round(float(g.sor_dist_end.mean()), 3)) for s, g in end.groupby('season')}
json.dump(out, open(f'{D}/lr_stats.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
