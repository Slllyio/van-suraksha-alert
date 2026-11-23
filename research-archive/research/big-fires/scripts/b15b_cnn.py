"""Small image net on the map patches (b15), season held out. Rotations and flips of the patch (with the target sector
turned the same way) multiply the training data 8x. Compared with "keep going the same way" and the column-based trees.
Variants: patch only; patch + previous direction; patch without the fire's own trail (ground only).
Out: results/ml/cnn_patches.json, figures/6_cnn_patches.png
"""
import json, time
import numpy as np, pandas as pd, torch, torch.nn as nn, torch.nn.functional as Fn
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
torch.manual_seed(0); np.random.seed(0); torch.set_num_threads(4)
R = '/mnt/project-files/research/big-fires/results'; FG = '/mnt/project-files/research/big-fires/figures'
X = np.load('/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/patches.npz')['X'].astype(np.float32)
M = pd.read_csv(f'{R}/ml/patch_steps.csv'); y = M.sector.values; prev = M.prev_sector.values
print('X', X.shape)
def dihedral(x, s, p, k, flip):
    """rotate k*90 deg (np.rot90 = anticlockwise) and optionally mirror east-west; move the sectors the same way"""
    x = np.rot90(x, k, axes=(-2, -1)); s = (s - 2 * k) % 8; p = np.where(p >= 0, (p - 2 * k) % 8, -1)
    if flip: x = x[..., ::-1]; s = (-s) % 8; p = np.where(p >= 0, (-p) % 8, -1)
    return np.ascontiguousarray(x), s, p
class Net(nn.Module):
    def __init__(self, c_in, use_prev):
        super().__init__(); self.use_prev = use_prev
        self.c1 = nn.Conv2d(c_in, 16, 3, padding=1); self.c2 = nn.Conv2d(16, 32, 3, padding=1); self.c3 = nn.Conv2d(32, 32, 3, padding=1)
        self.fc1 = nn.Linear(32 * 6 * 6 + (9 if use_prev else 0) + 2, 64); self.fc2 = nn.Linear(64, 8); self.do = nn.Dropout(0.3)
    def forward(self, x, extra):
        h = Fn.max_pool2d(Fn.relu(self.c1(x)), 2); h = Fn.max_pool2d(Fn.relu(self.c2(h)), 2); h = Fn.max_pool2d(Fn.relu(self.c3(h)), 2)
        h = h.flatten(1); h = torch.cat([h, extra], 1); return self.fc2(self.do(Fn.relu(self.fc1(h))))
def extras(p, gap, night, use_prev):
    e = [np.log1p(gap)[:, None] / 3, night[:, None]]
    if use_prev: oh = np.zeros((len(p), 9), np.float32); oh[np.arange(len(p)), np.where(p >= 0, p, 8)] = 1; e.append(oh)
    return np.concatenate(e, 1).astype(np.float32)
def run(chan, use_prev, epochs=12, label=''):
    pred = np.full((len(M), 8), np.nan); t0 = time.time()
    for s in sorted(M.season.unique()):
        tr = (M.season != s).values; te = ~tr
        xs, ys, ps = [], [], []
        for k in range(4):
            for flip in (0, 1):
                xa, sa, pa = dihedral(X[tr][:, chan], y[tr], prev[tr], k, flip); xs.append(xa); ys.append(sa); ps.append(pa)
        xs = np.concatenate(xs); ys = np.concatenate(ys); ps = np.concatenate(ps)
        gap = np.tile(M.gap_h.values[tr], 8); night = np.tile(M.night.values[tr], 8).astype(np.float32)
        ex = extras(ps, gap, night, use_prev)
        net = Net(len(chan), use_prev); opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-2)
        xt, yt, et = torch.tensor(xs), torch.tensor(ys), torch.tensor(ex); n = len(xt)
        for ep in range(epochs):
            net.train(); perm = torch.randperm(n)
            for i in range(0, n, 128):
                b = perm[i:i + 128]; opt.zero_grad(); loss = Fn.cross_entropy(net(xt[b], et[b]), yt[b]); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad():
            ex_te = extras(prev[te], M.gap_h.values[te], M.night.values[te].astype(np.float32), use_prev)
            pred[te] = Fn.softmax(net(torch.tensor(np.ascontiguousarray(X[te][:, chan])), torch.tensor(ex_te)), 1).numpy()
    print(label, 'done in', round(time.time() - t0), 's')
    return pred
def score(pred, mask=None):
    mask = np.ones(len(M), bool) if mask is None else mask
    top = pred[mask].argmax(1); dd = (top - y[mask]) % 8
    return dict(top1=round(float((dd == 0).mean()), 3), within_1=round(float(np.isin(dd, [0, 1, 7]).mean()), 3), n=int(mask.sum()))
ALLC = list(range(15)); GROUND = list(range(10)) + [13, 14]
runs = {'patch, all 15 layers': (ALLC, False), 'patch + previous direction': (ALLC, True), 'ground layers only (no fire trail)': (GROUND, False),
        'ground layers + previous direction': (GROUND, True)}
preds = {nm: run(ch, up, label=nm) for nm, (ch, up) in runs.items()}
# keep-going-the-same-way on the same steps
has = prev >= 0; keep = dict(top1=round(float((prev[has] == y[has]).mean() * has.mean()), 3), note='steps without a previous step count as wrong; see keep_same_way_when_available')
keep_av = dict(top1=round(float((prev[has] == y[has]).mean()), 3), within_1=round(float(np.isin((prev[has] - y[has]) % 8, [0, 1, 7]).mean()), 3), n=int(has.sum()))
out = dict(n_steps=len(M), n_fires=int(M.fire.nunique()), results={nm: score(p) for nm, p in preds.items()}, keep_same_way_all_steps=keep, keep_same_way_when_available=keep_av)
masks = {'gap >= 3 h': M.gap_h.values >= 3, 'gap < 3 h': M.gap_h.values < 3, 'big fires': M.big.values == 1, 'other fires': M.big.values == 0, 'seasons 2025-26': M.season.values >= 2025, 'steps with a previous step': has}
out['subsets'] = {nm: {rn: score(p, mk)['top1'] for rn, p in preds.items()} | {'keep going the same way': round(float((prev[mk & has] == y[mk & has]).mean()), 3), 'n': int(mk.sum())} for nm, mk in masks.items()}
# calibration of the best
best = max(out['results'], key=lambda k: out['results'][k]['top1']); p = preds[best]; top = p.max(1); right = p.argmax(1) == y
bins = pd.cut(top, [0, .15, .2, .25, .3, .4, 1]); cal = pd.DataFrame(dict(bin=bins, p=top, r=right)).groupby('bin', observed=True).agg(n=('r', 'size'), predicted=('p', 'mean'), right=('r', 'mean')).round(3)
out['calibration_best'] = dict(model=best, rows=cal.reset_index().astype(str).to_dict('records'))
# which layers matter: zero one layer group at test time for the best patch-only net is not possible without retrain; instead compare runs above
json.dump(out, open(f'{R}/ml/cnn_patches.json', 'w'), indent=1); print(json.dumps(out, indent=1))
np.save('/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/bigfires_cache/cnn_pred_best.npy', preds[best])
fig, ax = plt.subplots(figsize=(9, 4.5))
names = ['keep going the same way'] + list(preds); vals = [keep_av['top1'] * 100] + [out['results'][k]['top1'] * 100 for k in preds]
ax.barh(names, vals, color=['0.5'] + ['C4'] * len(preds)); ax.axvline(12.5, color='k', ls=':', label='random'); ax.axvline(28.6, color='C1', ls='--', label='trees on columns (b14)')
ax.set_xlabel('right sector out of 8, % (held-out seasons)'); ax.set_title(f'Image net on 3 km map patches, {len(M)} steps'); ax.legend(fontsize=8); ax.tick_params(labelsize=8)
plt.tight_layout(); plt.savefig(f'{FG}/6_cnn_patches.png', dpi=110)
