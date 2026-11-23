"""Collect every scored variant (out/results/*.json) and add the paired bootstrap difference against a reference variant
(same fires, 2,000 resamples of fires). Usage: python3 compare.py [period] [ref]. Out: out/compare_{period}{tag}.csv"""
import sys, glob, json, os, pandas as pd
import common as C, evalr as E

if __name__ == '__main__':
    per = sys.argv[1] if len(sys.argv) > 1 else 'held'; ref = sys.argv[2] if len(sys.argv) > 2 else 'B0'
    rows = []; er = pd.read_parquet(C.SC + f'ev_{ref}_{per}{C.TAG}.parquet')
    for f in sorted(glob.glob(C.OUT + f'results/*_{per}{C.TAG}.json')):
        s = json.load(open(f)); nm = s.get('variant', os.path.basename(f))
        r = dict(variant=nm, all=s['all'], new=s['new'], old=s['old'], beats=s['beats'], ground=s['ground'], bpr=s['bpr'], n_fires=s['n_fires'], n_new=s['n_new'])
        fe = C.SC + f'ev_{nm}_{per}{C.TAG}.parquet'
        if os.path.exists(fe) and nm != ref:
            ev = pd.read_parquet(fe)
            if len(ev) == len(er):
                d = E.paired(er, ev)
                r.update(d_all=d['all'][0], d_all_lo=d['all'][1], d_all_hi=d['all'][2], d_new=d['new'][0], d_new_lo=d['new'][1], d_new_hi=d['new'][2])
        rows.append(r)
    T = pd.DataFrame(rows).round(2); T.to_csv(C.OUT + f'compare_{per}{C.TAG}.csv', index=False); print(T.to_string())
