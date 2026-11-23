"""Tables for the fair comparison (fair_table.py scores): per truth, method and budget, pooled hit rates (detections within 240 m of the
forecast) with 95% intervals from 500 fire bootstraps, split by horizon and by elapsed time since the first detection; end-outline Sorensen,
precision and recall at each budget; snapshot precision/recall at each budget by lead; differences against persistence at the same budget.
  python3 fair_summary.py 'data/fair_score_[0-3].parquet' out.json
"""
import numpy as np, pandas as pd, sys, json, glob
rng = np.random.default_rng(11); NB = 500


def boot_ratio(d, num, den, nb=NB):
    ev = d.event.values; ids = np.unique(ev); g = d.groupby('event')[[num, den]].sum()
    a, b = g[num].values, g[den].values; vals = []
    for _ in range(nb):
        i = rng.integers(0, len(a), len(a)); vals.append(a[i].sum() / max(b[i].sum(), 1))
    return float(a.sum() / max(b.sum(), 1)), [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def boot_mean(d, col, nb=NB):
    g = d.groupby('event')[col].mean().values; vals = [g[rng.integers(0, len(g), len(g))].mean() for _ in range(nb)]
    return float(g.mean()), [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def main(pat, out):
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(pat))], ignore_index=True)
    d['elapsed_bin'] = pd.cut(d.elapsed_h, [-1, 0.01, 12, 24, 48], labels=['first pass', '0-12 h', '12-24 h', '24-48 h'])
    res = dict(n_fires=int(d.event.nunique()), n_steps=int(d.groupby(['event', 'k']).ngroups))
    # (a) detections within the horizon
    H = {}
    for truth in ['h6', 'h12', 'h24', 'h48']:
        q = d[(d.truth == truth) & (d.n_det > 0)]
        if not len(q):
            continue
        T = dict(n_steps=int(q.groupby(['event', 'k']).ngroups), n_det=int(q[q.method == 'pers'].drop_duplicates(['event', 'k']).n_det.sum()),
                 n_new=int(q[q.method == 'pers'].drop_duplicates(['event', 'k']).n_new.sum()))
        for bud in q.budget.unique():
            for meth in q.method.unique():
                qq = q[(q.budget == bud) & (q.method == meth)]
                if not len(qq):
                    continue
                r, ci = boot_ratio(qq, 'hit', 'n_det'); rn, cin = boot_ratio(qq, 'hitnew', 'n_new')
                T[f'{meth}|{bud}'] = dict(hit=r, hit_ci=ci, hitnew=rn, hitnew_ci=cin, area_ha=float(qq.n_px.median() * 0.04), n=len(qq))
            # differences vs persistence by fire bootstrap
            base = q[(q.budget == bud) & (q.method == 'pers')].set_index(['event', 'k'])
            for meth in q.method.unique():
                if meth == 'pers':
                    continue
                qq = q[(q.budget == bud) & (q.method == meth)].set_index(['event', 'k'])
                j = qq[['hit', 'n_det']].join(base[['hit']].rename(columns={'hit': 'hit_pers'}), how='inner').reset_index()
                if len(j):
                    g = j.groupby('event')[['hit', 'hit_pers', 'n_det']].sum(); diffs = []
                    for _ in range(NB):
                        i = rng.integers(0, len(g), len(g)); diffs.append((g.hit.values[i].sum() - g.hit_pers.values[i].sum()) / max(g.n_det.values[i].sum(), 1))
                    T[f'{meth}|{bud}']['minus_pers_ci'] = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
        # by elapsed time, persistence budget
        T['by_elapsed_pers_budget'] = {}
        for eb, qe in q[q.budget == 'pers'].groupby('elapsed_bin', observed=True):
            T['by_elapsed_pers_budget'][str(eb)] = {meth: boot_ratio(qe[qe.method == meth], 'hit', 'n_det')[0] for meth in qe.method.unique()}
            T['by_elapsed_pers_budget'][str(eb)]['n_det'] = int(qe[qe.method == 'pers'].n_det.sum())
        H[truth] = T
    res['horizons'] = H
    # (b) end outline
    q = d[d.truth == 'end']; E = {}
    for bud in q.budget.unique():
        for meth in q.method.unique():
            qq = q[(q.budget == bud) & (q.method == meth)]
            if len(qq):
                s, ci = boot_mean(qq, 'sor'); E[f'{meth}|{bud}'] = dict(sor=s, sor_ci=ci, prec=float(qq.prec.mean()), rec=float(qq.rec.mean()), n=len(qq))
    E['by_elapsed_truth_budget'] = {}
    for eb, qe in q[q.budget == 'truth'].groupby('elapsed_bin', observed=True):
        E['by_elapsed_truth_budget'][str(eb)] = {meth: float(qe[qe.method == meth].sor.mean()) for meth in qe.method.unique()}
        E['by_elapsed_truth_budget'][str(eb)]['n'] = int(qe[qe.method == 'pers'].shape[0])
    E['last_pass_truth_budget'] = {meth: float(v.sor.mean()) for meth, v in q[(q.budget == 'truth') & (q.k == q.n_pass)].groupby('method')}
    res['end'] = E
    # (c) snapshots
    q = d[d.truth == 'snap']
    if len(q):
        q = q.copy(); q['lead_bin'] = pd.cut(q.lead_h, [0, 6, 12, 24, 48], labels=['0-6 h', '6-12 h', '12-24 h', '24-48 h']); SN = dict(n_scenes=int(q.drop_duplicates(['event', 'k', 'scene']).shape[0]))
        for bud in q.budget.unique():
            for meth in q.method.unique():
                qq = q[(q.budget == bud) & (q.method == meth)]
                if len(qq):
                    SN[f'{meth}|{bud}'] = dict(prec=float(qq.prec.mean()), rec=float(qq.rec.mean()), sor=float(qq.sor.mean()), n=len(qq))
        SN['by_lead_truth_budget'] = {str(lb): {meth: float(v.sor.mean()) for meth, v in qq.groupby('method')} for lb, qq in q[q.budget == 'truth'].groupby('lead_bin', observed=True)}
        res['snap'] = SN
    json.dump(res, open(out, 'w'), indent=1)
    # print the headline table: persistence budget and 25 ha budget, by horizon
    for truth, T in H.items():
        print(truth, 'steps', T['n_steps'], 'dets', T['n_det'], 'new', T['n_new'])
        for bud in ['pers', '25ha', '100ha']:
            print('  ', bud, {k.split('|')[0]: f"{v['hit']:.3f}" for k, v in T.items() if '|' in k and k.endswith('|' + bud)})
    print('end, truth budget:', {k.split('|')[0]: round(v['sor'], 3) for k, v in E.items() if '|' in k and k.endswith('|truth')})
    print('end, last pass:', {k: round(v, 3) for k, v in E['last_pass_truth_budget'].items()})


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
