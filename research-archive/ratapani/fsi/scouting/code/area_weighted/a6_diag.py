"""Diagnostics: which big fires does the current list miss, and why the size term cannot add much.
Out: out/diag_{period}.json"""
import json, pandas as pd, numpy as np, aw_common as A
ev = pd.read_parquet(A.S24 + 'events.parquet')
for per in ('held', 'fwd'):
    e = ev[ev.season.isin(A.TEST[per]) & ev.valid]
    H = pd.read_parquet(A.S24 + f'hits_{per}.parquet'); h = H[H.ranking == 'P (current)'].merge(e, on=['division', 'ev'])
    s = h[h.area_src == 'scar']; big = s.area_ha >= A.BIG
    x = H[H.ranking == 'PxE'].merge(e, on=['division', 'ev']); x = x[x.area_src == 'scar']
    m = s[['division', 'ev', 'hit', 'area_ha', 'new']].merge(x[['division', 'ev', 'hit']], on=['division', 'ev'], suffixes=('', '_pxe'))
    b = m.area_ha >= A.BIG
    out = dict(n_scar=len(s), n_big=int(big.sum()), big_new_share=float(s.new[big].mean()), all_new_share=float(s.new.mean()),
               missed_big=int((~s.hit & big).sum()), missed_big_new=int((~s.hit & big & s.new).sum()),
               missed_ha_share=float(((~s.hit) * s.area_ha).sum() / s.area_ha.sum()),
               missed_ha_new_share=float(((~s.hit) * s.area_ha)[s.new].sum() / ((~s.hit) * s.area_ha).sum()),
               big_catch_new=float(s.hit[big & s.new].mean()), small_catch_new=float(s.hit[~big & s.new].mean()),
               big_catch_old=float(s.hit[big & ~s.new].mean()), small_catch_old=float(s.hit[~big & ~s.new].mean()),
               fdsq_med_big=float(s.nfd[big].median()), fdsq_med_small=float(s.nfd[~big].median()),
               big_gained_by_pxe=int((b & ~m.hit & m.hit_pxe).sum()), big_lost_by_pxe=int((b & m.hit & ~m.hit_pxe).sum()),
               small_gained_by_pxe=int((~b & ~m.hit & m.hit_pxe).sum()), small_lost_by_pxe=int((~b & m.hit & ~m.hit_pxe).sum()))
    json.dump(out, open(A.OUT + f'diag_{per}.json', 'w'), indent=1); print(per, json.dumps({k: round(v, 3) for k, v in out.items()}))

# 95% CIs (resampling fires) for the current list's % fires, % scar ha and % 200 ha+ fires caught
for per in ('held', 'fwd'):
    e = ev[ev.season.isin(A.TEST[per]) & ev.valid]
    H = pd.read_parquet(A.S24 + f'hits_{per}.parquet'); h = H[H.ranking == 'P (current)'].merge(e, on=['division', 'ev'])
    rng = np.random.default_rng(0); hit = h.hit.values.astype(float); sc = (h.area_src == 'scar').values; a = h.area_ha.values; n = len(h)
    S = []
    for _ in range(1000):
        i = rng.integers(0, n, n); s = i[sc[i]]; b = s[a[s] >= A.BIG]
        S.append((hit[i].mean(), (hit[s] * a[s]).sum() / a[s].sum(), hit[b].mean()))
    lo, hi = np.percentile(S, [2.5, 97.5], axis=0) * 100
    ci = dict(fires=(lo[0], hi[0]), ha_scar=(lo[1], hi[1]), big_scar=(lo[2], hi[2]))
    json.dump(ci, open(A.OUT + f'current_ci_{per}.json', 'w')); print(per, {k: tuple(round(x, 1) for x in v) for k, v in ci.items()})
