"""Step 2. Repeat-burn patches.
Per division, on a 120 m grid (2 x 2 VTM cells): a 120 m cell burned in a season if >= 2 of its four 60 m cells are forest/scrub
AND inside a scar of that season (outlines clipped to VTM forest/scrub). Count seasons burned.
Patch = 8-connected area of cells burned in >= K of N seasons, at least 10 ha.
Patch sets: training 2017-21 with K = 3, 4, 5 (of 5); all seasons 2017-25 with K = 5 (majority), 7, 9 (of 9).
Also: share of each season's burnt forest that lies in the patches (in-sample for the seasons that define them; the 2017-21
patches against 2022-25 burns is the held-out check), and the share of forest the patches cover.
Out (scratch r26): patches_<div>.npz (count rasters, labels per patch set), patch_stats.csv"""
import pickle, glob, sys
import numpy as np, pandas as pd
from scipy import ndimage as ndi
import c26 as C

SETS = {'tr3': ('train', 3), 'tr4': ('train', 4), 'tr5': ('train', 5), 'all5': ('all', 5), 'all7': ('all', 7), 'all9': ('all', 9)}


def unpack(f):
    return np.unpackbits(f['M'])[:f['shape'][0] * f['shape'][1]].reshape(f['shape']).astype(bool)


def year_burn(L):
    H, W = L['H'], L['W']; FOR = np.unpackbits(L['forest'])[:H * W].reshape(H, W).astype(bool)
    B = {y: np.zeros((H, W), bool) for y in C.ALL}
    for f in L['fires']:
        if f['year'] not in B: continue
        M = unpack(f); r0, c0 = f['r0'], f['c0']
        B[f['year']][r0:r0 + M.shape[0], c0:c0 + M.shape[1]] |= M
    for y in B: B[y] &= FOR
    return FOR, B


def agg(a, k=C.AGG):
    H, W = a.shape; Hb, Wb = -(-H // k), -(-W // k)
    p = np.zeros((Hb * k, Wb * k), a.dtype); p[:H, :W] = a
    return p.reshape(Hb, k, Wb, k).sum((1, 3))


def inside_mask(L, key):
    import geopandas as gpd
    from rasterio import features
    from rasterio.transform import Affine
    DV = gpd.read_file(C.C25.P + 'fire-alert-scars/mp/out/mp_divisions.geojson').to_crs(32643)
    DV = DV[DV.Division.map(C.slug) == key]
    return features.rasterize([(g, 1) for g in DV.geometry], out_shape=(L['H'], L['W']), transform=Affine(C.RES, 0, L['x0'], 0, -C.RES, L['y1']), dtype='uint8').astype(bool)


def main(key):
    L = pickle.load(open(C.SC + f'fires_{key}.pkl', 'rb'))
    FOR, B = year_burn(L); INS = inside_mask(L, key)
    fb = agg(FOR.astype(np.int16))
    burn120 = {y: (agg(B[y].astype(np.int16)) >= 2) & (fb >= 2) for y in C.ALL}
    cnt_tr = sum(burn120[y].astype(np.int8) for y in C.TRAIN); cnt_all = sum(burn120[y].astype(np.int8) for y in C.ALL)
    out = dict(cnt_tr=cnt_tr, cnt_all=cnt_all, fb=fb.astype(np.int8), ins=agg(INS.astype(np.int16)) >= 2)
    rows = []
    burnt_ha = {y: B[y].sum() * C.CELL_HA for y in C.ALL}
    st = np.ones((3, 3), bool)
    for s, (which, K) in SETS.items():
        cnt = cnt_tr if which == 'train' else cnt_all
        lab, n = ndi.label(cnt >= K, structure=st)
        if n:
            area = ndi.sum(fb, lab, np.arange(1, n + 1)) * C.CELL_HA   # forest ha per patch
            keep = np.r_[False, area >= C.MIN_PATCH_HA]
            ren = np.zeros(n + 1, np.int32); ren[keep] = np.arange(1, keep.sum() + 1); lab = ren[lab]
            n = int(keep.sum())
        out['lab_' + s] = lab.astype(np.int32)
        m60 = np.kron(lab > 0, np.ones((C.AGG, C.AGG), bool))[:FOR.shape[0], :FOR.shape[1]]
        row = dict(key=key, div=L['div'], set=s, which=which, K=K, n_patches=n, patch_forest_ha=float((m60 & FOR).sum() * C.CELL_HA),
                   forest_ha=float((FOR & INS).sum() * C.CELL_HA), forest_ha_window=float(FOR.sum() * C.CELL_HA))
        for y in C.ALL:
            row[f'burnt_{y}'] = burnt_ha[y]; row[f'inpatch_{y}'] = float((B[y] & m60).sum() * C.CELL_HA)
        rows.append(row)
    # how many seasons a burnt cell burns (120 m), per year: share of a season's burnt forest cells that burned in >= 3 / 5 of 2017-21
    np.savez_compressed(C.SC + f'patches_{key}.npz', **out)
    print(key, {r['set']: r['n_patches'] for r in rows}, flush=True)
    return rows


if __name__ == '__main__':
    keys = sys.argv[1:] or [p.split('fires_')[1][:-4] for p in sorted(glob.glob(C.SC + 'fires_*.pkl'))]
    from multiprocessing import Pool
    with Pool(4) as p: rows = sum(p.map(main, keys, chunksize=1), [])
    pd.DataFrame(rows).to_csv(C.SC + 'patch_stats.csv', index=False)
