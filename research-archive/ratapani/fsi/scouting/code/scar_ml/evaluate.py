"""Score every method on the independent truth only. Out: results/*.csv and results/summary.json.
A. Esri Wayback sub-metre image (real fires vs decoys): darkness of mapped ground, false scars on decoys, and a
   brightness mixing estimate of pixel precision / recall (inferred, see the report).
B. Sentinel-2 / Landsat fire pixels (the scene itself removed from the stack): share of fire pixels each map covers,
   with and without a FIRMS alert nearby.
C. Per-pixel burn date vs VIIRS first detection, and vs mid-fire photos (photo scene removed from the stack)."""
import json, os, warnings, numpy as np, pandas as pd, datetime as dt
from scipy.ndimage import binary_dilation
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
from pyproj import Transformer
from lib import CODE, SCR, alerts, RES
warnings.filterwarnings('ignore')
OUT = CODE + 'results/'; os.makedirs(OUT, exist_ok=True)
C = pd.read_csv(CODE + 'chips.csv').set_index('chip')
I = pd.read_json(SCR + 'res_index.jsonl', lines=True); I = I[I.status == 'ok'].set_index('chip')
METH = ['rule', 'v2', 'b_abs', 'b_nc', 'ml_pu', 'ml_pn', 'ml_af', 'combo']
NAME = dict(rule='current rule (all alerts in chip)', v2='v2 event outline', b_abs='NBR drop >= 0.10', b_nc='rule test, no alert tie',
            ml_pu='LightGBM PU', ml_pn='LightGBM PN', ml_af='LightGBM, fire-pixel labels', combo='rule + PN patches')
TO = Transformer.from_crs(4326, 32643, always_xy=True)
S = {}
class R(dict):
    """Result arrays of a chip, plus 'combo' = current rule OR the PN model (the rule's map plus alert-free patches)."""
    def __init__(self, ch):
        z = np.load(f'{SCR}res/{ch}.npz'); super().__init__({k: z[k] for k in z.files}); self['combo'] = self['rule'] | self['ml_pn']
        self.files = list(self)
ring = lambda m, a, b: binary_dilation(m, iterations=a) & ~binary_dilation(m, iterations=b)

# ------------------------------------------------------------ A. Wayback
V2L = pd.read_csv('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_alert_scar_lookup.csv').drop_duplicates('event_id').set_index('event_id')
rows, mix = [], []
for ch in I.index:
    c = C.loc[ch]
    if c.kind not in ('wb_real', 'wb_decoy') or not os.path.exists(f'{SCR}wb/{ch}.npz'): continue
    z = R(ch); w = np.load(f'{SCR}wb/{ch}.npz'); B = w['bright']; W = np.isfinite(B)
    if W.sum() < 1500: continue
    ms = {m: z[m] & W for m in METH}
    for m in METH:
        if c.kind == 'wb_decoy' and m == 'v2': continue
        M = ms[m]; rg = ring(z[m], 7, 1) & W
        con = B[rg].mean() - B[M].mean() if M.sum() >= 10 and rg.sum() >= 10 else np.nan
        rows.append(dict(chip=ch, kind=c.kind, age=c.age, method=m, ha=M.sum() * 0.04, contrast=con,
                         v2_ha=V2L.scar_ha.get(c.key, np.nan) if c.kind == 'wb_real' else np.nan))
    # mixing estimate (fresh real chips): consensus burned = mapped by >= 4 of the 5 chip methods; unburned reference =
    # unmapped cells >= 100 m from any mapped cell
    if c.kind == 'wb_real' and c.age <= 10:
        five = ['rule', 'b_abs', 'b_nc', 'ml_pu', 'ml_pn']
        votes = sum(ms[m].astype(int) for m in five); cons = votes >= 4
        un = np.zeros_like(W)
        for m in METH: un |= ms[m]
        ref = W & ~binary_dilation(un, iterations=5); near = W & ~un & binary_dilation(un, iterations=5)
        if cons.sum() < 10 or ref.sum() < 100: continue
        bu, bc = B[ref].mean(), B[cons].mean(); dc = bu - bc
        if dc < 3: continue  # burn not visible on this image: cannot calibrate
        p = lambda G: float(np.clip((bu - B[G].mean()) / dc, 0, 1)) if G.sum() >= 5 else 0.0
        tot = cons.sum() + p(un & ~cons) * (un & ~cons).sum() + p(near) * near.sum()
        r = dict(chip=ch, age=c.age, v2_ha=V2L.scar_ha.get(c.key, np.nan), dc=dc, total_burn_ha=tot * 0.04, p_near=p(near), near_ha=near.sum() * 0.04)
        for m in METH:
            M = ms[m]; extra = M & ~cons
            r[f'{m}_ha'] = M.sum() * 0.04; r[f'{m}_burn_ha'] = ((M & cons).sum() + p(extra) * extra.sum()) * 0.04; r[f'{m}_extra_p'] = p(extra)
        # disagreement: ground the PU model adds beyond the rule, and rule ground it drops
        for nm, G in (('pu_not_rule', ms['ml_pu'] & ~ms['rule']), ('rule_not_pu', ms['rule'] & ~ms['ml_pu']), ('pu_not_v2', ms['ml_pu'] & ~ms['v2']),
                      ('v2_not_pu', ms['v2'] & ~ms['ml_pu'])):
            r[f'{nm}_ha'] = G.sum() * 0.04; r[f'{nm}_p'] = p(G) if G.sum() >= 5 else np.nan
        mix.append(r)
A = pd.DataFrame(rows); A.to_csv(OUT + 'wayback_chip_method.csv', index=False)
X = pd.DataFrame(mix); X.to_csv(OUT + 'wayback_mixing.csv', index=False)
tabA = []
for m in METH:
    a = A[A.method == m]; re, de = a[a.kind == 'wb_real'], a[a.kind == 'wb_decoy']
    score = a.contrast.fillna(0).where(a.ha >= 0.5, 0)
    auc = roc_auc_score(a.kind == 'wb_real', score) if m != 'v2' else np.nan
    fr = re[re.age <= 10]
    tabA.append(dict(method=m, real_chips=len(re), real_mapped=(re.ha >= 0.5).mean(), real_contrast_med=re.contrast.median(),
                     fresh_contrast_med=fr.contrast.median(), fresh_darker5=(fr.contrast > 5).mean(),
                     decoys=len(de), decoy_with_scar=(de.ha >= 0.5).mean() if len(de) else np.nan, decoy_ha_mean=de.ha.mean() if len(de) else np.nan,
                     decoy_scar_contrast_med=de[de.ha >= 0.5].contrast.median() if len(de) else np.nan, real_vs_decoy_auc=auc))
TA = pd.DataFrame(tabA); TA.to_csv(OUT + 'A_wayback.csv', index=False); print(TA.round(3).to_string())
if len(X):
    pr = []
    for sub, g in (('all fresh', X), ('v2 < 20 ha', X[X.v2_ha < 20]), ('v2 >= 20 ha', X[X.v2_ha >= 20])):
        for m in METH:
            pr.append(dict(subset=sub, chips=len(g), method=m, mapped_ha=g[f'{m}_ha'].sum(), est_burned_ha=g[f'{m}_burn_ha'].sum(),
                           precision=g[f'{m}_burn_ha'].sum() / max(g[f'{m}_ha'].sum(), 1e-9), recall=g[f'{m}_burn_ha'].sum() / g.total_burn_ha.sum(),
                           area_bias=g[f'{m}_ha'].sum() / g.total_burn_ha.sum()))
    PR = pd.DataFrame(pr); PR['f1'] = 2 * PR.precision * PR.recall / (PR.precision + PR.recall); PR.to_csv(OUT + 'A_mixing_pr.csv', index=False)
    print(PR.round(3).to_string())
    dis = {k: dict(ha=float(X[f'{k}_ha'].sum()), p_area_weighted=float((X[f'{k}_p'] * X[f'{k}_ha']).sum() / X.loc[X[f'{k}_p'].notna(), f'{k}_ha'].sum()))
           for k in ('pu_not_rule', 'rule_not_pu', 'pu_not_v2', 'v2_not_pu')}
    S['disagreement'] = dis; S['mix_chips'] = len(X); S['near_ring_p'] = float((X.p_near * X.near_ha).sum() / X.near_ha.sum())
    print(dis)

# ------------------------------------------------------------ B. fire pixels
af = pd.read_csv('/mnt/project-files/fire-alert-scars/out/af/af_pixels_clean.csv')
af['key'] = af.season.astype(str) + '_' + af.cluster.astype(str) + '_' + af.date
af['x'], af['y'] = TO.transform(af.lon.values, af.lat.values)
rb = []
for ch in I.index:
    c = C.loc[ch]
    if not c.kind.startswith('af_'): continue
    z = R(ch); n = int(I.loc[ch, 'n']); tr = None
    st = np.load(f'{SCR}stacks/{ch}.npz'); tr = st['tr']
    p = af[af.key == c.key]; cc = ((p.x - tr[2]) / RES).astype(int).values; rr = ((tr[5] - p.y) / RES).astype(int).values
    k = (cc >= 1) & (cc < n - 1) & (rr >= 1) & (rr < n - 1); cc, rr = cc[k], rr[k]
    if not len(cc): continue
    for m in ['rule', 'b_abs', 'b_nc', 'ml_pu', 'ml_pn', 'ml_af', 'combo']:
        M = binary_dilation(z[m], iterations=1)
        rb.append(dict(chip=ch, kind=c.kind, method=m, n_af=len(cc), hit=M[rr, cc].mean(), any_hit=M[rr, cc].any(),
                       chip_ha=z[m].sum() * 0.04, rule_ha=z['rule'].sum() * 0.04, n_alerts=I.loc[ch, 'n_alerts']))
Bd = pd.DataFrame(rb); Bd.to_csv(OUT + 'af_chip_method.csv', index=False)
TB = Bd.groupby(['kind', 'method']).agg(chips=('chip', 'size'), af_pixels_covered=('hit', 'mean'), clusters_touched=('any_hit', 'mean'),
                                        chip_ha_median=('chip_ha', 'median')).reset_index()
TB.to_csv(OUT + 'B_firepixels.csv', index=False); print(TB.round(3).to_string())

# ------------------------------------------------------------ C1. dates vs VIIRS first detection
AL = alerts(); V = AL[AL.viirs]
rc = []
for ch in I.index:
    c = C.loc[ch]
    if c.kind not in ('wb_real', 'af_firms'): continue
    z = R(ch); st = np.load(f'{SCR}stacks/{ch}.npz'); tr = st['tr']; n = int(I.loc[ch, 'n'])
    d0 = pd.Timestamp(c.date)
    v = V[(V.d >= d0 - pd.Timedelta(days=30)) & (V.d <= d0 + pd.Timedelta(days=40)) & (V.x > tr[2] - 500) & (V.x < tr[2] + n * RES + 500) &
          (V.y < tr[5] + 500) & (V.y > tr[5] - n * RES - 500)]
    if not len(v): continue
    m = z['ml_pu'] & np.isfinite(z['U']); rr, cc = np.where(m)
    if not len(rr): continue
    if len(rr) > 400: k = np.random.default_rng(1).choice(len(rr), 400, replace=False); rr, cc = rr[k], cc[k]
    X_ = tr[2] + (cc + 0.5) * RES; Y_ = tr[5] - (rr + 0.5) * RES
    tree = cKDTree(v[['x', 'y']].values); vd = v.d.map(pd.Timestamp.toordinal).values
    first = np.array([vd[j].min() if len(j) else np.nan for j in tree.query_ball_point(np.c_[X_, Y_], 400)])
    pre = dt.date.fromisoformat(I.loc[ch, 'pre']).toordinal(); post = dt.date.fromisoformat(I.loc[ch, 'post']).toordinal()
    rc.append(pd.DataFrame(dict(chip=ch, U=z['U'][rr, cc], L=z['L'][rr, cc], v=first, pre=pre, post=post, anchor=d0.toordinal())))
D = pd.concat(rc).dropna(subset=['v']); D.to_parquet(OUT + 'dates_vs_viirs.parquet')
D['mid'] = (D.U + D.L) / 2; D['wmid'] = (D.pre + D.post) / 2
def dstats(est, lo, hi, d):
    e = est - d.v
    return dict(pixels=len(d), chips=d.chip.nunique(), median_abs_err_days=float(np.median(np.abs(e))), within_2d=float((np.abs(e) <= 2).mean()),
                window_median_days=float(np.median(hi - lo)), window_holds_viirs_day=float(((d.v >= lo) & (d.v <= hi)).mean()))
TC = pd.DataFrame([dict(method='per-pixel first persistent drop (midpoint of its window)', **dstats(D.mid, D.L, D.U, D)),
                   dict(method='per-pixel, upper end (first look showing the drop)', **dstats(D.U, D.L, D.U, D)),
                   dict(method='current: image-pair window (pre, post], midpoint', **dstats(D.wmid, D.pre, D.post, D)),
                   dict(method='current: alert day of the chip event for every pixel', **dstats(D.anchor.astype(float), D.anchor, D.anchor, D))])
TC.to_csv(OUT + 'C1_dates_vs_viirs.csv', index=False); print(TC.round(3).to_string())

# ------------------------------------------------------------ C2. dates vs mid-fire photos
rp = []
for ch in I.index:
    c = C.loc[ch]
    if c.kind != 'photo': continue
    z = R(ch)
    if 'S' not in z.files: continue
    S_, bym, okp, U, L = z['S'], z['bym'], z['okp'], z['U'], z['L']
    m = S_ & okp
    if m.sum() < 20: continue
    T = pd.Timestamp(c['T']); Td = T.normalize().toordinal() + 10.5 / 24  # photo near 10:30 IST (05:00 UTC) on its date
    u, l, y = U[m], L[m], bym[m]
    s = np.where(np.isnan(u), np.nan, np.where(u <= Td - 0.5, 1.0, np.where(l >= Td, 0.0, np.clip((Td - l) / np.maximum(u - l, 1), 0, 1))))
    # VIIRS dots seen before the photo (last 3 days): distance score ('closest to any dot so far')
    st = np.load(f'{SCR}stacks/{ch}.npz'); tr = st['tr']; rr, cc = np.where(m)
    X_ = tr[2] + (cc + 0.5) * RES; Y_ = tr[5] - (rr + 0.5) * RES
    a = AL[AL.viirs]; a = a[(a.d >= T.normalize() - pd.Timedelta(days=3)) & (a.d <= T.normalize())]
    a = a[(a.d < T.normalize()) | (a.acq_time.astype(int) < T.hour * 100 + T.minute)]
    dmin = cKDTree(a[['x', 'y']].values).query(np.c_[X_, Y_])[0] if len(a) else np.full(len(rr), 9e9)
    rp.append(pd.DataFrame(dict(chip=ch, y=y, s=s, dmin=dmin)))
P = pd.concat(rp); P.to_parquet(OUT + 'dates_vs_photos.parquet')
k = P.s.notna(); dec = k & ((P.s == 0) | (P.s == 1))
au = lambda yy, ss: roc_auc_score(yy, ss) if 0 < yy.mean() < 1 else np.nan
S['photo'] = dict(photos=int(P.chip.nunique()), pixels=len(P), burned_by_photo=float(P.y.mean()), dated=float(k.mean()),
                  decided=float(dec.mean()), acc_decided=float(((P.s[dec] == 1) == P.y[dec]).mean()),
                  auc_perpixel_dated=au(P.y[k], P.s[k]), auc_viirs_distance_same_pixels=au(P.y[k], -P.dmin[k]),
                  auc_viirs_distance_all=au(P.y, -P.dmin), auc_combined_all=au(P.y, P.s.fillna(0.5) - P.dmin / 2000),
                  acc_viirs_400m_all=float(((P.dmin <= 400) == P.y).mean()))
print(S['photo'])
S['n_chips_scored'] = I.reset_index().merge(C.reset_index()[['chip', 'kind']]).kind.value_counts().to_dict()
json.dump(S, open(OUT + 'summary.json', 'w'), indent=1, default=float)

# ------------------------------------------------------------ B2. pixel AUC: fire pixels (burned) vs decoy-window pixels (presumed unburned)
from lib import prepare
pos, neg = [], []
rng = np.random.default_rng(3)
for ch in I.index:
    c = C.loc[ch]
    if not (c.kind.startswith('af_') or c.kind == 'wb_decoy'): continue
    r = c.to_dict(); r['chip'] = ch
    ex = [c.scene_date] if isinstance(c.get('scene_date'), str) else []
    p = prepare(r, ex)
    if p is None: continue
    z = R(ch); n = p['st']['n']; tr = p['st']['tr']; ok = p['parts']['ok']
    sc = dict(dnbr=p['parts']['dnbr'], rdn=p['parts']['rdn'], p_pu=z['p_pu'].astype(float), p_pn=z['p_pn'].astype(float), p_af=z['p_af'].astype(float))
    if c.kind == 'wb_decoy':
        yy, xx = np.mgrid[0:n, 0:n]; ctr = ((yy - n / 2) ** 2 + (xx - n / 2) ** 2 <= 25 ** 2) & ok
        ii = np.flatnonzero(ctr.ravel()); ii = rng.choice(ii, min(200, len(ii)), replace=False)
        neg.append(pd.DataFrame({k: v.ravel()[ii] for k, v in sc.items()}).assign(chip=ch, y=0, firms=np.nan))
    else:
        q = af[af.key == c.key]; cc = ((q.x - tr[2]) / RES).astype(int).values; rr = ((tr[5] - q.y) / RES).astype(int).values
        k = (cc >= 0) & (cc < n) & (rr >= 0) & (rr < n); ii = np.unique(rr[k] * n + cc[k]); ii = ii[ok.ravel()[ii]]
        pos.append(pd.DataFrame({k_: v.ravel()[ii] for k_, v in sc.items()}).assign(chip=ch, y=1, firms=c.kind == 'af_firms'))
PX = pd.concat(pos + neg, ignore_index=True); PX.to_parquet(OUT + 'pixel_auc_rows.parquet')
def boot_auc(d, col, B=300):
    ch = d.chip.unique(); g = {c_: d[d.chip == c_] for c_ in ch}; a = []
    for b in range(B):
        s = pd.concat([g[c_] for c_ in rng.choice(ch, len(ch))]); a.append(roc_auc_score(s.y, s[col]) if s.y.nunique() == 2 else np.nan)
    return np.nanpercentile(a, [2.5, 97.5])
tab = []
for sub, d in (('fire pixels, no FIRMS nearby', PX[(PX.firms == False) | (PX.y == 0)]), ('fire pixels, FIRMS nearby', PX[(PX.firms == True) | (PX.y == 0)])):
    for col in ('dnbr', 'rdn', 'p_pu', 'p_pn', 'p_af'):
        lo, hi = boot_auc(d, col, 200)
        tab.append(dict(subset=sub, score=col, pos=int(d.y.sum()), neg=int((d.y == 0).sum()), auc=roc_auc_score(d.y, d[col]), lo=lo, hi=hi))
TB2 = pd.DataFrame(tab); TB2.to_csv(OUT + 'B2_pixel_auc.csv', index=False); print(TB2.round(3).to_string())

# ------------------------------------------------------------ bootstrap ranges for headline rates (resampling chips)
def boot_rate(v, B=2000):
    v = np.asarray(v, float); b = [rng.choice(v, len(v)).mean() for _ in range(B)]; return np.percentile(b, [2.5, 97.5])
bt = []
for m in ['rule', 'b_abs', 'b_nc', 'ml_pu', 'ml_pn', 'ml_af', 'combo']:
    de = A[(A.method == m) & (A.kind == 'wb_decoy')]; lo, hi = boot_rate(de.ha >= 0.5)
    bt.append(dict(metric='decoys with a scar', method=m, value=(de.ha >= 0.5).mean(), lo=lo, hi=hi))
    for kd in ('af_nofirms', 'af_firms'):
        b_ = Bd[(Bd.method == m) & (Bd.kind == kd)]; lo, hi = boot_rate(b_.hit)
        bt.append(dict(metric=f'{kd} fire pixels covered (chip mean)', method=m, value=b_.hit.mean(), lo=lo, hi=hi))
if len(X):
    for m in ['ml_pn', 'ml_pu', 'ml_af', 'b_abs', 'v2', 'combo']:
        d = []
        for b in range(1000):
            s = X.iloc[rng.choice(len(X), len(X))]; tot = s.total_burn_ha.sum()
            d.append((s[f'{m}_burn_ha'].sum() - s['rule_burn_ha'].sum()) / tot)
        bt.append(dict(metric='Wayback recall minus rule recall', method=m, value=(X[f'{m}_burn_ha'].sum() - X.rule_burn_ha.sum()) / X.total_burn_ha.sum(),
                       lo=np.percentile(d, 2.5), hi=np.percentile(d, 97.5)))
BT = pd.DataFrame(bt); BT.to_csv(OUT + 'bootstrap_ranges.csv', index=False); print(BT.round(3).to_string())
json.dump(S, open(OUT + 'summary.json', 'w'), indent=1, default=float)
