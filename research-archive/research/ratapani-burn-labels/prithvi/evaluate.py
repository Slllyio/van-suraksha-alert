"""Score the fine-tuned model on the 400 judged validation points, the same way validate.py scores the detector.
Usage: python evaluate.py <obsroot> <weights.pt> <validation_dir> <out_csv> [size=100_tl]
"""
import os, sys, csv, json, datetime as dt
import numpy as np, torch
from common import build_model, device, normalise, season_files, load_image, CHIP, fetch


def score(rows, pred, strata):
    """Stratified precision/recall: detector strata (flagged / not flagged) weighted by their pixel counts."""
    nb, nu = strata["burned_px"], strata["unburned_px"]
    sb = [r for r in rows if r["detected_burned"] == "1"]; su = [r for r in rows if r["detected_burned"] == "0"]
    def frac(s, f): return sum(f(r) for r in s) / max(len(s), 1)
    A = lambda f: nb * frac(sb, f) + nu * frac(su, f)
    mj = A(lambda r: pred(r) and r["j"] == 1); mm = A(lambda r: pred(r)); jj = A(lambda r: r["j"] == 1)
    return mj / max(mm, 1), mj / max(jj, 1)


def main(obsroot, weights, vdir, out_csv, size="100_tl"):
    key = {r["point_id"]: r for r in csv.DictReader(open(os.path.join(vdir, "key.csv")))}
    rows = []
    for r in csv.DictReader(open(os.path.join(vdir, "judged.csv"))):
        if r["judged_burned"] in ("0", "1"):
            k = dict(key[r["point_id"]]); k["j"] = int(r["judged_burned"]); rows.append(k)
    strata = json.load(open(os.path.join(vdir, "strata.json")))
    dev = device()
    m = build_model(False, size)
    m.load_state_dict(torch.load(weights, map_location="cpu")); m = m.to(dev).eval()
    H, W = fetch.INSIDE.shape
    for y in sorted({int(r["year"]) for r in rows}):
        files = season_files(os.path.join(obsroot, str(y)))
        cache = {}
        def img(d):
            d = dt.date.fromisoformat(d)
            if d not in cache:
                cache[d] = load_image(files[d])[0]
            return cache[d]
        for r in [r for r in rows if int(r["year"]) == y]:
            rr, cc = int(r["row"]), int(r["col"])
            r0, c0 = min(max(rr - CHIP // 2, 0), H - CHIP), min(max(cc - CHIP // 2, 0), W - CHIP)
            x = np.stack([img(r["pre"])[:, r0:r0 + CHIP, c0:c0 + CHIP], img(r["post"])[:, r0:r0 + CHIP, c0:c0 + CHIP]], 1)
            xs = [x, x[..., ::-1], x[..., ::-1, :]]  # flip test-time augmentation
            with torch.no_grad():
                out = torch.softmax(m(torch.from_numpy(np.ascontiguousarray(normalise(np.stack(xs)))).to(dev)).output, 1).cpu().numpy()
            pr = [out[0, 1, rr - r0, cc - c0], out[1, 1, rr - r0, CHIP - 1 - (cc - c0)], out[2, 1, CHIP - 1 - (rr - r0), cc - c0]]
            r["p_burn"] = float(np.mean(pr))
        cache.clear()
        print("season", y, "done", flush=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    p, rc = score(rows, lambda r: r["detected_burned"] == "1", strata)
    print(f"detector            precision {p:.2f}  area recall {rc:.2f}")
    for t in (0.3, 0.4, 0.5, 0.6, 0.7):
        p, rc = score(rows, lambda r, t=t: r["p_burn"] >= t, strata)
        print(f"prithvi p>={t:.1f}      precision {p:.2f}  area recall {rc:.2f}")


if __name__ == "__main__":
    main(*sys.argv[1:6])
