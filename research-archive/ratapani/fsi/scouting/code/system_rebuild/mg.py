"""Matched-ground comparison: for each variant (saved cube), find the flag fraction at which its ground share (flagged or
next to a flag) equals the reference's ground share at the standard 10%, re-score there, and paired-bootstrap against the
reference. Usage: python3 mg.py period ref var1 var2 ... Out: out/matched_{period}{tag}.csv"""
import sys, pickle, json, numpy as np, pandas as pd
import common as C, evalr as E, features as Fe
if __name__ == '__main__':
    per, ref = sys.argv[1], sys.argv[2]; vs = sys.argv[3:]; U = Fe.base()['U']
    cr = pickle.load(open(C.SC + f'cube_{ref}_{per}{C.TAG}.pkl', 'rb')); sr, er, _ = E.score(cr, U, per); tg = sr['ground']; del cr
    rows = [dict(variant=ref, q=0.90, ground=sr['ground'], all=sr['all'], new=sr['new'], beats=sr['beats'])]
    for v in vs:
        cu = pickle.load(open(C.SC + f'cube_{v}_{per}{C.TAG}.pkl', 'rb'))
        _, T = E.score_matched(cu, U, per, tg, qs=(0.90, 0.92, 0.94, 0.95))
        q = float(np.interp(tg, T.ground, T.q)); s, ev, _ = E.score(cu, U, per, q=q); d = E.paired(er, ev)
        rows.append(dict(variant=v, q=round(q, 4), ground=s['ground'], all=s['all'], new=s['new'], beats=s['beats'], d_all=d['all'][0], d_all_lo=d['all'][1], d_all_hi=d['all'][2],
                         d_new=d['new'][0], d_new_lo=d['new'][1], d_new_hi=d['new'][2]))
        print(rows[-1], flush=True)
    T = pd.DataFrame(rows).round(2); fn = C.OUT + f'matched_{per}{C.TAG}.csv'
    try: old = pd.read_csv(fn); T = pd.concat([old[~old.variant.isin(T.variant)], T])
    except FileNotFoundError: pass
    T.to_csv(fn, index=False); print(T.to_string())
