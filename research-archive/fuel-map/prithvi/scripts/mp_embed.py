"""Statewide regions: frozen Prithvi-EO-2.0-300M-TL tokens (4 half-token shifts -> 240 m grid, as embed.py for Ratapani), then sampled
straight onto the all-MP 500 m cells in the box (mean of 5 bilinear samples: centre and +-125 m, as cells.py).
Per cell: frame-mean last layer (1024), Feb-minus-Nov last layer (1024), layer-12 mean (1024), clear share; and the raw HLS
pixels Prithvi saw, averaged over the same 480 m token window (36 = 9 x 4 frames, as feats.py).
Out: mp/feat/{region}_{Y}.npz cell, tok (n, 3072) float16, raw (n, 36) float32, clear (n,)"""
import os, sys, json, time, numpy as np, torch, warnings
warnings.filterwarnings('ignore')
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
sys.path.insert(0, SP + '/models/p300tl'); from prithvi_mae import PrithviMAE
from pyproj import Transformer
M = SP + '/models/p300tl/'; cfg = json.load(open(M + 'config.json'))['pretrained_cfg']
MEAN = np.array(cfg['mean'], np.float32)[:, None, None]; STD = np.array(cfg['std'], np.float32)[:, None, None]
for k in ['bands', 'mean', 'std', 'origin_url', 'paper_ids']: cfg.pop(k)
net = PrithviMAE(**cfg); sd = torch.load(M + 'Prithvi_EO_V2_300M_TL.pt', map_location='cpu', weights_only=True)
net.load_state_dict({k: v for k, v in sd.items() if 'pos_embed' not in k}, strict=False); enc = net.encoder.eval(); del net, sd
torch.set_num_threads(int(os.environ.get('NT', 4)))
inv = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform
MID = {1: (-1, 105), 2: (-1, 320), 3: (0, 16), 4: (0, 38)}
S = 30.0; os.makedirs(f'{SP}/mp/feat', exist_ok=True)
REGS = json.load(open(f'{SP}/mp/regions.json'))
def bil(F, X0, Y1, x, y):
    R, C, _ = F.shape; fx = (x - X0) / 240.0; fy = (Y1 - y) / 240.0
    c0 = np.clip(np.floor(fx).astype(int), 0, C - 2); r0 = np.clip(np.floor(fy).astype(int), 0, R - 2)
    wx = np.clip(fx - c0, 0, 1)[:, None]; wy = np.clip(fy - r0, 0, 1)[:, None]
    v = [F[r0, c0], F[r0, c0 + 1], F[r0 + 1, c0], F[r0 + 1, c0 + 1]]; w = [(1 - wx) * (1 - wy), wx * (1 - wy), (1 - wx) * wy, wx * wy]
    num = sum(np.nan_to_num(a) * b * ~np.isnan(a) for a, b in zip(v, w)); den = sum(b * ~np.isnan(a) for a, b in zip(v, w))
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
def cells(g):
    c0 = int((g['X0'] - 399000) / 500); r0 = int((2996000 - g['Y1']) / 500); n = int(g['W'] * S // 500)
    rr, cc = np.meshgrid(np.arange(r0, r0 + n), np.arange(c0, c0 + n), indexing='ij'); rr, cc = rr.ravel(), cc.ravel()
    return rr * 1829 + cc, 399000 + 500 * cc + 250.0, 2996000 - 500 * rr - 250.0
def run(reg, Y):
    g = REGS[reg]; X0, Y1, H, W = g['X0'], g['Y1'], g['H'], g['W']; R, C = H // 8 + 1, W // 8 + 1
    fr = [np.load(f'{SP}/mp/hls/{reg}/{Y}_F{k}.npy').astype(np.float32) for k in (1, 2, 3, 4)]
    real = np.stack([f[0] != -9999 for f in fr]); a = np.stack(fr); a[a == -9999] = np.nan
    # raw: 480 m window means on the 240 m node grid (same as feats.raw)
    rawg = []
    for k in range(4):
        b, gg, r, n, s1, s2 = a[k]
        for band in list(a[k]) + [(n - r) / (n + r), (n - s2) / (n + s2), (n - s1) / (n + s1)]:
            p = np.full((R * 8 + 8, C * 8 + 8), np.nan, np.float32); p[8:8 + H, 8:8 + W] = band
            blk = np.nanmean(p.reshape(R + 1, 8, C + 1, 8), axis=(1, 3))
            rawg.append(np.nanmean(np.stack([blk[:-1, :-1], blk[1:, :-1], blk[:-1, 1:], blk[1:, 1:]]), 0))
    rawg = np.stack(rawg, -1)
    order = {0: [1, 2, 3], 1: [2, 0, 3], 2: [3, 1, 0], 3: [2, 1, 0]}
    for t in range(4):
        for o in order[t]:
            m = np.isnan(a[t]); a[t][m] = a[o][m]
    a = np.nan_to_num((a - MEAN[None]) / STD[None], nan=0.0); x = np.transpose(a, (1, 0, 2, 3))
    tc = torch.tensor([[[Y + MID[k][0], MID[k][1]] for k in (1, 2, 3, 4)]], dtype=torch.float32)
    TOK = np.full((R, C, 3072), np.nan, np.float16); clear = np.zeros((R, C), np.float32)
    for dy in (0, 8):
        for dx in (0, 8):
            ph, pw = int(np.ceil((H + dy) / 224) * 224), int(np.ceil((W + dx) / 224) * 224)
            P = np.zeros((6, 4, ph, pw), np.float32); P[:, :, dy:dy + H, dx:dx + W] = x
            Q = np.zeros((4, ph, pw), np.float32); Q[:, dy:dy + H, dx:dx + W] = real
            chips = [(i, j) for i in range(0, ph, 224) for j in range(0, pw, 224)]
            for b in range(0, len(chips), 2):
                cb = chips[b:b + 2]
                xb = torch.from_numpy(np.stack([P[:, :, i:i + 224, j:j + 224] for i, j in cb]))
                ll = [inv(X0 + (j - dx + 112) * S, Y1 - (i - dy + 112) * S) for i, j in cb]
                lc = torch.tensor([[la, lo] for lo, la in ll], dtype=torch.float32)
                with torch.inference_mode(): o = enc.forward_features(xb, tc.expand(len(cb), -1, -1), lc)
                L = o[-1][:, 1:].reshape(len(cb), 4, 14, 14, 1024).numpy(); Mi = o[11][:, 1:].reshape(len(cb), 4, 14, 14, 1024).mean(1).numpy()
                V = np.concatenate([L.mean(1), L[:, 3] - L[:, 1], Mi], -1).astype(np.float16)
                for n, (i, j) in enumerate(cb):
                    for ti in range(14):
                        for tj in range(14):
                            r0, c0 = i + 16 * ti - dy, j + 16 * tj - dx; m_r, m_c = (r0 + 8) // 8, (c0 + 8) // 8
                            if r0 + 16 <= 0 or c0 + 16 <= 0 or r0 >= H or c0 >= W or m_r >= R or m_c >= C: continue
                            TOK[m_r, m_c] = V[n, ti, tj]; clear[m_r, m_c] = Q[:, i + 16 * ti:i + 16 * ti + 16, j + 16 * tj:j + 16 * tj + 16].mean()
    cid, cx, cy = cells(g); off = [(0, 0), (125, 125), (-125, 125), (125, -125), (-125, -125)]
    T = TOK.astype(np.float32); T[clear < 0.05] = np.nan
    tok = np.nanmean(np.stack([bil(T, X0, Y1, cx + ox, cy + oy) for ox, oy in off]), 0).astype(np.float16)
    raw = np.nanmean(np.stack([bil(rawg, X0, Y1, cx + ox, cy + oy) for ox, oy in off]), 0).astype(np.float32)
    cl = np.nanmean(np.stack([bil(clear[..., None], X0, Y1, cx + ox, cy + oy) for ox, oy in off]), 0)[:, 0]
    np.savez(f'{SP}/mp/feat/{reg}_{Y}.npz', cell=cid, tok=tok, raw=raw, clear=cl)
jobs = [(r, Y) for Y in (2022, 2023, 2024, 2025) for r in REGS]
while jobs:
    for r, Y in list(jobs):
        if os.path.exists(f'{SP}/mp/feat/{r}_{Y}.npz'): jobs.remove((r, Y)); continue
        if all(os.path.exists(f'{SP}/mp/hls/{r}/{Y}_F{k}.npy') for k in (1, 2, 3, 4)):
            t = time.time(); run(r, Y); jobs.remove((r, Y)); print(r, Y, 'done', f'{time.time() - t:.0f}s', flush=True)
    time.sleep(30)
