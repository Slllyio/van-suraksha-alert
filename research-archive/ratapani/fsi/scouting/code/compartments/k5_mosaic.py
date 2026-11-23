"""Part B helper. Statewide 120 m mosaic of repeat burning (seasons burnt 2017-25 and 2017-21 per 120 m forest cell, from the round-26
per-division count rasters) and per-division summaries for the conference paper maps.
Out (scratch r27): mosaic.npz (UTM 43N grid, 120 m: cnt_all, cnt_tr, forest, x0, y1); out/division_summary.csv"""
import pickle, glob
import numpy as np, pandas as pd
import k0 as K

R120 = 120.0


def main():
    keys = sorted(p.split('patches_')[1][:-4] for p in glob.glob(K.SC26 + 'patches_*.npz'))
    win = {}
    for k in keys:
        L = pickle.load(open(K.SC26 + f'fires_{k}.pkl', 'rb')); win[k] = (L['x0'], L['y1'], L['W'], L['H'], L['div'])
    X0 = min(v[0] for v in win.values()); Y1 = max(v[1] for v in win.values())
    X1 = max(v[0] + v[2] * K.RES for v in win.values()); Y0 = min(v[1] - v[3] * K.RES for v in win.values())
    NW = int(np.ceil((X1 - X0) / R120)) + 2; NH = int(np.ceil((Y1 - Y0) / R120)) + 2
    CA = np.full((NH, NW), -1, np.int8); CT = np.full((NH, NW), -1, np.int8)
    P5 = np.zeros((NH, NW), bool); P3 = np.zeros((NH, NW), bool)
    rows = []
    for k in keys:
        Z = np.load(K.SC26 + f'patches_{k}.npz'); x0, y1, W, H, div = win[k]
        m = (Z['fb'] >= 2) & Z['ins']
        c0 = int(round((x0 - X0) / R120)); r0 = int(round((Y1 - y1) / R120)); h, w = m.shape
        sub = CA[r0:r0 + h, c0:c0 + w]; sub[m] = Z['cnt_all'][m]
        sub = CT[r0:r0 + h, c0:c0 + w]; sub[m] = Z['cnt_tr'][m]
        P5[r0:r0 + h, c0:c0 + w] |= (Z['lab_all5'] > 0) & Z['ins']; P3[r0:r0 + h, c0:c0 + w] |= (Z['lab_tr3'] > 0) & Z['ins']
        ca = Z['cnt_all'][m]
        rows.append(dict(key=k, division=div, set='core' if k in K.CORE else 'rest', forest_cells_120=int(m.sum()),
                         forest_kha=round(m.sum() * 1.44 / 1e3, 1), burnt_once_pct=round(100 * (ca >= 1).mean(), 1),
                         mean_seasons=round(float(ca.mean()), 3), ge5of9_pct=round(100 * (ca >= 5).mean(), 2),
                         n_patch_tr3=int(Z['lab_tr3'].max()), n_patch_all5=int(Z['lab_all5'].max())))
    np.savez_compressed(K.SC + 'mosaic.npz', cnt_all=CA, cnt_tr=CT, p5=P5, p3=P3, x0=X0, y1=Y1, res=R120)
    pd.DataFrame(rows).to_csv(K.OUT + 'division_summary.csv', index=False)
    print(NH, NW, len(rows), flush=True)


if __name__ == '__main__':
    main()
