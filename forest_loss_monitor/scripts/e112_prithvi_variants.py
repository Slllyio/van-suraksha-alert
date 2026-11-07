"""Pre-declared Prithvi variants for the diagnosis (see outputs/final/survey_model/prithvi_diagnosis.md section 3). Same held-out test pixels as A, B, C.
a  frozen 24 blocks + linear per-pixel head, weighted CE, Adam 1e-3, 3 epochs on the 546 cached patches.
b  blocks 1-22 frozen, 23-24 + segmentation head trained from a bank of 6,000 random dihedral-augmented 224 px crops (3,000 per epoch), weighted CE,
   lr 1e-5 / 1e-4 cosine over 15 epochs, early stopping (patience 3) on an inner validation range (next range alphabetically).
c  as b on cleaned labels.
e  token probe: logistic regression (balanced) on 64 PCA dims of the frozen block-24 tokens (3 frames concatenated), trained on tokens with >= 50% labelled
   pixels and > 90% one class; each token's prediction fills its 16 x 16 pixels (480 m). PCA fitted on the training-fold tokens.
Final models: a 3 epochs; b, c the median early-stopping epoch from CV. States for 2015 and 2017-2025 (HLS z-matched to 2015).
Usage: e112_prithvi_variants.py bank | cv a|b|c|e | final a|b|c|e"""
import json
import sys
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import confusion_matrix

from common import *
from e106_survey_data import NAMES, SM, hls
from e107_survey_states import OD, PER_CID_TEST, SEED, YEARS, sample, zmatch
from e108_prithvi_net import D, G, IMG, TF, Encoder, Head, masked_ce, up_bilinear
from e109_prithvi_survey import BATCH, CACHE, S, dev, origins, padded, patch, place, tok

BANK = SM / "prithvi_bank22"
NBANK, PER_EPOCH, MAX_EP, PATIENCE = 6000, 3000, 15, 3
KB = 22


class LinHead(nn.Module):
    """Linear map of the 3-frame token features to classes (1x1 conv), then bilinear upsampling (linear maps commute with it)."""
    def __init__(self):
        super().__init__()
        self.lin = nn.Conv2d(TF * D, 3, 1)

    def forward(self, t):
        B = t.shape[0]
        x = t[:, 1:].reshape(B, TF, G, G, D).permute(0, 1, 4, 2, 3).reshape(B, TF * D, G, G)
        return up_bilinear(self.lin(x), (IMG, IMG))


def dihedral(x, k):
    """x (..., H, W): rotate k % 4 quarter turns, flip if k >= 4."""
    x = torch.rot90(x, k % 4, dims=(-2, -1))
    return torch.flip(x, dims=(-1,)) if k >= 4 else x


def data(variant):
    L = np.load(SM / "labels30.npz")
    lab = np.load(SM / "clean_lab.npy") if variant == "c" else L["lab"]
    return lab, L["lab"], L["cid"], L["rng"], L["zone"]


def plab(lab, keep):
    return np.pad(np.where(keep, lab, 0), ((S, IMG), (S, IMG))).astype("int64") - 1


def weights(y):
    cnt = torch.bincount(y[y >= 0], minlength=3).float()
    return (cnt.sum() / (3 * cnt.clamp(min=1))).to(dev)


def toks_at(enc, a, b):
    """Run cached block-20 tokens of every stride-112 patch through frozen blocks a..b; returns a list of fp16 CPU tensors (1, 589, D)."""
    org = [tuple(v) for v in pd.read_csv(CACHE / "origins.csv").values]
    out = []
    with torch.no_grad():
        for i in range(0, len(org), BATCH):
            t = torch.cat([tok(j) for j in range(i, min(i + BATCH, len(org)))]).float().to(dev)
            t = enc.run(t, a, b)
            if b == 24:
                t = enc.norm(t)            # final LayerNorm for the frozen probe (missing in the first run of variant a)
            out += [x.unsqueeze(0).half().cpu() for x in t]
    return org, out


def bank():
    BANK.mkdir(parents=True, exist_ok=True)
    lab, _, _, _, zone = data("b")
    H, W = lab.shape
    x = padded(hls(2015))
    rs = np.random.default_rng(SEED)
    rows = []
    while len(rows) < NBANK:
        r, c = int(rs.integers(-S // 2, H - IMG // 2)), int(rs.integers(-S // 2, W - IMG // 2))
        w = lab[max(r, 0):r + IMG, max(c, 0):c + IMG]
        if w.size and (w > 0).mean() >= .10:
            rows.append((r, c, int(rs.integers(0, 8))))
    pd.DataFrame(rows, columns=["r", "c", "k"]).to_csv(BANK / "bank.csv", index=False)
    enc = Encoder().eval().to(dev)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, NBANK, BATCH):
            f = BANK / f"{i:05d}.pt"
            if f.exists():
                continue
            xb = torch.stack([dihedral(patch(x, r, c), k) for r, c, k in rows[i:i + BATCH]]).to(dev)
            torch.save(enc.run(enc.embed(xb), 0, KB).half().cpu(), f)
            if i % 400 == 0:
                print("bank", i, int(time.time() - t0), "s", flush=True)
    print("bank done")


_bk = {}


def btok(i):
    f, k = i // BATCH * BATCH, i % BATCH
    if f not in _bk:
        if len(_bk) > 256:
            _bk.clear()
        _bk[f] = torch.load(BANK / f"{f:05d}.pt", weights_only=True)
    return _bk[f][k:k + 1]


def eval_pixels(enc, head, org, t22, shape, rr, cc):
    st = np.zeros(shape, "uint8")
    with torch.no_grad():
        for i in range(0, len(org), BATCH):
            t = torch.cat(t22[i:i + BATCH]).float().to(dev)
            p = head(enc.norm(enc.run(t, KB, 24))).argmax(1).cpu().numpy().astype("uint8") + 1
            for k, (r, c) in enumerate(org[i:i + BATCH]):
                place(st, p[k], r, c)
    return st, st[rr, cc]


def train_ft(lab, rng, train_mask, val, epochs, org, t22, log):
    """Variant b/c trainer. val = (rows, cols, labels) for early stopping, or None with a fixed epoch count."""
    bk = pd.read_csv(BANK / "bank.csv").values
    P = plab(lab, train_mask)
    ys = []
    for r, c, k in bk:
        ys.append(dihedral(torch.as_tensor(P[r + S:r + S + IMG, c + S:c + S + IMG]), int(k)))
    use = [i for i, y in enumerate(ys) if (y >= 0).any()]
    w = weights(torch.cat([ys[i].flatten() for i in use]))
    enc = Encoder().to(dev)
    for p in enc.parameters():
        p.requires_grad = False
    tr_params = list(enc.blocks[KB:].parameters()) + list(enc.norm.parameters())
    for p in tr_params:
        p.requires_grad = True
    head = Head().to(dev)
    opt = torch.optim.AdamW([{"params": tr_params, "lr": 1e-5}, {"params": head.parameters(), "lr": 1e-4}], weight_decay=.01)
    steps = MAX_EP * (PER_EPOCH // BATCH)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    rs = np.random.default_rng(SEED)
    best, best_ep, bad, best_state = -1, 0, 0, None
    for ep in range(epochs):
        enc.train(), head.train()
        pick = rs.choice(use, size=min(PER_EPOCH, len(use)), replace=len(use) < PER_EPOCH)
        tot = 0.
        for j in range(0, len(pick), BATCH):
            b = pick[j:j + BATCH]
            t = torch.cat([btok(int(i)) for i in b]).float().to(dev)
            y = torch.stack([ys[int(i)] for i in b]).to(dev)
            loss = masked_ce(head(enc.norm(enc.run(t, KB, 24))), y, w)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sch.step()
            tot += float(loss)
        enc.eval(), head.eval()
        msg = f"  epoch {ep} loss {tot / (len(pick) / BATCH):.4f}"
        if val is not None:
            _, p = eval_pixels(enc, head, org, t22, lab.shape, val[0], val[1])
            acc = float((p == val[2]).mean())
            msg += f" val {acc:.3f}"
            if acc > best:
                best, best_ep, bad = acc, ep + 1, 0
                best_state = ({k: v.detach().clone() for k, v in enc.state_dict().items() if k.startswith(("blocks.22", "blocks.23", "norm"))}, {k: v.detach().clone() for k, v in head.state_dict().items()})
            else:
                bad += 1
        log(msg)
        if val is not None and bad >= PATIENCE:
            break
    if best_state is not None:
        enc.load_state_dict(best_state[0], strict=False)
        head.load_state_dict(best_state[1])
    return enc.eval(), head.eval(), best_ep or epochs


def train_lin(lab, train_mask, org, t24, epochs=3):
    head = LinHead().to(dev)
    P = plab(lab, train_mask)
    ys = [torch.as_tensor(P[r + S:r + S + IMG, c + S:c + S + IMG]) for r, c in org]
    use = [i for i, y in enumerate(ys) if (y >= 0).any()]
    w = weights(torch.cat([ys[i].flatten() for i in use]))
    opt = torch.optim.Adam(head.parameters(), 1e-3)
    rs = np.random.default_rng(SEED)
    for ep in range(epochs):
        rs.shuffle(use)
        for j in range(0, len(use), 8):
            b = use[j:j + 8]
            t = torch.cat([t24[i] for i in b]).float().to(dev)
            loss = masked_ce(head(t), torch.stack([ys[i] for i in b]).to(dev), w)
            opt.zero_grad()
            loss.backward()
            opt.step()
    return head.eval()


def pred_lin(head, org, t24, shape):
    st = np.zeros(shape, "uint8")
    with torch.no_grad():
        for i in range(0, len(org), 8):
            p = head(torch.cat(t24[i:i + 8]).float().to(dev)).argmax(1).cpu().numpy().astype("uint8") + 1
            for k, (r, c) in enumerate(org[i:i + 8]):
                place(st, p[k], r, c)
    return st


def tokfeat(t):
    return t[0, 1:].float().numpy().reshape(TF, G, G, D).transpose(1, 2, 0, 3).reshape(G * G, TF * D)


def train_tok(lab, train_mask, org, t24):
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    Lp = np.pad(np.where(train_mask, lab, 0), ((S, IMG), (S, IMG)))
    X, Y = [], []
    for (r, c), t in zip(org, t24):
        l = Lp[r + S:r + S + IMG, c + S:c + S + IMG].reshape(G, 16, G, 16).transpose(0, 2, 1, 3).reshape(G * G, 256)
        f = tokfeat(t)
        for i in range(G * G):
            v = l[i][l[i] > 0]
            if len(v) >= 128:
                k = np.bincount(v, minlength=4)
                if k.max() / len(v) > .9:
                    X.append(f[i])
                    Y.append(k.argmax())
    X = np.array(X, "float32")
    pca = PCA(64, random_state=SEED).fit(X)
    m = LogisticRegression(max_iter=2000, class_weight="balanced").fit(pca.transform(X), Y)
    return pca, m


def tok_classes(model, t):
    pca, m = model
    return np.kron(m.predict(pca.transform(tokfeat(t))).reshape(G, G).astype("uint8"), np.ones((16, 16), "uint8"))


def pred_tok(model, org, t24, shape):
    st = np.zeros(shape, "uint8")
    for (r, c), t in zip(org, t24):
        place(st, tok_classes(model, t), r, c)
    return st


def metrics(nm, y, p):
    cm = confusion_matrix(y, p, labels=[1, 2, 3])
    return dict(held_out=nm, n=len(y), overall=round(float((p == y).mean()), 3),
                **{f"recall_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[k - 1].sum(), 1), 3) for k in (1, 2, 3)},
                **{f"precision_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[:, k - 1].sum(), 1), 3) for k in (1, 2, 3)}, confusion_rows_true_cols_pred=cm.tolist())


def cv(v):
    lab, lab0, cid, rng, zone = data(v)
    clean = np.load(SM / "clean_lab.npy")
    ranges = pd.read_csv(SM / "ranges.csv", index_col=0).iloc[:, 0].to_dict()
    gl = sorted(ranges)
    te_r, te_c = sample(lab0, cid, rng, PER_CID_TEST, SEED + 1)
    yte, gte = lab0[te_r, te_c], rng[te_r, te_c]
    enc0 = Encoder().eval().to(dev)
    org, tt = toks_at(enc0, 20, 24 if v in ("a", "e") else KB)
    del enc0
    logf = open(OD / f"cv_{v}_train.log", "w")
    def log(s):
        print(s, flush=True)
        logf.write(s + "\n")
        logf.flush()
    pred = np.zeros(len(yte), "uint8")
    rows, eps = [], []
    for g in gl:
        t0 = time.time()
        m = gte == g
        if v == "a":
            head = train_lin(lab, (rng != g) & (rng > 0), org, tt)
            st = pred_lin(head, org, tt, lab.shape)
        elif v == "e":
            st = pred_tok(train_tok(lab, (rng != g) & (rng > 0), org, tt), org, tt, lab.shape)
        else:
            vg = gl[(gl.index(g) + 1) % len(gl)]
            vr, vc = sample(np.where(rng == vg, lab, 0), cid, rng, 100, SEED + 2)
            enc, head, ep = train_ft(lab, rng, (rng != g) & (rng != vg) & (rng > 0), (vr, vc, lab[vr, vc]), MAX_EP, org, tt, log)
            eps.append(ep)
            st, _ = eval_pixels(enc, head, org, tt, lab.shape, te_r[:1], te_c[:1])
        pred[m] = st[te_r[m], te_c[m]]
        rows.append(metrics(ranges[g], yte[m], pred[m]))
        log(f"{ranges[g]} {rows[-1]['overall']} {int(time.time() - t0)} s")
    rows.append(metrics("ALL (pooled held-out)", yte, pred))
    cl = clean[te_r, te_c] > 0
    rows.append(metrics("ALL, cleaned test pixels only", yte[cl], pred[cl]))
    r = pd.DataFrame(rows)
    r.to_csv(OD / f"cv_{v}.csv", index=False)
    json.dump(dict(stop_epochs=eps), open(OD / f"cv_{v}_epochs.json", "w"))
    pd.set_option("display.width", 250)
    print(r.drop(columns="confusion_rows_true_cols_pred").to_string())


def final(v):
    lab, lab0, cid, rng, zone = data(v)
    enc0 = Encoder().eval().to(dev)
    org, tt = toks_at(enc0, 20, 24 if v in ("a", "e") else KB)
    tm = None
    if v == "e":
        tm = train_tok(lab, rng > 0, org, tt)
        enc = enc0
        out = {"s2015": pred_tok(tm, org, tt, lab.shape)}
        run = None
    elif v == "a":
        head = train_lin(lab, rng > 0, org, tt)
        enc = enc0
        out = {"s2015": pred_lin(head, org, tt, lab.shape)}
        run = lambda xb: head(enc.norm(enc.run(enc.embed(xb), 0, 24)))
    else:
        eps = json.load(open(OD / f"cv_{v}_epochs.json"))["stop_epochs"]
        n = int(np.median(eps)) if eps else 6
        enc, head, _ = train_ft(lab, rng, rng > 0, None, n, org, tt, print)
        out = {"s2015": eval_pixels(enc, head, org, tt, lab.shape, np.array([0]), np.array([0]))[0]}
        run = lambda xb: head(enc.norm(enc.run(enc0.run(enc0.embed(xb), 0, KB), KB, 24)))
    ref = hls(2015)
    with torch.no_grad():
        for y in YEARS:
            x = padded(zmatch(hls(y), ref, zone > 0))
            s = np.zeros(lab.shape, "uint8")
            for i in range(0, len(org), BATCH):
                b = org[i:i + BATCH]
                xb = torch.stack([patch(x, r, c) for r, c in b]).to(dev)
                if v == "e":
                    tk = enc.norm(enc.run(enc.embed(xb), 0, 24)).half().cpu()
                    for k, (r, c) in enumerate(b):
                        place(s, tok_classes(tm, tk[k:k + 1]), r, c)
                    continue
                p = run(xb).argmax(1).cpu().numpy().astype("uint8") + 1
                for k, (r, c) in enumerate(b):
                    place(s, p[k], r, c)
            s[zone == 0] = 0
            out[f"s{y}"] = s
            print(v, y, {NAMES[k]: int((s == k).sum()) for k in (1, 2, 3)}, flush=True)
    out["s2015"][zone == 0] = 0
    np.savez_compressed(SM / f"states_A{v}.npz", **out)


if __name__ == "__main__":
    {"bank": lambda: bank(), "cv": lambda: cv(sys.argv[2]), "final": lambda: final(sys.argv[2])}[sys.argv[1]]()
