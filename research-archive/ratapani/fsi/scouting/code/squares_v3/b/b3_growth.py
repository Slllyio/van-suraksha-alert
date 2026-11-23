"""B step 3: growth rate = active line length x spread speed, tested against independent and semi-independent growth.

Per Ratapani fire (big-fires ids, v2 outlines): its VIIRS passes, each its own (line_pass.parquet, L from b2, held-out
calibration). Evaluation intervals = consecutive look slots >= 6 h apart (a slot = the passes within 2 h; L of a slot =
mean of its passes' own L). Predicted growth over [t1, t2]:
    dA = k x mean(L1, L2) x v x clock_hours(t1, t2)          (ha, k fitted on the other seasons)
v variants: 'same speed for all' (flat class model), 'class' (class mean), 'per fire' (posterior, all the fire's pairs),
plus 'line only' (L x clock hours, = same speed) and 'speed only' (v x clock hours, L fixed).
All class / tau / DE fits leave the fire's season out (b_post).
Truth:
  (1) blend-map growth (fire-continuity map, b3a): area with arrival <= t2 minus <= t1
  (2) grid-map growth (squares_v2 tracking fronts_grid12.csv): burned ha at the two passes
  (3) photo-to-photo growth: two mid-fire Sentinel-2/Landsat photos of the same event (burned share of the chip's scar x
      scar area in chip)
  (4) burned area by photo time (340 photos): cumulative predicted area by the photo minute vs the photo's burned share x
      chip scar area; also the burned SHARE by photo time vs the blend and grid maps' own shares (t6 table)
  (5) part A's per-fire 30 m front advance (hot-pixel scenes 1-6 days apart, a2_front_advance_30m.csv): rank agreement with
      per-fire vs class speeds
Scores: Spearman rho, held-out R2 of log growth; 95% ranges by bootstrap over fires.
Out: results/b3_growth.json, b3_intervals.csv, b3_photo.csv, fig_b3_growth.png"""
import sys, os, json, pickle, glob
import numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
from b_post import fire_speed, ratapani_meta, models
from b1_hier import load
rng = np.random.default_rng(21)
IST = pd.Timedelta(hours=5.5)

def ist_h(t):  # absolute hours since 2017-01-01 IST
    return ((pd.to_datetime(t) + IST) - pd.Timestamp('2017-01-01')).dt.total_seconds().values / 3600 if hasattr(t, 'dt') else \
        ((pd.Timestamp(t) + IST) - pd.Timestamp('2017-01-01')).total_seconds() / 3600

def speeds():
    """per Ratapani fire and season-held-out models: mu, f_post (all pairs), flat mu"""
    O, _ = load(); P = O[O.fire_rt >= 0]; meta = ratapani_meta(); out = []
    for s, m in meta.groupby('season'):
        pp = P[P.fire_rt.isin(m.fire)]
        a = fire_speed(m, pp, s); b = fire_speed(m, pp, s, flat=True)
        a['v_flat'] = b.mu.values; a['f_post_flat'] = b.f_post.values; a['season'] = s; out.append(a)
    return pd.concat(out)

def slots(G):
    G = G[G.kind == 'viirs'].sort_values(['fire', 't']).copy()
    G['slot'] = G.groupby('fire').t.transform(lambda t: (t.diff().dt.total_seconds().fillna(1e9) > 2 * 3600).cumsum())
    return G.groupby(['fire', 'slot']).agg(t=('t', 'min'), L=('L_m', 'mean'), n=('n', 'mean'), passes=('n', 'size'), dn=('dn', 'first')).reset_index()

def boot_rho(df, a, b, n=500):
    f = df.fire.values; u = np.unique(f); ix = {q: np.where(f == q)[0] for q in u}; v = []
    for _ in range(n):
        k = np.concatenate([ix[q] for q in rng.choice(u, len(u))]); v.append(spearmanr(df[a].values[k], df[b].values[k])[0])
    return [round(float(np.quantile(v, .025)), 3), round(float(np.quantile(v, .975)), 3)]

def heldout_r2(df, pred, obs):
    """log(obs + 1 ha) = log k + log(pred), k fitted on the other seasons (median of the log ratio)"""
    y = np.log(df[obs].clip(lower=0).values + 1.0); x = np.log(df[pred].values + 1e-6); e = np.zeros(len(df))
    for s in df.season.unique():
        tr = (df.season != s).values; lk = np.median(y[tr] - x[tr]); e[~tr] = y[~tr] - (x[~tr] + lk)
    return round(float(1 - np.mean(e ** 2) / np.var(y)), 3)

if __name__ == '__main__':
    V = speeds(); V.to_parquet(f'{SC}/ratapani_speeds.parquet')
    G = pd.read_parquet(f'{SC}/line_pass.parquet'); S = slots(G)
    S['th'] = ist_h(S.t)
    rows = []
    for fire, g in S.groupby('fire'):
        g = g.sort_values('t')
        for a, b in zip(g.iloc[:-1].itertuples(), g.iloc[1:].itertuples()):
            if (b.t - a.t).total_seconds() < 6 * 3600 or (b.t - a.t).total_seconds() > 40 * 3600: continue
            ck = float(clock_between([a.th], [b.th])[0])
            rows.append(dict(fire=fire, t1=a.t, t2=b.t, gap_h=(b.t - a.t).total_seconds() / 3600, clock_h=ck, L1=a.L, L2=b.L, n1=a.n, n2=b.n))
    I = pd.DataFrame(rows).merge(V[['mu', 'f_post', 'v_post', 'v_flat', 'season', 'n_pairs', 'B']], left_on='fire', right_index=True)
    Lm = (I.L1 + I.L2) / 2
    I['pred_same'] = Lm * I.v_flat * I.clock_h / 1e4; I['pred_class'] = Lm * I.mu * I.clock_h / 1e4; I['pred_fire'] = Lm * I.v_post * I.clock_h / 1e4
    I['pred_speedonly'] = 375.0 * I.v_post * I.clock_h / 1e4; I['pred_clock'] = I.clock_h
    # truth (1) blend
    BA = pd.read_parquet(f'{SC}/blend_area.parquet')
    def area_at(tab, fire, t, col='area_ha', tcol='t'):
        g = tab[tab.fire == fire]
        if not len(g): return np.nan
        g = g.sort_values(tcol); k = np.searchsorted(g[tcol].values, np.datetime64(t + pd.Timedelta(minutes=30)), side='right') - 1
        return float(g[col].values[k]) if k >= 0 else 0.0
    I['obs_blend'] = [area_at(BA, f, b) - area_at(BA, f, a) for f, a, b in zip(I.fire, I.t1, I.t2)]
    FG = pd.read_csv(f'{V2}/tracking/results/fronts_grid12.csv', parse_dates=['t'])
    I['obs_grid'] = [area_at(FG, f, b, 'burned_ha') - area_at(FG, f, a, 'burned_ha') for f, a, b in zip(I.fire, I.t1, I.t2)]
    I.to_csv(f'{OUT}/b3_intervals.csv', index=False)
    res = dict(intervals=len(I), fires=int(I.fire.nunique()), fires_with_pairs=int((I.drop_duplicates('fire').n_pairs > 0).sum()),
               median_B_of_these_fires=round(float(I.drop_duplicates('fire').B.median()), 4))
    preds = ['pred_same', 'pred_class', 'pred_fire', 'pred_speedonly', 'pred_clock']
    for obs in ['obs_blend', 'obs_grid']:
        d = I.dropna(subset=[obs]); d = d[d[obs] >= 0]; r = dict(n=len(d), fires=int(d.fire.nunique()), median_obs_ha=round(float(d[obs].median()), 1))
        for p in preds:
            r[p] = dict(rho=round(float(spearmanr(d[p], d[obs])[0]), 3), rho_ci=boot_rho(d, p, obs), heldout_r2_log=heldout_r2(d, p, obs),
                        k_median=round(float(np.exp(np.median(np.log(d[obs] + 1) - np.log(d[p] + 1e-6)))), 3) if p != 'pred_clock' else None)
        # paired: per-fire minus class (rho difference, bootstrap)
        f = d.fire.values; u = np.unique(f); ix = {q: np.where(f == q)[0] for q in u}; dv = []
        for _ in range(500):
            k = np.concatenate([ix[q] for q in rng.choice(u, len(u))])
            dv.append(spearmanr(d.pred_fire.values[k], d[obs].values[k])[0] - spearmanr(d.pred_class.values[k], d[obs].values[k])[0])
        r['rho_fire_minus_class'] = [round(float(np.mean(dv)), 4), round(float(np.quantile(dv, .025)), 4), round(float(np.quantile(dv, .975)), 4)]
        dd = d[d.B > 0.2]
        r['fires_B_gt_0.2'] = dict(n=len(dd), fires=int(dd.fire.nunique()),
                                   rho_fire=round(float(spearmanr(dd.pred_fire, dd[obs])[0]), 3) if len(dd) > 10 else None,
                                   rho_class=round(float(spearmanr(dd.pred_class, dd[obs])[0]), 3) if len(dd) > 10 else None)
        res[obs] = r
    # truth (3)/(4) photos
    PH = pickle.load(open(f'{R17}/photos.pkl', 'rb')); T6 = pd.read_csv(f'{V2}/tracking/results/t6_photos_grid12.csv')
    CH = f'{ROOT}/fuel-map/ratapani/timing/chips'
    prow = []
    for ph in PH:
        fn = f"{CH}/{ph['event']}_{ph['scene'][:40]}.npz"
        if not os.path.exists(fn): continue
        z = np.load(fn); Sm = z['S']; ok = z['ok']; bym = z['bym']
        share = float(bym[Sm & ok].mean()) if (Sm & ok).any() else np.nan
        A_chip = float(Sm.sum() * 0.04)
        f = ph['fire']; g = S[S.fire == f].sort_values('t')
        if not len(g) or f not in V.index: continue
        T = pd.Timestamp(ph['T']); tT = ist_h(T); th = g.th.values; L = g.L.values; v = V.loc[f]
        def cum(vv, upto):
            c = 0.0
            for i in range(len(g) - 1):
                if th[i] >= upto: break
                t2 = min(th[i + 1], upto); c += 0.5 * (L[i] + L[i + 1]) * vv * float(clock_between([th[i]], [t2])[0]) / 1e4
            return c
        end = th[-1] + 12
        r = dict(event=ph['event'], scene=ph['scene'], fire=f, season=ph['season'], T=T, share_obs=share, A_chip_ha=A_chip, A_obs_ha=share * A_chip,
                 n_slots_before=int((th < tT).sum()), n_slots=len(g))
        for nm, vv in [('same', v.v_flat), ('class', v.mu), ('fire', v.v_post)]:
            r[f'A_{nm}'] = cum(vv, tT); r[f'Aend_{nm}'] = cum(vv, end)
        r['share_pred_line'] = r['A_class'] / r['Aend_class'] if r['Aend_class'] > 0 else np.nan
        t6 = T6[(T6.event == ph['event']) & (T6.scene == ph['scene'])]
        if len(t6): r['share_blend'] = float(t6.frac_blend.iloc[0]); r['share_grid'] = float(t6.frac_inversion.iloc[0]); r['share_nearest'] = float(t6.frac_nearest.iloc[0])
        prow.append(r)
    PR = pd.DataFrame(prow); PR.to_csv(f'{OUT}/b3_photo.csv', index=False)
    rp = dict(photos=len(PR), fires=int(PR.fire.nunique()))
    d = PR[(PR.n_slots_before >= 1) & (PR.n_slots >= 2)].copy()
    rp['area_by_photo'] = dict(n=len(d))
    for nm in ['same', 'class', 'fire']:
        rp['area_by_photo'][nm] = dict(rho=round(float(spearmanr(d[f'A_{nm}'], d.A_obs_ha)[0]), 3), rho_ci=boot_rho(d, f'A_{nm}', 'A_obs_ha'),
                                       heldout_r2_log=heldout_r2(d.rename(columns={f'A_{nm}': 'p'}), 'p', 'A_obs_ha'))
    dd = d.dropna(subset=['share_blend'])
    rp['share_by_photo'] = dict(n=len(dd))
    for c in ['share_pred_line', 'share_blend', 'share_grid', 'share_nearest']:
        dd2 = dd.dropna(subset=[c]); rp['share_by_photo'][c] = dict(mae=round(float((dd2[c] - dd2.share_obs).abs().mean()), 3),
                                                                    bias=round(float((dd2[c] - dd2.share_obs).mean()), 3),
                                                                    rho=round(float(spearmanr(dd2[c], dd2.share_obs)[0]), 3))
    # photo-to-photo growth (same event, later photo minus earlier)
    pp = []
    for ev, g in PR.groupby('event'):
        g = g.sort_values('T')
        for a, b in zip(g.iloc[:-1].itertuples(), g.iloc[1:].itertuples()):
            if (b.T - a.T).total_seconds() < 12 * 3600: continue
            pp.append(dict(fire=a.fire, season=a.season, gap_h=(b.T - a.T).total_seconds() / 3600, dA_obs=b.A_obs_ha - a.A_obs_ha,
                           dA_same=b.A_same - a.A_same, dA_class=b.A_class - a.A_class, dA_fire=b.A_fire - a.A_fire))
    PP = pd.DataFrame(pp); rp['photo_to_photo'] = dict(pairs=len(PP))
    if len(PP) >= 8:
        for nm in ['same', 'class', 'fire']:
            rp['photo_to_photo'][nm] = dict(rho=round(float(spearmanr(PP[f'dA_{nm}'], PP.dA_obs)[0]), 3))
        rp['photo_to_photo']['median_obs_growth_ha_per_h'] = round(float((PP.dA_obs / PP.gap_h).median()), 3)
        rp['photo_to_photo']['median_pred_class_ha_per_h'] = round(float((PP.dA_class / PP.gap_h).median()), 3)
    res['photos'] = rp
    # truth (5) part A's 30 m front advance per fire
    fa_fn = f'{A_RES}/a2_front_advance_30m.csv'
    if os.path.exists(fa_fn):
        FA = pd.read_csv(fa_fn); FA['adv_m_h'] = FA.adv_med_m / FA.gap_h
        FA = FA.groupby('fire').adv_m_h.median().to_frame().join(V[['mu', 'v_post', 'v_flat', 'B', 'n_pairs']], how='inner')
        res['front_advance_30m_partA'] = dict(fires=len(FA), median_adv_m_h=round(float(FA.adv_m_h.median()), 1),
                                              rho_class=round(float(spearmanr(FA.mu, FA.adv_m_h)[0]), 3), rho_fire=round(float(spearmanr(FA.v_post, FA.adv_m_h)[0]), 3),
                                              fires_with_pairs=int((FA.n_pairs > 0).sum()), median_B=round(float(FA.B.median()), 4),
                                              median_v_post=round(float(FA.v_post.median()), 1))
    json.dump(res, open(f'{OUT}/b3_growth.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
    # figure
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    for j, obs in enumerate(['obs_blend', 'obs_grid']):
        d = I.dropna(subset=[obs]); d = d[d[obs] >= 0]
        ax[j].loglog(d.pred_class + 1e-3, d[obs] + 1, '.', alpha=.3, ms=4)
        ax[j].set_xlabel('predicted growth: line length x class speed x clock hours (ha, before k)'); ax[j].set_ylabel('map growth + 1 (ha)')
        ax[j].set_title(f"{'blend' if j == 0 else 'grid'} map growth between looks: rho {res[obs]['pred_class']['rho']}")
    d = PR[(PR.n_slots_before >= 1)]
    ax[2].loglog(d.A_class + 1e-3, d.A_obs_ha + .1, '.', alpha=.5); ax[2].set_xlabel('predicted burned area by photo time (ha, before k)'); ax[2].set_ylabel('photo: burned area in chip (ha)')
    ax[2].set_title(f"mid-fire photos: rho {rp['area_by_photo']['class']['rho']}")
    plt.tight_layout(); plt.savefig(f'{OUT}/fig_b3_growth.png', dpi=110)
