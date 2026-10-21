# Score the output of big_fire_season_check.py: ranking (AUC), calibration, and big fires caught in the top 10 a day
# (by chance vs by dot count), on VIIRS truth.   python scripts/big_fire_season_score.py season_2025.csv [season_2026.csv ...]
import csv, re, sys
from collections import defaultdict
from datetime import datetime, timedelta


def auc(score, y):
    pos = [s for s, t in zip(score, y) if t]; neg = [s for s, t in zip(score, y) if not t]
    allv = sorted(set(score)); rank, r = {}, 1
    srt = sorted(score)
    i = 0
    while i < len(srt):
        j = i
        while j < len(srt) and srt[j] == srt[i]:
            j += 1
        rank[srt[i]] = (i + 1 + j) / 2; i = j
    return (sum(rank[s] for s in pos) - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


for f in sys.argv[1:]:
    R = list(csv.DictReader(open(f)))
    for r in R:
        m = re.search(r"(\d+) dots at the first look", r["items"])
        r["dots"] = int(m.group(1)) if m else 1
        r["chance"] = float(r["chance"]); r["big"] = int(r["big"])
        r["day"] = (datetime.strptime(r["first_look_utc"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=5, minutes=30)).date()
    y = [r["big"] for r in R]
    print(f"\n{f}: {len(R)} new-fire alerts, {sum(y)} became 200 ha+ (VIIRS truth, {sum(y) / len(R):.1%})")
    print(f"  ranking AUC: chance {auc([r['chance'] for r in R], y):.3f} · dot count {auc([r['dots'] for r in R], y):.3f}")
    print(f"  said {sum(r['chance'] for r in R) / len(R):.1%} on average, happened {sum(y) / len(R):.1%}")
    bands = [(0, .05), (.05, .1), (.1, .2), (.2, .4), (.4, 1.01)]
    for a, b in bands:
        g = [r for r in R if a <= r["chance"] < b]
        if g:
            print(f"    said {a:.0%}-{min(b, 1):.0%}: {len(g)} alerts, said {sum(r['chance'] for r in g) / len(g):.1%}, happened {sum(r['big'] for r in g) / len(g):.1%}")
    D = defaultdict(list)
    for r in R:
        D[r["day"]].append(r)
    for N in (10, 20):
        c_ch = sum(sum(r["big"] for r in sorted(g, key=lambda r: -r["chance"])[:N]) for g in D.values())
        c_dt = sum(sum(r["big"] for r in sorted(g, key=lambda r: (-r["dots"], -r["chance"] * 0))[:N]) for g in D.values())
        print(f"  top {N} a day ({len(D)} days): chance catches {c_ch} of {sum(y)} big fires ({c_ch / sum(y):.0%}), dot count {c_dt} ({c_dt / sum(y):.0%})")
    fc = sum(1 for r in R if r["farmland_checked"] == "1")
    print(f"  farmland checked on {fc / len(R):.0%} of alerts")
