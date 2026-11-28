"""Model A: Prithvi-EO-2.0-300M fine-tuned on the 2015 survey states (forest / open / farm), Guna, HLS 2015 3-season stacks at 30 m.
Blocks 1-20 frozen and run once (tokens cached); blocks 21-24 + a segmentation head trained (DirectML, RX 9060 XT). Fixed settings chosen before scoring:
4 epochs, batch 4, AdamW lr 1e-4 (blocks) / 1e-3 (head), inverse-frequency class weights, patches 224 px at stride 112, centre 112 px kept at prediction.
cv: leave-one-range-out on the same held-out pixels as models C and B. final: train on all ranges, predict 2015 and 2017-2025 (HLS z-matched to 2015).
Usage: e109_prithvi_survey.py cache | cv | final"""
import os
import sys
import time

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import torch_directml
from sklearn.metrics import confusion_matrix

from common import *
from e106_survey_data import NAMES, SM, hls
from e107_survey_states import OD, PER_CID_TEST, SEED, YEARS, sample, zmatch
from e108_prithvi_net import IMG, Encoder, Head, masked_ce, normalise

K = 20
S = IMG // 2
EPOCHS, BATCH = 4, 4
CACHE = SM / "prithvi_tok2015"
dev = torch.device("cpu") if os.environ.get("PRITHVI_CPU") else torch_directml.device()      # PRITHVI_CPU=1: CPU reference runs (e114)
torch.manual_seed(SEED)


def origins(H, W, zone):
    out = []
    for r in range(-S // 2, H, S):
        for c in range(-S // 2, W, S):
            r0, c0 = max(r, 0), max(c, 0)
            if (zone[r0:r + IMG, c0:c + IMG] > 0).any():
                out.append((r, c))
    return out


def padded(a):
    x = normalise(a)
    return F.pad(x, (S, IMG, S, IMG))         # origin (r, c) -> padded index (r + S, c + S)


def patch(x, r, c):
    return x[:, :, r + S:r + S + IMG, c + S:c + S + IMG]


def cache():
    CACHE.mkdir(parents=True, exist_ok=True)
    L = np.load(SM / "labels30.npz")
    zone = L["zone"]
    org = origins(*zone.shape, zone)
    x = padded(hls(2015))
    enc = Encoder().eval().to(dev)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(org), BATCH):
            b = org[i:i + BATCH]
            f = CACHE / f"{i:05d}.pt"
            if f.exists():
                continue
            xb = torch.stack([patch(x, r, c) for r, c in b]).to(dev)
            torch.save(enc.run(enc.embed(xb), 0, K).half().cpu(), f)
            if i % 100 == 0:
                print("cached", i, "of", len(org), int(time.time() - t0), "s", flush=True)
    pd.DataFrame(org, columns=["r", "c"]).to_csv(CACHE / "origins.csv", index=False)
    print("cache done", len(org))


def labels_for(org, lab, keep):
    """Per patch label tensor (224 x 224), 0 = ignore, classes shifted to 0..2 -> stored as cls-1 with -1 ignore."""
    H, W = lab.shape
    lp = np.pad(np.where(keep, lab, 0), ((S, IMG), (S, IMG)))
    return [torch.as_tensor(lp[r + S:r + S + IMG, c + S:c + S + IMG].astype("int64") - 1) for r, c in org]


def train(org, ys):
    enc = Encoder().to(dev)
    for p in enc.parameters():
        p.requires_grad = False
    for p in list(enc.blocks[K:].parameters()) + list(enc.norm.parameters()):
        p.requires_grad = True
    head = Head().to(dev)
    allY = torch.cat([y.flatten() for y in ys])
    cnt = torch.bincount(allY[allY >= 0], minlength=3).float()
    w = (cnt.sum() / (3 * cnt.clamp(min=1))).to(dev)
    opt = torch.optim.AdamW([{"params": list(enc.blocks[K:].parameters()) + list(enc.norm.parameters()), "lr": 1e-4}, {"params": head.parameters(), "lr": 1e-3}], weight_decay=.01)
    idx = [i for i, y in enumerate(ys) if (y >= 0).any()]
    rs = np.random.default_rng(SEED)
    for ep in range(EPOCHS):
        rs.shuffle(idx)
        tot = 0.
        for j in range(0, len(idx), BATCH):
            b = idx[j:j + BATCH]
            t = torch.cat([tok(i) for i in b]).float().to(dev)
            y = torch.stack([ys[i] for i in b]).to(dev)
            out = head(enc.norm(enc.run(t, K, 24)))
            loss = masked_ce(out, y, w)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss)
        print(" epoch", ep, "loss", round(tot / max(1, len(idx) // BATCH), 4), flush=True)
    return enc.eval(), head.eval()


_tok = {}


def tok(i):
    """Cached tokens of patch i (files hold BATCH patches each)."""
    f, k = i // BATCH * BATCH, i % BATCH
    if f not in _tok:
        if len(_tok) > 64:
            _tok.clear()
        _tok[f] = torch.load(CACHE / f"{f:05d}.pt", weights_only=True)
    return _tok[f][k:k + 1]


def predict_cached(enc, head, org, shape):
    out = np.zeros(shape, "uint8")
    with torch.no_grad():
        for i in range(0, len(org), BATCH):
            t = torch.cat([tok(j) for j in range(i, min(i + BATCH, len(org)))]).float().to(dev)
            p = head(enc.norm(enc.run(t, K, 24))).argmax(1).cpu().numpy().astype("uint8") + 1
            for k, (r, c) in enumerate(org[i:i + BATCH]):
                place(out, p[k], r, c)
    return out


def place(out, p, r, c):
    """Keep the centre S x S of a patch prediction."""
    H, W = out.shape
    r0, c0 = r + S // 2, c + S // 2
    rs, cs = max(0, -r0), max(0, -c0)
    re_, ce = min(S, H - r0), min(S, W - c0)
    if re_ > rs and ce > cs:
        out[r0 + rs:r0 + re_, c0 + cs:c0 + ce] = p[S // 2 + rs:S // 2 + re_, S // 2 + cs:S // 2 + ce]


def cv():
    L = np.load(SM / "labels30.npz")
    lab, cid, rng, zone = L["lab"], L["cid"], L["rng"], L["zone"]
    ranges = pd.read_csv(SM / "ranges.csv", index_col=0).iloc[:, 0].to_dict()
    org = [tuple(v) for v in pd.read_csv(CACHE / "origins.csv").values]
    te_r, te_c = sample(lab, cid, rng, PER_CID_TEST, SEED + 1)
    yte, gte = lab[te_r, te_c], rng[te_r, te_c]
    pred = np.zeros(len(yte), "uint8")
    rows = []
    for g, nm in ranges.items():
        t0 = time.time()
        enc, head = train(org, labels_for(org, lab, (rng != g) & (rng > 0)))
        st = predict_cached(enc, head, org, lab.shape)
        m = gte == g
        p = st[te_r[m], te_c[m]]
        pred[m] = p
        cm = confusion_matrix(yte[m], p, labels=[1, 2, 3])
        rows.append(dict(held_out=nm, n=int(m.sum()), overall=round(float((p == yte[m]).mean()), 3),
                         **{f"recall_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[k - 1].sum(), 1), 3) for k in (1, 2, 3)},
                         **{f"precision_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[:, k - 1].sum(), 1), 3) for k in (1, 2, 3)}, confusion_rows_true_cols_pred=cm.tolist()))
        print(nm, rows[-1]["overall"], int(time.time() - t0), "s", flush=True)
        del enc, head
    cm = confusion_matrix(yte, pred, labels=[1, 2, 3])
    rows.append(dict(held_out="ALL (pooled held-out)", n=len(yte), overall=round(float((pred == yte).mean()), 3),
                     **{f"recall_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[k - 1].sum(), 1), 3) for k in (1, 2, 3)},
                     **{f"precision_{NAMES[k]}": round(cm[k - 1, k - 1] / max(cm[:, k - 1].sum(), 1), 3) for k in (1, 2, 3)}, confusion_rows_true_cols_pred=cm.tolist()))
    r = pd.DataFrame(rows)
    OD.mkdir(parents=True, exist_ok=True)
    r.to_csv(OD / "cv_A.csv", index=False)
    pd.set_option("display.width", 250)
    print(r.drop(columns="confusion_rows_true_cols_pred").to_string())
    print("pooled confusion:\n", cm)


def final():
    L = np.load(SM / "labels30.npz")
    lab, rng, zone = L["lab"], L["rng"], L["zone"]
    org = [tuple(v) for v in pd.read_csv(CACHE / "origins.csv").values]
    enc, head = train(org, labels_for(org, lab, rng > 0))
    torch.save(dict(blocks=enc.blocks[K:].state_dict(), norm=enc.norm.state_dict(), head=head.state_dict()), SM / "prithvi_A.pt")
    out = {"s2015": predict_cached(enc, head, org, lab.shape)}
    ref = hls(2015)
    with torch.no_grad():
        for y in YEARS:
            x = padded(zmatch(hls(y), ref, zone > 0))
            s = np.zeros(lab.shape, "uint8")
            for i in range(0, len(org), BATCH):
                b = org[i:i + BATCH]
                xb = torch.stack([patch(x, r, c) for r, c in b]).to(dev)
                p = head(enc.norm(enc.run(enc.embed(xb), 0, 24))).argmax(1).cpu().numpy().astype("uint8") + 1
                for k, (r, c) in enumerate(b):
                    place(s, p[k], r, c)
            s[zone == 0] = 0
            out[f"s{y}"] = s
            print("A", y, {NAMES[k]: int((s == k).sum()) for k in (1, 2, 3)}, flush=True)
    out["s2015"][zone == 0] = 0
    np.savez_compressed(SM / "states_A.npz", **out)


if __name__ == "__main__":
    {"cache": cache, "cv": cv, "final": final}[sys.argv[1]]()
