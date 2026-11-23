"""Train a small map head on frozen Prithvi tokens to draw the final scar around the first alert (30 m).
Same network for every variant; only the inputs change. 5 folds, two seasons held out per fold.
Scored inside 1.5 km of the dots' centre: pixel AUC, per-fire overlap at true size (IoU), per-season AUC.
Variants: 'distance + canopy', '+ raw HLS 30 m', '+ raw HLS + Prithvi'.  Usage: python s2_head.py [variant...]"""
import sys, json, time, numpy as np, torch, torch.nn as nn, torch.nn.functional as Fn
from sklearn.metrics import roc_auc_score
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
torch.set_num_threads(4); torch.manual_seed(0); np.random.seed(0)
z = np.load(f'{SP}/chips.npz'); meta = z['meta']; season = meta[:, 1].astype(int); Y = torch.from_numpy(z['y'].astype(np.float32))
MEAN = np.array([1087, 1342, 1433, 2734, 1958, 1363], np.float32); STD = np.array([2248, 2179, 2178, 1850, 1242, 1049], np.float32)
raw = z['raw'].astype(np.float32).reshape(len(meta), 4, 6, 104, 104); raw = np.where(raw == -9999, MEAN[None, None, :, None, None], raw)
RAW = torch.from_numpy(((raw - MEAN[None, None, :, None, None]) / STD[None, None, :, None, None]).reshape(len(meta), 24, 104, 104)); del raw
aux = z['aux'].copy(); aux[:, 0] /= 100; aux[:, 1] = np.minimum(aux[:, 1], 3000) / 1000; AUX = torch.from_numpy(aux)
TOK = torch.from_numpy(z['tok'])   # float16 (n, 2048, 15, 15)
yy, xx = np.mgrid[:104, :104]; DISK = torch.from_numpy(((yy - 51.5) ** 2 + (xx - 51.5) ** 2) <= 50 ** 2)
class Net(nn.Module):
    def __init__(s, use_raw, use_tok, ch=32):
        super().__init__(); s.ur, s.ut = use_raw, use_tok
        cin = 3 + (24 if use_raw else 0) + (ch if use_tok else 0)
        if use_tok: s.tok = nn.Sequential(nn.Conv2d(2048, 128, 1), nn.ReLU(), nn.Conv2d(128, ch, 1))
        s.inp = nn.Conv2d(cin, ch, 3, padding=1)
        s.blocks = nn.ModuleList([nn.Conv2d(ch, ch, 3, padding=d, dilation=d) for d in (1, 2, 4, 8, 16)])
        s.out = nn.Conv2d(ch, 1, 1)
    def forward(s, aux, raw, tok):
        x = [aux] + ([raw] if s.ur else [])
        if s.ut:
            t = s.tok(tok.float()); t = Fn.interpolate(t, size=(113, 113), mode='bilinear', align_corners=True)[:, :, 8:112, 8:112]; x.append(t)
        h = Fn.relu(s.inp(torch.cat(x, 1)))
        for b in s.blocks: h = h + Fn.relu(b(h))
        return s.out(h)[:, 0]
def aug(t, k, f):
    t = torch.rot90(t, k, (-2, -1)); return torch.flip(t, (-1,)) if f else t
VAR = {'distance + canopy': (False, False), '+ raw HLS 30 m': (True, False), '+ raw HLS + Prithvi': (True, True), 'Prithvi (no raw)': (False, True)}
FOLDS = [(2017, 2018), (2019, 2020), (2021, 2022), (2023, 2024), (2025, 2026)]
pos = (Y * DISK).sum() / (DISK.sum() * len(Y)); PW = torch.tensor(float((1 - pos) / pos))
out = json.load(open(f'{SP}/s2_head.json')) if len(sys.argv) > 1 and __import__('os').path.exists(f'{SP}/s2_head.json') else {}
for name in (sys.argv[1:] or VAR):
    ur, ut = VAR[name]; P = torch.zeros_like(Y); t0 = time.time()
    for fs in FOLDS:
        tr = np.where(~np.isin(season, fs))[0]; te = np.where(np.isin(season, fs))[0]
        net = Net(ur, ut); opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
        E = 8; sched = torch.optim.lr_scheduler.OneCycleLR(opt, 2e-3, total_steps=E * int(np.ceil(len(tr) / 16)))
        for ep in range(E):
            net.train(); np.random.shuffle(tr)
            for b in range(0, len(tr), 16):
                i = tr[b:b + 16]; k, f = np.random.randint(4), np.random.rand() < 0.5
                lo = net(aug(AUX[i], k, f), aug(RAW[i], k, f), aug(TOK[i], k, f)); yt = aug(Y[i], k, f); m = aug(DISK.expand(len(i), -1, -1), k, f)
                loss = Fn.binary_cross_entropy_with_logits(lo[m], yt[m], pos_weight=PW); opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        net.eval()
        with torch.no_grad():
            for b in range(0, len(te), 32):
                i = te[b:b + 32]; P[i] = torch.sigmoid(net(AUX[i], RAW[i], TOK[i]))
        print(name, fs, f'{time.time() - t0:.0f}s', flush=True)
    m = DISK.numpy(); yv = Y.numpy()[:, m]; pv = P.numpy()[:, m]
    ious = []
    for j in range(len(Y)):
        n = int(yv[j].sum())
        if n == 0: continue
        top = np.zeros_like(yv[j], bool); top[np.argsort(-pv[j])[:n]] = True; ious.append((top & (yv[j] > 0)).sum() / (top | (yv[j] > 0)).sum())
    out[name] = dict(auc=round(float(roc_auc_score(yv.ravel(), pv.ravel())), 4), iou_true_size=round(float(np.mean(ious)), 4),
                     auc_by_season={int(s): round(float(roc_auc_score(yv[season == s].ravel(), pv[season == s].ravel())), 3) for s in range(2017, 2027)})
    np.save(f'{SP}/s2_pred_{name.replace(" ", "_").replace("+", "p")}.npy', P.numpy().astype(np.float16))
    print(name, {k: v for k, v in out[name].items() if k != 'auc_by_season'}, flush=True)
    json.dump(out, open(f'{SP}/s2_head.json', 'w'), indent=1)
