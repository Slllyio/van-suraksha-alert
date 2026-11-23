"""Prithvi-EO-2.0-300M-TL embeddings over the Ratapani box, one per season, from 4 HLS frames
(Apr Y-1 leaf-off, Nov Y-1 full leaf, Jan Y, 1-14 Feb Y). Frozen encoder, CPU.
Tokens are 16 px (480 m); 4 half-token shifts give a 240 m grid (token centre at row/col 8*m px of the 30 m grid).
Out: emb/{Y}.npz with last (4, R, C, 1024) float16 = last-layer token per frame, mid (R, C, 1024) = layer-12 token mean over frames,
     clear (R, C) share of real (not gap-filled) pixels under the token, ys/xs token centre UTM."""
import os, sys, json, time, numpy as np, torch
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
sys.path.insert(0, SP + '/models/p300tl'); from prithvi_mae import PrithviMAE
from pyproj import Transformer
M = SP + '/models/p300tl/'; cfg = json.load(open(M + 'config.json'))['pretrained_cfg']
MEAN = np.array(cfg['mean'], np.float32)[:, None, None]; STD = np.array(cfg['std'], np.float32)[:, None, None]
for k in ['bands', 'mean', 'std', 'origin_url', 'paper_ids']: cfg.pop(k)
net = PrithviMAE(**cfg); sd = torch.load(M + 'Prithvi_EO_V2_300M_TL.pt', map_location='cpu', weights_only=True)
net.load_state_dict({k: v for k, v in sd.items() if 'pos_embed' not in k}, strict=False); enc = net.encoder.eval(); del net, sd
torch.set_num_threads(int(os.environ.get('NT', 4)))
X0, Y1, S, H, W = 739500.0, 2558520.0, 30.0, 1120, 2500
inv = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform
MID = {1: (-1, 105), 2: (-1, 320), 3: (0, 16), 4: (0, 38)}   # (year offset, doy) of each frame window centre
R, C = H // 8 + 1, W // 8 + 1
def run(Y):
    fr = [np.load(f'{SP}/hls/{Y}_F{k}.npy').astype(np.float32) for k in (1, 2, 3, 4)]
    real = np.stack([f[0] != -9999 for f in fr])                     # 4 x H x W
    a = np.stack(fr); a[a == -9999] = np.nan
    order = {0: [1, 2, 3], 1: [2, 0, 3], 2: [3, 1, 0], 3: [2, 1, 0]}  # nearest-in-season fill
    for t in range(4):
        for o in order[t]:
            m = np.isnan(a[t]); a[t][m] = a[o][m]
    a = (a - MEAN[None]) / STD[None]; a = np.nan_to_num(a, nan=0.0)   # 4 x 6 x H x W
    x = np.transpose(a, (1, 0, 2, 3))                                 # 6 x 4 x H x W
    tc = torch.tensor([[[Y + MID[k][0], MID[k][1]] for k in (1, 2, 3, 4)]], dtype=torch.float32)
    last = np.zeros((4, R, C, 1024), np.float16); mid = np.zeros((R, C, 1024), np.float16); clear = np.zeros((R, C), np.float32)
    for dy in (0, 8):
        for dx in (0, 8):
            ph, pw = int(np.ceil((H + dy) / 224) * 224), int(np.ceil((W + dx) / 224) * 224)
            P = np.zeros((6, 4, ph, pw), np.float32); P[:, :, dy:dy + H, dx:dx + W] = x
            Q = np.zeros((4, ph, pw), np.float32); Q[:, dy:dy + H, dx:dx + W] = real
            chips = [(i, j) for i in range(0, ph, 224) for j in range(0, pw, 224)]
            for b in range(0, len(chips), 4):
                cb = chips[b:b + 4]
                xb = torch.from_numpy(np.stack([P[:, :, i:i + 224, j:j + 224] for i, j in cb]))
                ll = [inv(X0 + (j - dx + 112) * S, Y1 - (i - dy + 112) * S) for i, j in cb]
                lc = torch.tensor([[la, lo] for lo, la in ll], dtype=torch.float32)
                with torch.inference_mode():
                    o = enc.forward_features(xb, tc.expand(len(cb), -1, -1), lc)
                L = o[-1][:, 1:].reshape(len(cb), 4, 14, 14, 1024).numpy(); Mi = o[11][:, 1:].reshape(len(cb), 4, 14, 14, 1024).mean(1).numpy()
                for n, (i, j) in enumerate(cb):
                    for ti in range(14):
                        for tj in range(14):
                            r0, c0 = i + 16 * ti - dy, j + 16 * tj - dx          # token top-left in original px
                            m_r, m_c = (r0 + 8) // 8, (c0 + 8) // 8              # centre index on 8 px grid
                            if r0 + 16 <= 0 or c0 + 16 <= 0 or r0 >= H or c0 >= W or m_r >= R or m_c >= C: continue
                            last[:, m_r, m_c] = L[n, :, ti, tj]; mid[m_r, m_c] = Mi[n, ti, tj]
                            clear[m_r, m_c] = Q[:, i + 16 * ti:i + 16 * ti + 16, j + 16 * tj:j + 16 * tj + 16].mean()
    ys = Y1 - 8 * S * np.arange(R); xs = X0 + 8 * S * np.arange(C)
    np.savez(f'{SP}/emb/{Y}.npz', last=last, mid=mid, clear=clear, ys=ys, xs=xs)
for Y in [int(v) for v in sys.argv[1:]]:
    while not all(os.path.exists(f'{SP}/hls/{Y}_F{k}.npy') for k in (1, 2, 3, 4)): time.sleep(30)
    if os.path.exists(f'{SP}/emb/{Y}.npz'): continue
    t = time.time(); run(Y); print(Y, 'done', f'{time.time() - t:.0f}s', flush=True)
