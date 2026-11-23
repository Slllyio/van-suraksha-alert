"""Window labels for the 48 h target from the research thread's burn-scar files (read-only inputs).
For issue day t the target is 'cell burns on day t+1 or t+2'.  A scar seen first at window_end (we) after a clear
unburned look at window_start (ws) burned somewhere in (ws, we], so every issue day t in [ws-1, we-1] is a positive.
Days after we are masked (already burned) until the next window; days with t+2 after the cell's last clear look are
masked (not seen).  Everything else seen unburned is a negative.  Output scar_labels.npz: L (T x n, 0/1), valid (T x n)."""
import sys, numpy as np, pandas as pd
H = int(sys.argv[1]) if len(sys.argv) > 1 else 2   # horizon in days: target = burns in (t, t+H]
MODE = sys.argv[2] if len(sys.argv) > 2 else 'gap'  # gap: mask between burns (original, biased); first: first burn per season only; open: post-burn days stay valid
D = '/mnt/project-files/research/ratapani-burn-labels/'
DAYS = pd.date_range('2012-10-01', '2024-12-31', freq='D'); T = len(DAYS); di = {d: i for i, d in enumerate(DAYS)}
n = 3614
bw = pd.read_csv(D + 'burn_windows.csv', parse_dates=['window_start', 'window_end'])
cc = pd.read_parquet(D + 'clear_calendar.parquet'); cc['date'] = pd.to_datetime(cc['date'])
L = np.zeros((T, n), np.int8); valid = np.zeros((T, n), bool); seasons = sorted(s for s in bw.season.unique() if s <= 2024)
C = np.zeros((len(seasons), n), np.float32)   # cell burned this season (>=0.5 ha), for the leave-season-out prior
for k, Y in enumerate(seasons):
    lo, hi = di[pd.Timestamp(f'{Y}-01-01')], di[pd.Timestamp(f'{Y}-06-20')]
    seen = cc[(cc.season == Y) & (cc.clear_frac >= 0.5)].groupby('cell_id').date.max()
    last = np.full(n, -1); last[seen.index.values] = [di[d] for d in seen.values]
    for c in range(n):                                 # negatives wherever t+2 <= last clear look
        if last[c] >= lo: valid[lo:min(last[c] - H, hi) + 1, c] = True
    w = bw[(bw.season == Y) & (bw.burned == 1)].sort_values(['cell_id', 'window_end'])
    for c, g in w.groupby('cell_id'):
        C[k, c] = 1
        ends = [di[d] for d in g.window_end]; starts = [di[d] for d in g.window_start]
        for q, (s, e) in enumerate(zip(starts, ends)):
            a, b = max(s - H + 1, lo), min(e - 1, hi)
            L[a:b + 1, c] = 1; valid[a:b + 1, c] = True
            if MODE == 'first':
                L[e:hi + 1, c] = 0; valid[e:hi + 1, c] = False; break     # rest of season masked after the first burn
            if MODE == 'gap':
                nxt = starts[q + 1] - H if q + 1 < len(starts) else hi
                valid[e:nxt + 1, c] = False             # already burned: not a candidate until it burns again (biased)
    sv = valid[lo:hi + 1]; sl = L[lo:hi + 1]
    print(f'{Y}: valid cell-days {sv.mean():.1%}, positive share of valid {sl[sv].mean():.2%}, cells burned {int(C[k].sum())}', flush=True)
np.savez_compressed(f'scar_labels_H{H}.npz' if MODE == 'gap' else f'scar_labels_H{H}_{MODE}.npz', L=L, valid=valid, C=C, seasons=np.array(seasons))
print('saved')
