"""Step 10. Satellite check of the World Bank / MP FD claim (Dec 2022): free mahua-collection nets in 8 villages since 2020,
'fire incidents down almost 95%', '18,000 ha prevented over two years' (DFO North Betul). Named villages: Budhni and Khatpura
(Sehore division, Budhni range: beats Budhani, Khatpura_Dabari) and Kupwa (North Betul, Bhaura range: beat Kuppa).
Units: beats. Outcome 1: S-NPP VIIRS fire points per beat-season, 15 Feb-15 Jun, 2014-26 (one satellite, so the series is
consistent). Outcome 2: scar ha per beat-season 2017-25 (events table). Before = 2014-19, after = 2021-26 (2020 dropped).
Difference-in-differences against the other beats of the same division, and against all MP. Out: out/cb10_nets.csv"""
import sys, os
import numpy as np, pandas as pd, pyarrow.parquet as pq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cb0 as B
TREAT = {'012-002-003': 'Budhani (Sehore)', '012-002-010': 'Khatpura_Dabari (Sehore)', '004-002-016': 'Kuppa (North Betul)'}
RANGES = {('Sehore', 'Budhni'): 'Budhni range', ('North_Betul', 'Bhaura'): 'Bhaura range'}


def main():
    import json
    g = json.load(open('/mnt/project-files/ratapani/beats/mp_beats.geojson'))
    BT = pd.DataFrame([f['properties'] for f in g['features']])[['beat_uid', 'Division', 'Range', 'Beat', 'Beat_Ar']]
    V = pq.read_table(B.VIIRS, columns=['season', 'doy', 'sat', 'type', 'beat_uid']).to_pandas()
    V = V[(V.sat == 'snpp') & (V.type == 0) & V.doy.between(46, 166)]
    P = V.groupby(['beat_uid', 'season']).size().rename('pts').reset_index()
    E = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/mp_events.csv', usecols=['event_id', 'acq_date', 'beat_uid', 'rank'])
    E = E[E['rank'] == 1]; S = pd.read_csv('/mnt/project-files/fire-alert-scars/mp/out/scars_mp_hist.csv', usecols=['event_id', 'status', 'scar_ha'])
    E = E.merge(S, on='event_id'); E['season'] = pd.to_datetime(E.acq_date).dt.year
    H = E[E.status == 'scar'].groupby(['beat_uid', 'season']).scar_ha.sum().rename('scar_ha').reset_index()
    years = list(range(2014, 2027))
    full = BT[['beat_uid']].merge(pd.DataFrame({'season': years}), how='cross').merge(P, how='left').merge(H, how='left').fillna({'pts': 0, 'scar_ha': 0})
    full = full.merge(BT, on='beat_uid')
    full['period'] = np.where(full.season <= 2019, 'before', np.where(full.season >= 2021, 'after', 'drop'))
    full['treat_beat'] = full.beat_uid.map(TREAT); full['treat_range'] = [RANGES.get((d, r)) for d, r in zip(full.Division, full.Range)]
    rows = []

    def did(label, tmask, cmask, col, yrs=None):
        X = full[full.period != 'drop']
        if yrs is not None: X = X[X.season.isin(yrs)]
        t = X[tmask(X)].groupby('period')[col].mean(); c = X[cmask(X)].groupby('period')[col].mean()
        rt = t['after'] / t['before'] if t['before'] > 0 else np.nan; rc = c['after'] / c['before']
        rows.append(dict(test=label, outcome=col, treated_before=round(t['before'], 2), treated_after=round(t['after'], 2), treated_ratio=round(rt, 3),
                         control_before=round(c['before'], 2), control_after=round(c['after'], 2), control_ratio=round(rc, 3),
                         did_ratio=round(rt / rc, 3) if rc > 0 else np.nan, n_treated_beats=X[tmask(X)].beat_uid.nunique()))
    for col, yrs in (('pts', None), ('scar_ha', list(range(2017, 2026)))):
        for name, uid in [(v, k) for k, v in TREAT.items()]:
            div = BT.set_index('beat_uid').Division[uid]
            did(f'{name} vs other beats of {div}', lambda X, u=uid: X.beat_uid == u, lambda X, u=uid, d=div: (X.Division == d) & (X.beat_uid != u), col, yrs)
        did('3 named beats vs other beats of their divisions', lambda X: X.treat_beat.notna(), lambda X: X.Division.isin(['Sehore', 'North_Betul']) & X.treat_beat.isna(), col, yrs)
        for (d, r), lab in RANGES.items():
            did(f'{lab} vs other ranges of {d}', lambda X, d=d, r=r: (X.Division == d) & (X.Range == r), lambda X, d=d, r=r: (X.Division == d) & (X.Range != r), col, yrs)
        did('North Betul division vs all other MP beats', lambda X: X.Division == 'North_Betul', lambda X: X.Division != 'North_Betul', col, yrs)
        did('Sehore division vs all other MP beats', lambda X: X.Division == 'Sehore', lambda X: X.Division != 'Sehore', col, yrs)
    R = pd.DataFrame(rows); R.to_csv(B.OUT + 'cb10_nets.csv', index=False); print(R.to_string(index=False))
    # per-year series for the named beats and their divisions
    T = full[full.treat_beat.notna()].pivot_table(index='season', columns='treat_beat', values='pts', aggfunc='sum')
    D = full.groupby(['Division', 'season']).pts.sum().unstack(0)[['Sehore', 'North_Betul']]; D['all MP'] = full.groupby('season').pts.sum()
    out = pd.concat([T, D], axis=1); out.to_csv(B.OUT + 'cb10_series.csv'); print(out.astype(int).to_string())
    # placebo: distribution of beat-level DiD ratios for all beats with >= 5 points/season before, in the two divisions
    X = full[(full.period != 'drop') & full.Division.isin(['Sehore', 'North_Betul'])]
    bb = X.groupby(['beat_uid', 'period']).pts.mean().unstack(); bb = bb[bb.before >= 3]
    ref = X.groupby('period').pts.mean(); rr = (bb.after / bb.before) / (ref.after / ref.before)
    print('placebo beats (before >= 3 pts/season):', len(rr), 'share with DiD ratio <= 0.3:', round((rr <= 0.3).mean(), 3), 'median', round(rr.median(), 2))
    print('named beats DiD:', rr.reindex(list(TREAT)).round(2).to_dict())


if __name__ == '__main__':
    main()
