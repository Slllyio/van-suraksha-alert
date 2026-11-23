"""Read every chip's full image stack (all S2 + Landsat looks, -30..+40 days) into scratch. Resumable.
Usage: python fetch.py [n_workers]. Log: scratch/fetch_log.csv (seconds per chip)."""
import sys, os, time, numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from lib import SCR, CODE, read_stack
C = pd.read_csv(CODE + 'chips.csv')
order = {'train_af': 6, 'train_alert': 0, 'wb_real': 1, 'wb_decoy': 2, 'train_control': 3, 'af_nofirms': 4, 'af_firms': 4, 'photo': 5}
C = C.assign(o=C.kind.map(order)).sort_values(['o', 'chip'])


def one(d):
    from types import SimpleNamespace; r = SimpleNamespace(**d)
    f = f'{SCR}stacks/{r.chip}.npz'
    if os.path.exists(f):
        return None
    t = time.time()
    for k in range(3):
        try:
            st = read_stack(r.x, r.y, r.date, half_m=r.half)
            np.savez_compressed(f + '.tmp.npz', **st); os.replace(f + '.tmp.npz', f)
            return dict(chip=r.chip, kind=r.kind, sec=round(time.time() - t, 1), n_looks=len(st['dates']), n=st['n'])
        except Exception as e:
            err = str(e)[:150]; time.sleep(5)
    return dict(chip=r.chip, kind=r.kind, sec=round(time.time() - t, 1), err=err)


if __name__ == '__main__':
    nw = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    log = SCR + 'fetch_log.csv'
    with ProcessPoolExecutor(nw) as ex:
        for res in ex.map(one, C.drop(columns='o').to_dict('records')):
            if res:
                pd.DataFrame([res]).to_csv(log, mode='a', header=not os.path.exists(log), index=False)
