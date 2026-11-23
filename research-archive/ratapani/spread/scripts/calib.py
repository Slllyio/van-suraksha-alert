"""Audit item 2: chances you can trust. From fair_table.py's calibration lattice (fair_score_*_cal.parquet): for each method and horizon,
probabilities calibrated by isotonic regression fitted on the OTHER seasons' held-out predictions (nothing from the scored season), then
Brier score (raw and calibrated), reliability table (10 bins), AUC, average precision, precision at 50% / 80% recall, all with 95%
intervals from 500 bootstrap draws of fires. Persistence gets the same treatment as a probability: P(label | distance to known detections)
fitted the same way, so "learned vs persistence" compares two calibrated maps.
  python3 calib.py 'data/fair_score_[0-3]_cal.parquet' out.json
"""
import numpy as np, pandas as pd, sys, json, glob
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve
HOR = [6, 12, 24, 48]; NB = 500; rng = np.random.default_rng(7)


def cross_season_iso(d, col, lab, score_sign=1.0):
    """calibrated probability per row: isotonic fit on rows of all other seasons"""
    out = np.full(len(d), np.nan)
    x = d[col].values * score_sign; y = d[lab].values; s = d.season.values
    for se in np.unique(s):
        tr = (s != se) & (s <= 2024)      # 2025-26 (forward test) calibrated on 2017-24 held-out predictions only
        if y[tr].sum() == 0 or len(np.unique(y[tr])) < 2:
            continue
        iso = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(x[tr], y[tr])
        out[s == se] = iso.predict(x[s == se])
    return out


def metrics(y, p, w=None):
    m = dict(n=int(len(y)), base=float(y.mean()), brier=float(np.mean((p - y) ** 2)))
    if 0 < y.sum() < len(y):
        m['auc'] = float(roc_auc_score(y, p)); m['ap'] = float(average_precision_score(y, p))
        pr, rc, _ = precision_recall_curve(y, p)
        m['prec_at_rec50'] = float(pr[rc >= 0.5].max()); m['prec_at_rec80'] = float(pr[rc >= 0.8].max())
    return m


def reliability(y, p, nb=10):
    b = np.clip((p * nb).astype(int), 0, nb - 1); rows = []
    for k in range(nb):
        m = b == k
        if m.sum():
            rows.append(dict(bin=k, n=int(m.sum()), pred=float(p[m].mean()), obs=float(y[m].mean())))
    return rows


def boot(d, y, p, q, fn, nb=NB):
    """fire-level bootstrap of fn(y, p) - fn(y, q) and of fn(y, p)"""
    ev = d.event.values; ids = np.unique(ev); idx = {e: np.nonzero(ev == e)[0] for e in ids}
    vals, diffs = [], []
    for _ in range(nb):
        pick = rng.choice(ids, len(ids), replace=True); ii = np.concatenate([idx[e] for e in pick])
        yy, pp, qq = y[ii], p[ii], q[ii]
        a, b = fn(yy, pp), fn(yy, qq); vals.append(a); diffs.append(a - b)
    return [float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))], [float(np.nanpercentile(diffs, 2.5)), float(np.nanpercentile(diffs, 97.5))]


FAR_M = 475.0


def main(pat, out, score_pat=None):
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(pat))], ignore_index=True)
    if score_pat:          # fire age at issue time, from the fair table's score rows (one elapsed_h per event and pass)
        sc = pd.concat([pd.read_parquet(f, columns=['event', 'k', 'elapsed_h']) for f in sorted(glob.glob(score_pat))], ignore_index=True).drop_duplicates(['event', 'k'])
        d = d.merge(sc, on=['event', 'k'], how='left')
    print('rows', len(d), 'fires', d.event.nunique(), 'steps', d.groupby(['event', 'k']).ngroups, flush=True)
    res = {}
    brier = lambda y, p: float(np.mean((p - y) ** 2))
    auc = lambda y, p: float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else np.nan
    ap = lambda y, p: float(average_precision_score(y, p)) if y.sum() > 0 else np.nan
    for truth in [f'h{h}' for h in HOR] + ['end']:
        lab = f'y_{truth}'
        q = d if truth == 'end' else d[d[f'nop_{truth}'] >= 1]
        q = q[q[lab].notna()].copy()
        if not len(q):
            continue
        y = q[lab].values.astype(float)
        q['p_pers_cal'] = cross_season_iso(q, 'd_all', lab, -1.0)
        q['p_phys_cal'] = cross_season_iso(q, 't_phys', lab, -1.0)
        if 'd_last' in q:
            q['ring_score'] = -np.abs(q.d_last - 600.0); q['p_ring_cal'] = cross_season_iso(q, 'ring_score', lab)
        meths = [c for c in q.columns if c.startswith('p_') and not c.endswith('_cal') and (c.endswith(f'_{truth[1:]}') if truth != 'end' else (c.endswith('_end') or c == 'p_lfoot'))]
        R = {}
        far = q.d_all.values > FAR_M        # beyond the persistence ring: the FSI thread's warning that the previous footprint inflates scores
        age = q.elapsed_h.values if 'elapsed_h' in q else None
        def by_age(yv, pv, okv):
            if age is None: return None
            out = {}
            for lo, hi in [(0, 6), (6, 12), (12, 24), (24, 48), (48, 1e9)]:
                m = okv & (age >= lo) & (age < hi)
                if m.sum() > 200 and 0 < yv[m].sum() < m.sum():
                    out[f'{lo}-{int(hi) if hi < 1e9 else "inf"}h'] = dict(n=int(m.sum()), base=float(yv[m].mean()), brier=float(np.mean((pv[m] - yv[m]) ** 2)), auc=float(roc_auc_score(yv[m], pv[m])))
            return out
        for base in ['pers', 'phys'] + (['ring'] if 'p_ring_cal' in q else []):
            pc = q[f'p_{base}_cal'].values; ok = np.isfinite(pc)
            R[base] = dict(calibrated=metrics(y[ok], pc[ok]), reliability=reliability(y[ok], pc[ok]), beyond_475m=metrics(y[ok & far], pc[ok & far]) if (ok & far).sum() > 100 else None,
                           by_age=by_age(y, pc, ok))
        for c in meths:
            praw = q[c].values; pc = cross_season_iso(q, c, lab); ok = np.isfinite(pc)
            r = dict(raw=metrics(y, praw), calibrated=metrics(y[ok], pc[ok]), reliability_raw=reliability(y, praw), reliability_cal=reliability(y[ok], pc[ok]),
                     beyond_475m=metrics(y[ok & far], pc[ok & far]) if (ok & far).sum() > 100 else None, by_age=by_age(y, pc, ok))
            qq = q[ok]; pp = q.loc[ok, f'p_pers_cal'].values; okp = np.isfinite(pp)
            if okp.sum() > 100:
                yy, pcc, ppc = y[ok][okp], pc[ok][okp], pp[okp]
                r['brier_ci'], r['brier_minus_pers_ci'] = boot(qq[okp], yy, pcc, ppc, brier)
                r['auc_ci'], r['auc_minus_pers_ci'] = boot(qq[okp], yy, pcc, ppc, auc)
                r['ap_ci'], r['ap_minus_pers_ci'] = boot(qq[okp], yy, pcc, ppc, ap)
            R[c[2:]] = r
            print(truth, c, {k: round(v, 4) for k, v in r['calibrated'].items() if isinstance(v, float)}, flush=True)
        res[truth] = R
    json.dump(res, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
