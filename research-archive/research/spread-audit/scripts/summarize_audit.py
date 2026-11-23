"""Spread audit: summarise the rerun outputs (audit_restart.py, audit_footprint.py, physics score.py runs with and without
scar-snapped ignition) with 95% CIs bootstrapped by fire. Writes ../results/audit_summary.json and copies the per-fire rows."""
import pandas as pd, numpy as np, glob, json, shutil, os
T = '/tmp/sa'; RES = '/mnt/project-files/research/spread-audit/results'; SP = '/mnt/project-files/ratapani/spread/results'
B = 2000; rng = np.random.default_rng(1)


def rate(df, a, b, den):
    g = df.groupby('event')[[a, b, den]].sum(); A, Bv, D = g[a].values, g[b].values, g[den].values
    n = len(g); idx = rng.integers(0, n, (B, n)); ra, rb = A[idx].sum(1) / D[idx].sum(1), Bv[idx].sum(1) / D[idx].sum(1)
    ci = lambda x: [round(100 * np.percentile(x, 2.5), 1), round(100 * np.percentile(x, 97.5), 1)]
    return dict(fires=n, a=round(100 * A.sum() / D.sum(), 1), b=round(100 * Bv.sum() / D.sum(), 1), diff=round(100 * (A.sum() - Bv.sum()) / D.sum(), 1), diff_ci=ci(ra - rb))


def mean(df, a, b):
    d = df[[a, b]].dropna(); A, Bv = d[a].values, d[b].values; n = len(d); idx = rng.integers(0, n, (B, n))
    ci = lambda x: [round(float(np.percentile(x, 2.5)), 3), round(float(np.percentile(x, 97.5)), 3)]
    return dict(fires=n, a=round(float(A.mean()), 3), b=round(float(Bv.mean()), 3), diff=round(float((A - Bv).mean()), 3), diff_ci=ci((A - Bv)[idx].mean(1)))


out = {}
fs = sorted(glob.glob(f'{T}/restart_[0-3].parquet'))
if fs:
    r = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True); r.to_parquet(f'{RES}/audit_restart_steps.parquet')
    saved = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f'{SP}/lrg_score_[0-3].parquet'))]); saved = saved[saved.lead_h.notna()]
    m = r.merge(saved[['event', 'k', 'hit_learn', 'hit_pers']], on=['event', 'k'], suffixes=('', '_saved'))
    o = dict(steps=len(r), reproduced_steps=int(((m.hit_learn == m.hit_learn_saved) & (m.hit_pers == m.hit_pers_saved)).sum()), matched_steps=len(m))
    for nm, sub in [('all', r), ('lead_3h_plus', r[r.lead_h >= 3]), ('lead_over_18h', r[r.lead_h > 18])]:
        o[nm] = dict(learn_vs_pers=rate(sub, 'hit_learn', 'hit_pers', 'n_target'), last_vs_pers=rate(sub, 'hit_last', 'hit_pers', 'n_target'),
                     learn_vs_last=rate(sub, 'hit_learn', 'hit_last', 'n_target'), honest_prev_vs_learn=rate(sub, 'hit_honest_prev', 'hit_learn', 'n_target'),
                     nolean_vs_learn=rate(sub, 'hit_nolean', 'hit_learn', 'n_target'), new_learn_vs_last=rate(sub, 'hitnew_learn', 'hitnew_last', 'n_new'),
                     new_last_vs_pers=rate(sub, 'hitnew_last', 'hitnew_pers', 'n_new'))
    o['share_prev_pixels_unconfirmed'] = round(float(r.drop_duplicates('event').eval('n_prev_unconf / n_prev_px').median()), 3)
    out['restart'] = o
fs = sorted(glob.glob(f'{T}/foot_[0-3].parquet'))
if fs:
    f = pd.concat([pd.read_parquet(x) for x in fs], ignore_index=True); f.to_parquet(f'{RES}/audit_footprint_fires.parquet')
    saved = pd.concat([pd.read_parquet(x) for x in sorted(glob.glob(f'{SP}/foot_score_grown2_[0-3].parquet'))])
    m = f.merge(saved[['event', 'sor_learn', 'sor_circle']].rename(columns={'sor_circle': 'sor_circle_saved'}), on='event')
    out['footprint'] = dict(fires=len(f), reproduced=int((np.isclose(m.sor_orig, m.sor_learn) & np.isclose(m.sor_circle, m.sor_circle_saved)).sum()),
                            orig_vs_circle=mean(f, 'sor_orig', 'sor_circle'), wxp_vs_orig=mean(f, 'sor_wxp', 'sor_orig'), honest_vs_orig=mean(f, 'sor_honest', 'sor_orig'),
                            honest_vs_circle_honest=mean(f, 'sor_honest', 'sor_circle_h'),
                            median_area_ha=dict(truth=float(f.scar_px.median() * .04), orig=float(f.npred_orig.median() * .04), honest=float(f.npred_honest.median() * .04)))
fs = sorted(glob.glob(f'{T}/phys_nosnap_*.parquet'))
if fs:
    ns = pd.concat([pd.read_parquet(x) for x in fs], ignore_index=True); ns.to_parquet(f'{RES}/audit_physics_nosnap.parquet')
    sv = pd.read_parquet(f'{SP}/res_loose_lfi_m2.parquet')
    m = ns.merge(sv, on='event', suffixes=('_ns', '_snap')); m = m[m.sor_model_snap.notna() & m.sor_model_ns.notna()]
    lo = lambda a: a.clip(lower=1)
    out['physics'] = dict(fires=len(m), snap=mean(m, 'sor_model_snap', 'sor_iso_snap'), nosnap=mean(m, 'sor_model_ns', 'sor_iso_ns'),
                          circle_snap_vs_nosnap=mean(m, 'sor_iso_snap', 'sor_iso_ns'), phys_snap_vs_nosnap=mean(m, 'sor_model_snap', 'sor_model_ns'),
                          end_sor_snap_vs_nosnap=mean(m, 'sor_end_snap', 'sor_end_ns'),
                          median_area_ratio_end=dict(snap=round(float((m.area_end_snap / lo(m.scar_px_snap)).median()), 2), nosnap=round(float((m.area_end_ns / lo(m.scar_px_ns)).median()), 2)),
                          median_area_ratio_48h=dict(snap=round(float((m.area48_snap / lo(m.scar_px_snap)).median()), 2), nosnap=round(float((m.area48_ns / lo(m.scar_px_ns)).median()), 2)))
    s0 = glob.glob(f'{T}/phys_snap_0.parquet')
    if s0:
        a = pd.read_parquet(s0[0]).merge(sv, on='event', suffixes=('', '_saved'))
        out['physics']['reproduced_snap_rows'] = dict(n=len(a), same_sor_model=int(np.isclose(a.sor_model.fillna(-1), a.sor_model_saved.fillna(-1)).sum()),
                                                      same_area_end=int((a.area_end == a.area_end_saved).sum()))
json.dump(out, open(f'{RES}/audit_summary.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
