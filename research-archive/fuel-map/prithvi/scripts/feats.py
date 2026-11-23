"""Per-season feature grids on the 240 m token grid (centre of node m at px 8m of the 30 m HLS grid):
  prithvi: PCA of frozen Prithvi tokens (frame-mean last layer 32 comps, Feb-minus-Nov change 16 comps, layer-12 mean 16 comps)
  raw: the same HLS pixels Prithvi saw, averaged over the same 480 m token window: 6 bands x 4 frames + NDVI/NBR/NDMI x 4 frames.
PCA is fitted on 2017-2024 tokens only (never on 2025-26).  Out: scratch feats/{Y}_{prithvi,raw}.npy (R, C, k) float32 + names."""
import os, sys, json, numpy as np
from sklearn.decomposition import PCA
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'; os.makedirs(f'{SP}/feats', exist_ok=True)
H, W = 1120, 2500; R, C = H // 8 + 1, W // 8 + 1
SEAS = list(range(2017, 2027))
def raw(Y):
    out = []
    for k in (1, 2, 3, 4):
        a = np.load(f'{SP}/hls/{Y}_F{k}.npy').astype(np.float32); a[a == -9999] = np.nan
        b, g, r, n, s1, s2 = a
        idx = [(n - r) / (n + r), (n - s2) / (n + s2), (n - s1) / (n + s1)]
        for band in list(a) + idx:
            p = np.full((R * 8 + 8, C * 8 + 8), np.nan, np.float32); p[8:8 + H, 8:8 + W] = band    # shift by one block so node m spans blocks m-1, m
            blk = np.nanmean(p.reshape(R + 1, 8, C + 1, 8), axis=(1, 3))
            win = np.nanmean(np.stack([blk[:-1, :-1], blk[1:, :-1], blk[:-1, 1:], blk[1:, 1:]]), 0)
            out.append(win)
    return np.stack(out, -1)
names_raw = [f'F{k}_{b}' for k in (1, 2, 3, 4) for b in ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'ndvi', 'nbr', 'ndmi']]
def load(Y):
    z = np.load(f'{SP}/emb/{Y}.npz'); L = z['last'].astype(np.float32)
    return L.mean(0), L[3] - L[1], z['mid'].astype(np.float32), z['clear']
if __name__ == '__main__':
    import warnings; warnings.filterwarnings('ignore')
    for Y in SEAS:
        f = f'{SP}/feats/{Y}_raw.npy'
        if not os.path.exists(f): np.save(f, raw(Y).astype(np.float32))
    rng = np.random.default_rng(0); samp = {'mean': [], 'diff': [], 'mid': []}
    for Y in range(2017, 2025):
        m, d, mi, cl = load(Y); ok = np.argwhere(cl > 0.5); ok = ok[rng.choice(len(ok), min(8000, len(ok)), replace=False)]
        for k, v in (('mean', m), ('diff', d), ('mid', mi)): samp[k].append(v[ok[:, 0], ok[:, 1]])
    P = {k: PCA(n, random_state=0).fit(np.concatenate(v)) for (k, v), n in zip(samp.items(), (32, 16, 16))}
    print({k: round(float(p.explained_variance_ratio_.sum()), 3) for k, p in P.items()})
    for Y in SEAS:
        m, d, mi, cl = load(Y)
        F = np.concatenate([P['mean'].transform(m.reshape(-1, 1024)), P['diff'].transform(d.reshape(-1, 1024)), P['mid'].transform(mi.reshape(-1, 1024))], 1)
        F = F.reshape(R, C, -1).astype(np.float32); F[cl < 0.05] = np.nan
        np.save(f'{SP}/feats/{Y}_prithvi.npy', F); print(Y, F.shape, flush=True)
    json.dump({'raw': names_raw, 'prithvi': [f'pm{i}' for i in range(32)] + [f'pd{i}' for i in range(16)] + [f'pl{i}' for i in range(16)]}, open(f'{SP}/feats/names.json', 'w'))
