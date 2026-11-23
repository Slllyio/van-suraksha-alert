"""Summaries for tests 2 and 4: photo scores (m3) and hidden looks (m4), paired against VIIRS-only with 95% ranges from
resampling fires. Out: results/photo_summary.csv, results/hidden_summary.csv, results/inside_footprint.csv"""
import os, numpy as np, pandas as pd
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
rng = np.random.default_rng(1)
def boot(D, a, b, B=1000):
    fires = D.fire.unique(); g = {f: i for i, f in enumerate(fires)}; fi = D.fire.map(g).values
    diff = (D[a] - D[b]).values; s = np.bincount(fi, diff, len(fires)); n = np.bincount(fi, None, len(fires))
    out = []
    for _ in range(B):
        c = np.bincount(rng.integers(0, len(fires), len(fires)), minlength=len(fires)); out.append((c * s).sum() / (c * n).sum())
    return np.nanmean(diff), *np.percentile(out, [2.5, 97.5])
X = pd.read_parquet(f'{OUT}/photo_modis.parquet')
rows = []
both = (X.looks_before > 0) & (X.looks_after > 0)
spec = [('reconstruction', 'blend', 'V', ['a_T_real', 'a_M_real', 'a_M_small', 'a2_M_real', 'a2_M_small', 'b_T_real', 'b_M_real', 'b_M_small']),
        ('reconstruction', 'nn', 'V', ['a_M_real', 'a_M_small', 'a2_M_real', 'b_M_real', 'b_M_small']),
        ('forecast', 'base', 'fcV', ['fc_a_real', 'fc_a_small', 'fc_b_real', 'fc_b_small'])]
for kind, meth, ref, vs in spec:
    for v in vs:
        for sub, msk in [('all photos', X.index == X.index), ('photos where MODIS adds a look', X[f'nM_{v}'] > 0), ('look before AND after', both)]:
            D = X[msk & X[f'acc_{meth}_{v}'].notna() & X[f'acc_{meth}_{ref}'].notna()]
            if len(D) < 5: continue
            r = dict(kind=kind, method=meth, variant=v, subset=sub, photos=len(D), acc_ref=D[f'acc_{meth}_{ref}'].mean(), acc=D[f'acc_{meth}_{v}'].mean())
            r['gain'], r['gain_lo'], r['gain_hi'] = boot(D, f'acc_{meth}_{v}', f'acc_{meth}_{ref}')
            r['auc_ref'] = D[f'auc_{meth}_{ref}'].mean(); r['auc'] = D[f'auc_{meth}_{v}'].mean()
            if kind == 'forecast':
                r['auc_dist_ref'] = D[f'auc_dist_{ref}'].mean(); r['auc_dist'] = D[f'auc_dist_{v}'].mean()
            rows.append(r)
P = pd.DataFrame(rows).round(4); P.to_csv(f'{OUT}/photo_summary.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 20); print(P.to_string())
# burned share inside footprints (photo truth), outside earlier VIIRS footprints
fp = []
for nm in ['inV', 'TN_before', 'TD_now', 'AQ_before', 'out']:
    n, b = X.get(f'{nm}_n'), X.get(f'{nm}_b')
    if n is None: continue
    fp.append(dict(where=nm, photos=int((n.fillna(0) > 0).sum()), pixels=int(n.sum()), burned_share=round(b.sum() / max(n.sum(), 1), 3)))
    if f'{nm}_nall' in X: fp.append(dict(where=nm + ' (incl. inside VIIRS)', photos=int((X[f'{nm}_nall'].fillna(0) > 0).sum()), pixels=int(X[f'{nm}_nall'].sum()), burned_share=round(X[f'{nm}_ball'].sum() / max(X[f'{nm}_nall'].sum(), 1), 3)))
FP = pd.DataFrame(fp); FP.to_csv(f'{OUT}/inside_footprint.csv', index=False); print(FP)
print('photos with any MODIS look of each kind:', {c: int((X[c] > 0).sum()) for c in X.columns if c.startswith('nM_')})
if os.path.exists(f'{OUT}/hidden_modis.parquet'):
    H = pd.read_parquet(f'{OUT}/hidden_modis.parquet'); rows = []
    for meth in ['blend', 'nn']:
        for v in ['T_real', 'T_small', 'M_real', 'M_small']:
            for sub, msk in [('all hidden looks', H.index == H.index), ('MODIS look in the gaps around it', H.modis_in_gaps > 0), ('Terra look in the gaps', H.terra_in_gaps > 0), ('big fires', H.big)]:
                D = H[msk]
                if len(D) < 5: continue
                r = dict(method=meth, variant=v, subset=sub, looks=len(D), fires=D.fire.nunique(), mae_viirs=D[f'mae_{meth}_V'].mean(), mae=D[f'mae_{meth}_{v}'].mean(), median_viirs=D[f'mae_{meth}_V'].median(), median=D[f'mae_{meth}_{v}'].median(),
                         share_within_6h_viirs=(D[f'mae_{meth}_V'] <= 6).mean(), share_within_6h=(D[f'mae_{meth}_{v}'] <= 6).mean())
                r['gain_h'], r['lo'], r['hi'] = boot(D, f'mae_{meth}_{v}', f'mae_{meth}_V')
                rows.append(r)
    Hs = pd.DataFrame(rows).round(3); Hs.to_csv(f'{OUT}/hidden_summary.csv', index=False); print(Hs.to_string())
