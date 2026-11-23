"""Fine-tune Prithvi-EO-2.0 (2-frame before/after, 6 HLS bands) on the weak burn-scar chips.
Usage: python train.py <chipdir> <outdir> [epochs=4] [batch=4] [size=100_tl]
Holds out 10% of chips to watch burn F1 against the detector labels; keeps the best epoch as best.pt.
"""
import os, sys, glob, time, json
import numpy as np, torch
from common import build_model, device, normalise

PW = 5.0  # positive class weight; new burns are ~1-2% of labelled pixels


def main(chipdir, outdir, epochs=4, batch=4, size="100_tl", lr=5e-5):
    os.makedirs(outdir, exist_ok=True)
    X = [np.load(f, mmap_mode="r") for f in sorted(glob.glob(os.path.join(chipdir, "x_*.npy")))]
    Y = [np.load(f, mmap_mode="r") for f in sorted(glob.glob(os.path.join(chipdir, "y_*.npy")))]
    idx = [(s, i) for s, y in enumerate(Y) for i in range(len(y))]
    rng = np.random.default_rng(0)
    rng.shuffle(idx)
    nval = len(idx) // 10
    val, tr = idx[:nval], idx[nval:]
    dev = device()
    m = build_model(True, size).to(dev)
    opt = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=0.05, foreach=False)
    steps = epochs * (len(tr) // batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.1)
    w = torch.tensor([1.0, PW], device=dev)

    def get(items, aug):
        xs, ys = [], []
        for s, i in items:
            x, y = normalise(np.asarray(X[s][i])), np.asarray(Y[s][i]).astype(np.int64)
            if aug:
                k = rng.integers(4)
                x, y = np.rot90(x, k, (2, 3)), np.rot90(y, k, (0, 1))
                if rng.random() < 0.5:
                    x, y = x[..., ::-1], y[:, ::-1]
            xs.append(np.ascontiguousarray(x)); ys.append(np.ascontiguousarray(y))
        return torch.from_numpy(np.stack(xs)).to(dev), torch.from_numpy(np.stack(ys)).to(dev)

    def loss_fn(out, y):
        # manual masked weighted CE (ignore -1), safe on DirectML
        lp = torch.log_softmax(out, 1)
        mask = (y >= 0).float()
        yc = y.clamp(min=0)
        nll = -lp.gather(1, yc[:, None])[:, 0]
        wt = w[yc] * mask
        return (nll * wt).sum() / wt.sum().clamp(min=1)

    best, log = -1, []
    for ep in range(epochs):
        m.train(); rng.shuffle(tr); t0 = time.time(); tl = []
        for k in range(0, len(tr) - batch + 1, batch):
            x, y = get(tr[k:k + batch], True)
            loss = loss_fn(m(x).output, y)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tl.append(loss.item())
            if (k // batch) % 50 == 0:
                print(f"ep {ep} step {k // batch}/{len(tr) // batch} loss {np.mean(tl[-50:]):.4f} "
                      f"{(time.time() - t0) / (k // batch + 1):.2f}s/step", flush=True)
        m.eval(); tp = fp = fn = 0
        with torch.no_grad():
            for k in range(0, len(val), batch):
                x, y = get(val[k:k + batch], False)
                p = m(x).output.argmax(1)
                tp += int(((p == 1) & (y == 1)).sum()); fp += int(((p == 1) & (y == 0)).sum())
                fn += int(((p == 0) & (y == 1)).sum())
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        rec = dict(epoch=ep, train_loss=float(np.mean(tl)), val_precision=tp / max(tp + fp, 1),
                   val_recall=tp / max(tp + fn, 1), val_f1=f1, minutes=(time.time() - t0) / 60)
        print(rec, flush=True); log.append(rec)
        torch.save(m.state_dict(), os.path.join(outdir, "last.pt"))
        if f1 > best:
            best = f1; torch.save(m.state_dict(), os.path.join(outdir, "best.pt"))
        json.dump(log, open(os.path.join(outdir, "train_log.json"), "w"), indent=1)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], *([int(v) for v in a[3:5]] + a[5:6]))
