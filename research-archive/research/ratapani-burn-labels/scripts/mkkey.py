"""Draw a stratified validation sample (burned / unburned eligible pixels, every season) and write
key.csv + strata.json for rerender.py and validate.py score.
Usage: python mkkey.py <obsroot> <burndir> <outdir> <n_burned> <n_unburned> <seed>
"""
import os, sys, glob, csv, json, datetime as dt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch

I = fetch.INSIDE
rows_, cols_ = np.where(I)


def main(obsroot, burndir, outdir, nb, nu, seed):
    rng = np.random.default_rng(seed)
    lc = np.load(fetch.WORLDCOVER)
    eligible = np.isin(lc, (10, 20, 30))
    years = sorted(int(os.path.basename(f)[5:9]) for f in glob.glob(os.path.join(burndir, "burn_*.npz")))
    strata = dict(burned_px=0, unburned_px=0)
    key = []
    for y in years:
        b = np.load(os.path.join(burndir, f"burn_{y}.npz"))
        burned = np.where(b["end"] > -999)[0]
        unb = np.where((b["end"] == -999) & eligible)[0]
        strata["burned_px"] += len(burned); strata["unburned_px"] += len(unb)
        pts = [(i, 1) for i in rng.choice(burned, nb // len(years), replace=False)] + \
              [(i, 0) for i in rng.choice(unb, nu // len(years), replace=False)]
        files = sorted(glob.glob(os.path.join(obsroot, str(y), "*.npz")))
        idx = np.array([p[0] for p in pts])
        vstack = np.array([np.load(f)["valid"][idx] for f in files])  # files x points
        fdates = [dt.date.fromisoformat(os.path.basename(f)[:10]) for f in files]
        for n, (i, lab) in enumerate(pts):
            seen = sorted({fdates[t] for t in range(len(files)) if vstack[t, n]})
            days = [(d - dt.date(y, 1, 1)).days for d in seen]
            if lab:
                s, e = int(b["start"][i]), int(b["end"][i])
                jb = max(k for k, dd in enumerate(days) if dd <= s); ka = days.index(e)
            else:
                cand = [k for k in range(1, len(days)) if 31 <= days[k] <= 150 and days[k] - days[k - 1] <= 20]
                if not cand:
                    continue
                ka = int(rng.choice(cand)); jb = ka - 1
            later = [k for k in range(ka + 1, len(days)) if 14 <= days[k] - days[ka] <= 40]
            kl = later[0] if later else min(ka + 1, len(days) - 1)
            key.append(dict(year=y, pixel=int(i), row=int(rows_[i]), col=int(cols_[i]), detected_burned=lab,
                            pre=seen[jb].isoformat(), post=seen[ka].isoformat(), late=seen[kl].isoformat(),
                            landcover=int(lc[i])))
    order = rng.permutation(len(key))
    key = [dict(point_id=n, **key[o]) for n, o in enumerate(order)]
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "key.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0])); w.writeheader(); w.writerows(key)
    json.dump({k: int(v) for k, v in strata.items()}, open(os.path.join(outdir, "strata.json"), "w"))
    print("points", len(key), strata)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[3], int(a[4]), int(a[5]), int(a[6]))
