"""Step 3 inputs. Per division-season-5 km square: forest ha burnt in 15-28 Feb (p1), 1-15 Mar (p2), 16 Mar-15 Jun (late),
Jan-14 Feb VIIRS points (eb), late VIIRS points, forest ha. Also: statewide weekly forest ha burnt; weekly outside-patch ha for
fires that started inside all5 repeat patches; fire sizes by start week (escape risk).
Out: out/cb3_squares.parquet, out/cb3_weekly.csv, out/cb3_sizes.csv"""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/fire_lines_v2/')
import cb0 as B
import m0 as M


def run(key):
    L, FOR = B.load_div(key); H, W = L['H'], L['W']
    sq = (np.arange(H)[:, None] // B.SQ) * 1000 + (np.arange(W)[None, :] // B.SQ)
    Z = np.load(B.SC26 + f'patches_{key}.npz'); LAB = M.labels(Z, 'all5', H, W).ravel()
    fha = pd.Series(np.bincount(sq[FOR].ravel()) * B.CELL_HA).rename_axis('sq').reset_index(name='forest_ha'); fha = fha[fha.forest_ha > 0]
    rows, wk, sizes = [], [], []
    for y in B.YEARS:
        bd = B.burn_day(L, y)
        P = B.points(L['div'], y); r, c = B.rc(L, P.latitude.values, P.longitude.values)
        ok = (r >= 0) & (r < H) & (c >= 0) & (c < W) & FOR[np.clip(r, 0, H - 1), np.clip(c, 0, W - 1)]; r, c, doy = r[ok], c[ok], P.doy.values[ok]
        per = np.where(bd < 60, 0, np.where(bd < 75, 1, np.where(bd < 9999, 2, 3)))
        for name, k in (('ha_p1', 0), ('ha_p2', 1), ('ha_late', 2)):
            m = FOR & (per == k); cnt = np.bincount(sq[m].ravel(), minlength=sq.max() + 1) * B.CELL_HA
            for s in np.nonzero(cnt)[0]: rows.append((key, y, int(s), name, float(cnt[s])))
        for name, m in (('eb_pts', doy < B.D0), ('late_pts', doy >= 75)):
            cnt = np.bincount(sq[r[m], c[m]], minlength=sq.max() + 1)
            for s in np.nonzero(cnt)[0]: rows.append((key, y, int(s), name, float(cnt[s])))
        # weekly burnt forest ha, all and outside-patch for patch-start fires
        wkall = np.bincount(((bd[FOR & (bd < 9999)] - B.D0) // 7).clip(0, 20), minlength=21) * B.CELL_HA
        wkout = np.zeros(21)
        for f in L['fires']:
            if f['year'] != y: continue
            h, w = f['shape']; ig = f['ign'].astype(np.int64); gi = (ig // w + f['r0']) * W + (ig % w + f['c0'])
            lb = LAB[gi]; lb = lb[lb > 0]
            if len(lb) == 0 or len(lb) * 2 < len(ig): continue
            p = int(np.bincount(lb).argmax())
            Mm = np.unpackbits(f['M'])[:h * w].astype(bool); loc = np.nonzero(Mm)[0]; gl = (loc // w + f['r0']) * W + (loc % w + f['c0'])
            out = FOR.ravel()[gl] & (LAB[gl] != p)
            d = ((f['t0'].dayofyear + f['day'].astype(int) - B.D0) // 7).clip(0, 20)
            wkout += np.bincount(d[out], minlength=21)[:21] * B.CELL_HA
        for i in range(21): wk.append((key, y, i, wkall[i], wkout[i]))
        for f in L['fires']:
            if f['year'] == y: sizes.append((key, y, f['t0'].dayofyear, f['ha'], f['forest_ha']))
    S = pd.DataFrame(rows, columns=['key', 'year', 'sq', 'var', 'val']).pivot_table(index=['key', 'year', 'sq'], columns='var', values='val', fill_value=0).reset_index()
    S = S.merge(fha, on='sq')
    return S, pd.DataFrame(wk, columns=['key', 'year', 'week', 'ha_all', 'ha_out_patch']), pd.DataFrame(sizes, columns=['key', 'year', 'doy', 'ha', 'forest_ha'])


if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool(2) as pool: res = pool.map(run, B.KEYS, chunksize=1)
    pd.concat([r[0] for r in res]).to_parquet(B.OUT + 'cb3_squares.parquet')
    pd.concat([r[1] for r in res]).to_csv(B.OUT + 'cb3_weekly.csv', index=False)
    pd.concat([r[2] for r in res]).to_csv(B.OUT + 'cb3_sizes.csv', index=False)
    print('done')
