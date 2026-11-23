import json, numpy as np
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
X0, Y1, STEP = 739500.0, 2558520.0, 240.0
NAMES = json.load(open(f'{SP}/feats/names.json')) if __import__('os').path.exists(f'{SP}/feats/names.json') else None
_cache = {}
def grid(Y, kind):
    k = (Y, kind)
    if k not in _cache: _cache[k] = np.load(f'{SP}/feats/{Y}_{kind}.npy')
    return _cache[k]
def sample(Y, kind, x, y):
    """Bilinear sample of the season-Y feature grid at UTM points (NaN-aware)."""
    F = grid(Y, kind); R, C, K = F.shape
    fx = (np.asarray(x) - X0) / STEP; fy = (Y1 - np.asarray(y)) / STEP
    c0 = np.clip(np.floor(fx).astype(int), 0, C - 2); r0 = np.clip(np.floor(fy).astype(int), 0, R - 2)
    wx = np.clip(fx - c0, 0, 1)[:, None]; wy = np.clip(fy - r0, 0, 1)[:, None]
    v = [F[r0, c0], F[r0, c0 + 1], F[r0 + 1, c0], F[r0 + 1, c0 + 1]]
    w = [(1 - wx) * (1 - wy), wx * (1 - wy), (1 - wx) * wy, wx * wy]
    num = sum(np.nan_to_num(a) * b * ~np.isnan(a) for a, b in zip(v, w)); den = sum(b * ~np.isnan(a) for a, b in zip(v, w))
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
