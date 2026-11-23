"""Per-pixel burn date variants. The variant is chosen on the TRAINING alert chips (VIIRS first detection within 400 m as the
reference), then scored once on the test chips (Wayback + FIRMS fire-pixel chips vs VIIRS; mid-fire photos).
Variants: first look with a persistent drop >= thr (thr 0.08 / 0.12 / 0.16), or the look with the largest persistent step.
Out: results/C_dating_variants_train.csv, results/C_dating_test.csv, results/C_dating_photo.json"""
import json, os, warnings, numpy as np, pandas as pd, datetime as dt
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
from lib import CODE, SCR, RES, alerts, best_looks, idx, prepare, features, static_layers, patches
warnings.filterwarnings('ignore')
OUT = CODE + 'results/'
C = pd.read_csv(CODE + 'chips.csv').set_index('chip'); V = alerts(); V = V[V.viirs]


def series(st, ex):
    ds, ii = best_looks(st, ex); nb = []
    for i in ii:
        v = idx(st['X'][i])['nbr']; ok = np.isfinite(v)
        nb.append(v - np.nanmedian(v[ok]) if ok.sum() > 200 else np.full_like(v, np.nan))
    return np.array([dt.date.fromisoformat(d).toordinal() for d in ds], float), np.stack(nb)


def date_px(days, S, how, thr=0.08, keep=0.6):
    """S: (T, m) chip-relative NBR. Returns U, L per pixel."""
    T, m = S.shape; fin = np.isfinite(S); o = np.argsort(~fin, axis=0, kind='stable')
    Vv = np.take_along_axis(S, o, 0); Dd = days[o]; cnt = fin.sum(0)
    u = np.full(m, np.nan); l = np.full(m, np.nan); found = np.zeros(m, bool); best = np.full(m, -9.0)
    for k in range(1, T):
        base = np.nanmedian(Vv[max(0, k - 3):k], axis=0)
        after = np.nanmedian(Vv[k:k + 2], axis=0)  # this look and the next: persistence
        nxt = Vv[k + 1] if k + 1 < T else np.full(m, np.nan)
        valid = (k < cnt) & (cnt >= 3)
        if how == 'first':
            hit = (~found) & valid & (base - Vv[k] >= thr) & ((k + 1 >= cnt) | (base - nxt >= keep * thr))
            u[hit] = Dd[k, hit]; l[hit] = Dd[k - 1, hit]; found |= hit
        else:  # largest persistent step
            step = np.where((k + 1 >= cnt), base - Vv[k], np.minimum(base - Vv[k], base - nxt))
            hit = valid & (step > best) & (step >= 0.05)
            best[hit] = step[hit]; u[hit] = Dd[k, hit]; l[hit] = Dd[k - 1, hit]
    return u, l


VARS = [('first', 0.08), ('first', 0.12), ('first', 0.16), ('max', None)]


def viirs_rows(chips, mask_fn, ex_fn):
    rows = []
    for ch in chips:
        c = C.loc[ch]
        if not os.path.exists(f'{SCR}stacks/{ch}.npz'): continue
        r = c.to_dict(); r['chip'] = ch; ex = ex_fn(r); p = prepare(r, ex)
        if p is None: continue
        st = p['st']; tr = st['tr']; n = st['n']; m = mask_fn(ch, p)
        rr, cc = np.where(m)
        if not len(rr): continue
        if len(rr) > 400: k = np.random.default_rng(1).choice(len(rr), 400, replace=False); rr, cc = rr[k], cc[k]
        d0 = pd.Timestamp(c.date)
        v = V[(V.d >= d0 - pd.Timedelta(days=30)) & (V.d <= d0 + pd.Timedelta(days=40)) & (V.x > tr[2] - 500) & (V.x < tr[2] + n * RES + 500) &
              (V.y < tr[5] + 500) & (V.y > tr[5] - n * RES - 500)]
        if not len(v): continue
        X_ = tr[2] + (cc + 0.5) * RES; Y_ = tr[5] - (rr + 0.5) * RES; vd = v.d.map(pd.Timestamp.toordinal).values
        first = np.array([vd[j].min() if len(j) else np.nan for j in cKDTree(v[['x', 'y']].values).query_ball_point(np.c_[X_, Y_], 400)])
        days, S = series(st, ex); S = S[:, rr, cc]
        out = dict(chip=ch, v=first, anchor=float(d0.toordinal()), pre=float(dt.date.fromisoformat(p['pair']['pre']).toordinal()),
                   post=float(dt.date.fromisoformat(p['pair']['post']).toordinal()))
        for how, thr in VARS:
            u, l = date_px(days, S, how, thr or 0.08); tag = f'{how}{thr or ""}'; out[f'U_{tag}'] = u; out[f'L_{tag}'] = l
        rows.append(pd.DataFrame(out))
    return pd.concat(rows).dropna(subset=['v'])


def score(D, tag=None, lo=None, hi=None, est=None):
    if tag: lo, hi = D[f'L_{tag}'], D[f'U_{tag}']; est = (lo + hi) / 2
    e = est - D.v; ok = np.isfinite(e)
    return dict(pixels=int(ok.sum()), dated_share=float(ok.mean()), median_abs_err=float(np.nanmedian(np.abs(e))), within_2d=float((np.abs(e[ok]) <= 2).mean()),
                window_median=float(np.nanmedian(hi - lo)), window_holds_viirs=float(((D.v >= lo) & (D.v <= hi))[ok].mean()))


if __name__ == '__main__':
    # 1) choose on training chips: pixels of the rule scar (the training chips' own map)
    tr_ch = C[C.kind == 'train_alert'].index[:200]
    Dt = viirs_rows(tr_ch, lambda ch, p: p['rule'], lambda r: [])
    T1 = pd.DataFrame([dict(variant=f'{h}{t or ""}', **score(Dt, f'{h}{t or ""}')) for h, t in VARS] +
                      [dict(variant='pair window', **score(Dt, lo=Dt.pre, hi=Dt.post, est=(Dt.pre + Dt.post) / 2))])
    T1.to_csv(OUT + 'C_dating_variants_train.csv', index=False); print(T1.round(3).to_string())
    T1v = T1[T1.variant != 'pair window']; best = T1v.sort_values('within_2d', ascending=False).variant.iloc[0]; print('chosen', best)
    # 2) test chips vs VIIRS, using the learned PU map's pixels (saved in res/)
    te = C[C.kind.isin(['wb_real', 'af_firms'])].index
    Dte = viirs_rows(te, lambda ch, p: np.load(f'{SCR}res/{ch}.npz')['ml_pu'], lambda r: [r['scene_date']] if isinstance(r.get('scene_date'), str) else [])
    Dte.to_parquet(OUT + 'dates_vs_viirs_test.parquet')
    late = (Dte.v - Dte.anchor).abs() >= 3
    rows = []
    for sub, g in (('all pixels', Dte), ('pixel VIIRS day >= 3 d from the chip alert day', Dte[late]), ('pixel VIIRS day within 2 d of alert day', Dte[~late])):
        rows += [dict(subset=sub, method=f'per-pixel ({best})', **score(g, best)),
                 dict(subset=sub, method='current: pair window (pre, post]', **score(g, lo=g.pre, hi=g.post, est=(g.pre + g.post) / 2)),
                 dict(subset=sub, method='alert day of the chip event', **score(g, lo=g.anchor, hi=g.anchor, est=g.anchor))]
    T2 = pd.DataFrame(rows); T2.to_csv(OUT + 'C_dating_test.csv', index=False); print(T2.round(3).to_string())
    # 3) mid-fire photos (photo scene removed): can the per-pixel date say burned-before vs after the photo?
    AL = alerts(); rp = []
    for ch in C[C.kind == 'photo'].index:
        if not os.path.exists(f'{SCR}res/{ch}.npz'): continue
        z = np.load(f'{SCR}res/{ch}.npz')
        if 'S' not in z.files: continue
        m = z['S'] & z['okp']
        if m.sum() < 20: continue
        c = C.loc[ch]; r = c.to_dict(); r['chip'] = ch; p = prepare(r, [c.scene_date])
        if p is None: continue
        st = p['st']; days, S = series(st, [c.scene_date]); rr, cc = np.where(m)
        h, t = (best[:5], float(best[5:])) if best.startswith('first') else ('max', None)
        u, l = date_px(days, S[:, rr, cc], h, t or 0.08)
        T = pd.Timestamp(c['T']); Td = T.normalize().toordinal() + 0.45
        s = np.where(np.isnan(u), np.nan, np.where(u < Td - 0.5, 1.0, np.where(l > Td, 0.0, np.clip((Td - l) / np.maximum(u - l, 1), 0, 1))))
        tr = st['tr']; X_ = tr[2] + (cc + 0.5) * RES; Y_ = tr[5] - (rr + 0.5) * RES
        a = AL[AL.viirs & (AL.d >= T.normalize() - pd.Timedelta(days=3)) & (AL.d <= T.normalize())]
        a = a[(a.d < T.normalize()) | (a.acq_time.astype(int) < T.hour * 100 + T.minute)]
        dmin = cKDTree(a[['x', 'y']].values).query(np.c_[X_, Y_])[0] if len(a) else np.full(len(rr), 9e9)
        rp.append(pd.DataFrame(dict(chip=ch, y=z['bym'][m], s=s, straddle=(l < Td) & (u > Td), dmin=dmin)))
    P = pd.concat(rp); k = P.s.notna()
    au = lambda y, s: float(roc_auc_score(y, s)) if 0 < y.mean() < 1 else None
    res = dict(variant=best, photos=int(P.chip.nunique()), pixels=len(P), burned_by_photo=float(P.y.mean()),
               window_straddles_photo=float(P.straddle[k].mean()), auc_perpixel=au(P.y[k], P.s[k]), auc_viirs_closest_dot=au(P.y[k], -P.dmin[k]))
    json.dump(res, open(OUT + 'C_dating_photo.json', 'w'), indent=1); print(res)
