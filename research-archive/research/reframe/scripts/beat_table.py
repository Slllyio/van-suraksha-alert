"""Beat-day table: one row per (season, issue day t, beat). Features use only what is known by the end of day t.
Targets (first burn per cell-season; a burn's day = its VIIRS date where one lies in the scar window, else the window midpoint):
  y{H}      any first burn in the beat in (t, t+H]                 H = 2, 7
  n{H}      number of first-burned cells in (t, t+H]
  v{H}      any S-NPP VIIRS point in the beat in (t, t+H]          (clean day, misses small fires)
  s{H}      any first-burn scar window overlapping (t, t+H]        (the blurred scar rule)"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D

def build():
    c = D.cells(); v = D.viirs(); b = D.burns(); w = D.weather(); lp = D.lean_preds()
    beats = sorted(c.beat_uid.dropna().unique()); bi = {x: k for k, x in enumerate(beats)}; nb = len(beats)
    cb = c.beat_uid.map(bi).values
    # beat adjacency through 4-neighbour cells
    key = {(int(x // 500), int(y // 500)): i for i, x, y in zip(c.cell_id, c.x, c.y)}
    A = np.zeros((nb, nb), bool)
    for i, x, y in zip(c.cell_id, c.x, c.y):
        for dx, dy in ((1, 0), (0, 1)):
            j = key.get((int(x // 500) + dx, int(y // 500) + dy))
            if j is not None and cb[i] != cb[j]: A[cb[i], cb[j]] = A[cb[j], cb[i]] = True
    ncell = np.bincount(cb, minlength=nb); forest = np.bincount(cb, c.forest_frac.values, minlength=nb) / ncell
    vs = v[v.satellite == 'N']   # S-NPP only: same sensor every season
    fb = b[b['first']].copy(); mid = fb.ws + (fb.we - fb.ws) / 2
    fb['bday'] = fb.vday.fillna(mid.dt.floor('D')); fb['beat'] = cb[fb.cell_id.values]
    lp['beat'] = cb[lp.cell_id.values]
    rows = []
    for Y in D.SEASONS:
        days = pd.date_range(f'{Y}-01-01', f'{Y}-06-30'); T = len(days); d0 = days[0]
        V = np.zeros((T, nb)); g = vs[(vs.date >= d0) & (vs.date <= days[-1])]
        np.add.at(V, ((g.date - d0).dt.days.values, cb[g.cell_id.values]), 1)
        FB = np.zeros((T, nb)); f = fb[(fb.season == Y)]
        k = (f.bday - d0).dt.days.values; ok = (k >= 0) & (k < T)
        np.add.at(FB, (k[ok], f.beat.values[ok]), 1)
        SEEN = np.zeros((T, nb)); k2 = (f.we - d0).dt.days.values; ok2 = (k2 >= 0) & (k2 < T)
        np.add.at(SEEN, (np.clip(k2[ok2], 0, T - 1), f.beat.values[ok2]), 1)    # scar becomes known on its window end
        OV = {}
        for H in (2, 7):
            o = np.zeros((T, nb))
            for ws, we, bt in zip((f.ws - d0).dt.days.values, (f.we - d0).dt.days.values, f.beat.values):
                lo_, hi_ = max(ws - H + 1, 0), min(we - 1, T - 1)   # t with (ws,we] overlapping (t,t+H]
                if hi_ >= lo_: o[lo_:hi_ + 1, bt] = 1
            OV[H] = o
        cumV = V.cumsum(0); cumFBseen = SEEN.cumsum(0)
        def lag(M, n):   # sum over days t-n+1..t
            cs = np.vstack([np.zeros((1, nb)), M.cumsum(0)]); idx = np.arange(T)
            return cs[idx + 1] - cs[np.maximum(idx + 1 - n, 0)]
        def lead(M, H):  # sum over t+1..t+H
            cs = np.vstack([np.zeros((1, nb)), M.cumsum(0)]); idx = np.arange(T)
            return cs[np.minimum(idx + 1 + H, T)] - cs[idx + 1]
        Vl1, Vl3, Vl7 = lag(V, 1), lag(V, 3), lag(V, 7)
        S14 = lag(SEEN, 14)
        adj3 = (Vl3 @ A.T.astype(float)); adj1 = (Vl1 @ A.T.astype(float))
        san1, san3, san7 = Vl1.sum(1), Vl3.sum(1), Vl7.sum(1)
        lastV = np.full(nb, -999); dsl = np.zeros((T, nb))
        for t in range(T):
            lastV = np.where(V[t] > 0, t, lastV); dsl[t] = np.minimum(t - lastV, 60)
        lpY = lp[lp.season == Y]
        agg = lpY.groupby(['date', 'beat']).pipeline_lean.agg(['sum', 'max', 'count', 'mean'])
        top5 = lpY.sort_values('pipeline_lean', ascending=False).groupby(['date', 'beat']).head(5).groupby(['date', 'beat']).pipeline_lean.mean()
        sel = (days >= pd.Timestamp(f'{Y}-02-01')) & (days <= pd.Timestamp(f'{Y}-06-20'))
        for t in np.nonzero(sel)[0]:
            r = pd.DataFrame(dict(season=Y, date=days[t], beat=np.arange(nb), ncell=ncell, forest=forest,
                                  v_l1=Vl1[t], v_l3=Vl3[t], v_l7=Vl7[t], v_season=cumV[t], v_dsl=dsl[t],
                                  adj_l1=adj1[t], adj_l3=adj3[t], san_l1=san1[t], san_l3=san3[t], san_l7=san7[t],
                                  seen_share=cumFBseen[t] / ncell, seen14=S14[t] / ncell, san_seen=cumFBseen[t].sum() / ncell.sum()))
            for H in (2, 7):
                r[f'y{H}'] = (lead(FB, H)[t] > 0).astype(int); r[f'n{H}'] = lead(FB, H)[t]
                r[f'v{H}'] = (lead(V, H)[t] > 0).astype(int); r[f's{H}'] = (lead(OV[H] if False else FB, 0)[t] * 0 + OV[H][t]).astype(int)
            rows.append(r)
        print(Y, flush=True)
    df = pd.concat(rows, ignore_index=True)
    lpa = agg.reset_index() if False else None
    # lean aggregates per beat-day (all seasons)
    allagg = lp.groupby(['date', 'beat']).pipeline_lean.agg(lean_sum='sum', lean_max='max', lean_n='count', lean_mean='mean').reset_index()
    t5 = lp.sort_values('pipeline_lean', ascending=False).groupby(['date', 'beat']).head(5).groupby(['date', 'beat']).pipeline_lean.mean().rename('lean_top5').reset_index()
    df = df.merge(allagg, on=['date', 'beat'], how='left').merge(t5, on=['date', 'beat'], how='left')
    for col in ('lean_sum', 'lean_max', 'lean_n', 'lean_mean', 'lean_top5'): df[col] = df[col].fillna(0)
    df['lean_rate'] = df.lean_sum / df.ncell
    df = df.merge(w, on='date', how='left'); df['doy'] = df.date.dt.dayofyear
    df['beat_uid'] = [beats[i] for i in df.beat]
    df.to_parquet(D.OUT + 'beat_day.parquet'); return df

if __name__ == '__main__':
    df = build(); print(df.shape)
    for c in ('y2', 'y7', 'v2', 'v7', 's2', 's7'): print(c, round(df[c].mean(), 4))
