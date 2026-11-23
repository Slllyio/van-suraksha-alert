"""Test 1. How often do Terra (and Aqua) looks fall between a fire's VIIRS looks, and does Terra night (22:30 IST) catch
fires that VIIRS 01:30 then also sees?
Sets: (i) Ratapani v2 fires (big-fires thread), (ii) all-MP forest VIIRS fires (m1), each with big-fire subsets.
Gaps = consecutive slots of the MP-wide VIIRS schedule between a fire's first and last VIIRS detection.
Out: results/coverage.csv, results/terra_night_catch.csv"""
import os, numpy as np, pandas as pd
S = os.environ['ML_SCRATCH']; OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
SCH = pd.read_parquet(f'{S}/schedule.parquet'); st = SCH.t.values
def cov(V, M, fires, name):
    """V: fire, slot (VIIRS detections); M: fire, t, kind (MODIS detections)."""
    V = V[V.fire.isin(fires)]; M = M[M.fire.isin(fires)].copy()
    g = V.groupby('fire').slot.agg(['min', 'max', 'nunique']); g = g[g['nunique'] >= 2]
    M = M[M.fire.isin(g.index)]
    k = np.searchsorted(st, M.t.values, side='right') - 1                # slot just before the MODIS time
    M['after_slot'] = k; M['gap_h_after'] = (M.t.values - st[k]) / np.timedelta64(1, 'h')
    M['next_h'] = (st[np.minimum(k + 1, len(st) - 1)] - M.t.values) / np.timedelta64(1, 'h')
    # 'between' = more than 1 h after one VIIRS look and more than 1 h before the next (Aqua sits on the VIIRS looks)
    inb = (M.after_slot.values >= g.loc[M.fire, 'min'].values) & (M.after_slot.values < g.loc[M.fire, 'max'].values) & (M.gap_h_after > 1) & (M.next_h > 1)
    Mb = M[inb]
    r = dict(set=name, fires=len(g), gaps=int((g['max'] - g['min']).sum()))
    for kd, lab in [('Terra', 'terra'), ('Terra_D', 'terra_day'), ('Terra_N', 'terra_night'), ('Aqua', 'aqua')]:
        mb = Mb[Mb.kind.str.startswith(kd)]
        r[f'fires_with_{lab}_between'] = round(mb.fire.nunique() / len(g), 3)
        r[f'gaps_with_{lab}'] = round(mb.groupby(['fire', 'after_slot']).ngroups / max(r['gaps'], 1), 3)
    r['aqua_within_1h_of_viirs_share'] = round(1 - inb[M.kind.str.startswith('Aqua').values].mean(), 3) if (M.kind.str.startswith('Aqua')).any() else np.nan
    # longest gap with and without Terra
    def longest(extra):
        out = []
        for f, row in g.iterrows():
            ts = np.r_[st[V[V.fire == f].slot.unique()], extra.get(f, np.array([], 'datetime64[ns]'))]
            ts = np.sort(ts); out.append(np.diff(ts).max() / np.timedelta64(1, 'h') if len(ts) > 1 else np.nan)
        return np.nanmedian(out)
    if len(g) <= 4000:
        ex = {f: d.t.values for f, d in Mb[Mb.kind.str.startswith('Terra')].groupby('fire')}
        r['median_longest_gap_h_viirs'] = round(longest({}), 1); r['median_longest_gap_h_with_terra'] = round(longest(ex), 1)
    return r, M
def catch(V, M, fires, name):
    """For each Terra-night pass on a fire: was it seen at the VIIRS look before (13:30) and the one after (01:30)?
    And the reverse view: of VIIRS 13:30 detections, how often is the fire seen at 01:30, split by Terra 22:30 yes/no."""
    V = V[V.fire.isin(fires)]; M = M[M.fire.isin(fires) & (M.kind == 'Terra_N')].copy()
    seen = set(zip(V.fire, V.slot))
    k = np.searchsorted(st, M.t.values, side='right') - 1; M['prev'] = k; M['next'] = k + 1
    tn = M.groupby(['fire', 'prev']).size().reset_index()[['fire', 'prev']]
    tn['viirs_prev'] = [(f, s) in seen for f, s in zip(tn.fire, tn.prev)]; tn['viirs_next'] = [(f, s + 1) in seen for f, s in zip(tn.fire, tn.prev)]
    r = dict(set=name, terra_night_fire_passes=len(tn), seen_by_viirs_0130_after=round(tn.viirs_next.mean(), 3),
             seen_by_viirs_1330_before=round(tn.viirs_prev.mean(), 3), terra_only_neither=round((~tn.viirs_next & ~tn.viirs_prev).mean(), 3))
    day = V[SCH.h.values[V.slot.values] > 8][['fire', 'slot']].drop_duplicates()
    day = day[day.slot + 1 < len(st)]
    tset = set(zip(tn.fire, tn.prev))
    day['terra_n'] = [(f, s) in tset for f, s in zip(day.fire, day.slot)]
    day['viirs_0130'] = [(f, s + 1) in seen for f, s in zip(day.fire, day.slot)]
    r['p_0130_given_1330'] = round(day.viirs_0130.mean(), 3)
    r['p_0130_given_1330_and_terraN'] = round(day[day.terra_n].viirs_0130.mean(), 3)
    r['p_0130_given_1330_no_terraN'] = round(day[~day.terra_n].viirs_0130.mean(), 3)
    r['share_1330_fires_with_terraN'] = round(day.terra_n.mean(), 3); r['n_1330'] = len(day)
    return r
rows, crow = [], []
# Ratapani v2 fires
RV = pd.read_parquet(f'{S}/rat_viirs.parquet'); RM = pd.read_parquet(f'{S}/rat_modis.parquet'); RF = pd.read_parquet(f'{S}/rat_fires.parquet')
for nm, fs in [('Ratapani v2 fires', RF.fire), ('Ratapani big fires (146)', RF.fire[RF.big])]:
    r, _ = cov(RV, RM, set(fs), nm); rows.append(r); crow.append(catch(RV, RM, set(fs), nm))
# all-MP
F = pd.read_parquet(f'{S}/fires_mp.parquet'); T = pd.read_parquet(f'{S}/fire_slots_mp.parquet'); MM = pd.read_parquet(f'{S}/modis_fire_mp.parquet')
VV = T[T.nv > 0][['fire', 'slot']]; MM = MM[MM.fire >= 0]
big = F.index[(F.n_looks >= 4) & (F.n >= 10)]
for nm, fs in [('all-MP forest fires', F.index), ('all-MP big (>=4 looks, >=10 pts)', big), ('all-MP, Ratapani box', F.index[F.ratapani_box])]:
    r, _ = cov(VV, MM, set(fs), nm); rows.append(r); crow.append(catch(VV, MM, set(fs), nm))
X = pd.DataFrame(rows); C = pd.DataFrame(crow)
X.to_csv(f'{OUT}/coverage.csv', index=False); C.to_csv(f'{OUT}/terra_night_catch.csv', index=False)
pd.set_option('display.width', 250); print(X.T); print(C.T)
