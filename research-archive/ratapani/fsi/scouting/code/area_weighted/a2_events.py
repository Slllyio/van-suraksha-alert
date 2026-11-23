"""Step 1: one row per fire event (round-22 strict events: 3x3 x consecutive-day components of target VIIRS fire square-days,
per division) with its burnt area.
- Test events: the round-22 event tables (scratch r22 eval_held_sub.pkl 2022-24, eval_fwd_sub.pkl, 2025 kept).
- Training events 2019-21: the same evalr._prep_div run on those seasons (saved to scratch r24 eval_train_sub.pkl).
Area truths:
- scar: a scar event (a1_scars) belongs to a VIIRS event when its alert square, or a square next to it, is part of that event
  on the scar event's date (else on the day before/after). The event's scar area = area of the union of all its matched
  outlines (status scar or scar_faint), so a multi-day fire whose daily scars overlap is not counted twice.
- viirs: distinct 500 m squares the event lit over all its days, turned into hectares with a log-log law fitted on events
  that have a scar (second truth, used only where no scar exists).
Out (scratch r24): events.parquet, fd_cells.parquet (first-day squares of each event, for the size model)."""
import os, pickle, numpy as np, pandas as pd, shapely
from multiprocessing import Pool
import aw_common as A
C, E = A.C, A.E


def train_prep():
    fn = A.S24 + 'eval_train_sub.pkl'
    if os.path.exists(fn): return pickle.load(open(fn, 'rb'))
    v = C.load_det(range(2018, 2022)); v = v[v.type == 0][['row', 'col', 'ld', 'ctrl']].drop_duplicates()
    G = C.grids_active()
    with Pool(3) as p: R = p.map(E._prep_div, [(k, r, c, v, (2019, 2020, 2021)) for k, (r, c) in G.items()], chunksize=1)
    R = {d['name']: d for d in R}
    for d in R.values():   # keep only what this round needs
        for k in ('Y', 'CLEAR', 'stv', 'bcol', 'inb', 'rng_of'): d.pop(k, None)
    pickle.dump(R, open(fn, 'wb'), protocol=4); return R


def event_rows(d, scars, keep_seasons):
    labc = d['labc']; T = len(d['DAYS']); n_ev = d['n_ev']; DAYS = d['DAYS']
    t, i = np.nonzero(labc); lab = labc[t, i]
    ncell = np.zeros(n_ev + 1, int); ndays = np.zeros(n_ev + 1, int)
    u = np.unique(lab * 10 ** 6 + i); np.add.at(ncell, u // 10 ** 6, 1)
    u = np.unique(lab * 10 ** 4 + t); np.add.at(ndays, u // 10 ** 4, 1)
    first = np.full(n_ev + 1, T); np.minimum.at(first, lab, t)
    fdt, fdi, fdl = d['fd']
    nfd = np.bincount(fdl, minlength=n_ev + 1)
    # scar matching
    cell_ix = dict(zip((d['rows'].astype(np.int64) * C.W + d['cols']).tolist(), range(len(d['rows']))))
    day_ix = pd.Series(np.arange(T), index=DAYS)
    sc = scars[scars.ld.isin(DAYS)]
    match = {}
    for eid, ld, r0, c0 in zip(sc.event_id.values, sc.ld.values, sc.row.values, sc.col.values):
        td = day_ix[pd.Timestamp(ld)]; got = 0
        for dt in (0, -1, 1):
            tt = td + dt
            if tt < 0 or tt >= T: continue
            if dt != 0 and tt < T and (DAYS[tt] - DAYS[td]).days != dt: continue
            cand = []
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    k = (r0 + dr) * C.W + c0 + dc
                    if k in cell_ix:
                        l = labc[tt, cell_ix[k]]
                        if l > 0: cand.append((abs(dr) + abs(dc), l))
            if cand:
                got = min(cand)[1]; break
        if got: match.setdefault(got, []).append(eid)
    ids = np.arange(1, n_ev + 1)
    out = pd.DataFrame(dict(division=d['name'], ev=ids, season=d['ev_season'][ids], first_day=DAYS[np.minimum(first[ids], T - 1)],
                            valid=d['valid'][ids], new=d['newev'][ids], ncell=ncell[ids], ndays=ndays[ids], nfd=nfd[ids]))
    out = out[out.season.isin(keep_seasons)]
    st = scars.set_index('event_id')
    sha, nsc, nout, stat = [], [], [], []
    for l in out.ev.values:
        es = match.get(l, [])
        nsc.append(len(es))
        gs = [st.geom_wkb[e] for e in es if st.status[e] in ('scar', 'scar_faint') and st.geom_wkb[e] is not None]
        nout.append(len(gs))
        if gs:
            sha.append(shapely.union_all([shapely.from_wkb(g) for g in gs]).area / 1e4); stat.append('scar')
        elif es and any(st.status[e] == 'no_scar_seen' for e in es): sha.append(np.nan); stat.append('no_scar_seen')
        elif es: sha.append(np.nan); stat.append('other')
        else: sha.append(np.nan); stat.append('unmatched')
    out['scar_ha'] = sha; out['n_scar_ev'] = nsc; out['n_outlines'] = nout; out['scar_status'] = stat
    fd = pd.DataFrame(dict(division=d['name'], ev=fdl, t=fdt, i=fdi, day=DAYS[fdt]))
    fd = fd[fd.ev.isin(out.ev)]
    fd['row'] = d['rows'][fd.i.values]; fd['col'] = d['cols'][fd.i.values]
    return out, fd


def main():
    scars = pd.read_parquet(A.S24 + 'scar_ev.parquet')
    srcs = [(train_prep(), (2019, 2020, 2021)),
            (pickle.load(open(C.SC + 'eval_held_sub.pkl', 'rb')), (2022, 2023, 2024)),
            (pickle.load(open(C.SC + 'eval_fwd_sub.pkl', 'rb')), (2025,))]
    EV, FD = [], []
    for R, ks in srcs:
        for nm, d in R.items():
            if nm.startswith('_'): continue
            e, f = event_rows(d, scars, ks); EV.append(e); FD.append(f); print(nm, ks, len(e), flush=True)
        del R
    ev = pd.concat(EV, ignore_index=True); fd = pd.concat(FD, ignore_index=True)
    # VIIRS area law on events with a clear scar (log ha = a + b log squares)
    m = (ev.scar_status == 'scar') & (ev.scar_ha > 0)
    b, a = np.polyfit(np.log(ev.ncell[m]), np.log(ev.scar_ha[m]), 1)
    ev['viirs_ha'] = np.exp(a) * ev.ncell ** b
    ev['area_ha'] = np.where(ev.scar_status == 'scar', ev.scar_ha, ev.viirs_ha)
    ev['area_src'] = np.where(ev.scar_status == 'scar', 'scar', 'viirs')
    rho = pd.Series(ev.scar_ha[m]).corr(pd.Series(ev.viirs_ha[m]), method='spearman')
    print('VIIRS law: ha = %.2f * squares^%.3f; Spearman with scar %.3f' % (np.exp(a), b, rho))
    pd.Series(dict(a=np.exp(a), b=b, spearman=rho, n=int(m.sum()))).to_json(A.OUT + 'viirs_area_law.json')
    ev.to_parquet(A.S24 + 'events.parquet', index=False); fd.to_parquet(A.S24 + 'fd_cells.parquet', index=False)
    print(pd.crosstab(ev.season, ev.scar_status).to_string())


if __name__ == '__main__':
    main()
