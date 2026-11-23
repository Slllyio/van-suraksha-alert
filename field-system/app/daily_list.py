"""Officials' daily "check in the next 2 days" list of 500 m squares (mp_grid), from the division model's scores.

The rule is the one the "Is the project at its limit" thread settled on (research/ceiling/DAILY_RULE_SPEC.md) and
the PC pipeline tested with no hindsight (van-suraksha-alert PR #1, mp/README.md "Live combined rule";
results/officer/live_*): held-out 2023-24 71.1% of fires / 45.8% brand-new / 83.2% beats, forward 2026
67.5 / 47.6 / 82.3, against 72.1 / 41.9 / 81.3 and 69.7 / 35.9 / 80.6 for the hindsight top 10% per division.

Each day:
  1. Daily total. Each division's danger-scaled count n_d = k x share x squares (k = config.DAILY_K, or the count the
     pipeline sends) adds up to the day's statewide total T. The workload equals the per-division rule's; only where flags go changes.
  2. Floor. Each division keeps half its count, ceil(n_d / 2): 35% of those on its quiet squares and 65% on the
     others, each by the model's score. Spare slots move between the two when one side runs out.
  3. Pool. The rest of T goes statewide by calibrated %, again 35% to quiet squares and 65% to others, with spare
     slots moving between them.
  A quiet square has no VIIRS point within 10 squares (5 km, as a box) in the 7 days before the list. Ties go to the raw score.
The % must come from calibration fitted on the previous season only (the pipeline's job, refit before 15 Feb).
FS_DAILY_RULE=division falls back to each division filling its own count. Guards' beat alerts are not touched."""
import json, math
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy as np

from . import config

IST = timezone(timedelta(hours=5, minutes=30))
FLOOR, QUIET_SHARE, QUIET_KM, QUIET_DAYS = 0.5, config.QUIET_SHARE, 5.0, 7
SHARE_MIN, SHARE_MAX, BASE_SHARE, FIRST_DAYS = 0.01, 0.40, 0.10, 7
RULE = config.DAILY_RULE   # "pool" (floor + quiet reserve + statewide pool) or "division"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_list (
  issue_date TEXT NOT NULL, cell INTEGER NOT NULL, division TEXT, beat_uid TEXT, pct REAL, score REAL,
  reason TEXT NOT NULL, quiet INTEGER NOT NULL, PRIMARY KEY (issue_date, cell, division));
CREATE INDEX IF NOT EXISTS dl_div ON daily_list(issue_date, division);
CREATE TABLE IF NOT EXISTS daily_list_meta (
  issue_date TEXT PRIMARY KEY, rule TEXT NOT NULL, model_version TEXT, counts TEXT NOT NULL, div_mean TEXT NOT NULL,
  summary TEXT NOT NULL, received_utc TEXT NOT NULL);
"""


@lru_cache(maxsize=1)
def cells():
    """Every mp_grid square in a beat: cell id -> (row, col, beat_uid), as arrays (ratapani/mp_grid/mp_cells.parquet)."""
    import pandas as pd
    d = pd.read_parquet(config.MP_CELLS, columns=["cell", "row", "col", "beat_uid"])
    return d.cell.to_numpy(), d.row.to_numpy(), d.col.to_numpy(), d.beat_uid.to_numpy()


def grid():
    return json.load(open(config.MP_GRID, encoding="utf-8"))


def quiet_mask(con, until_utc):
    """Raster, True for squares with no VIIRS point within 5 km in the 7 days before until_utc."""
    until_utc = until_utc.astimezone(timezone.utc)
    from pyproj import Transformer
    g = grid()
    hot = np.zeros((g["H"], g["W"]), bool)
    lo = (until_utc - timedelta(days=QUIET_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pts = con.execute("SELECT lat, lon FROM detections WHERE instrument='VIIRS' AND acq_utc >= ? AND acq_utc < ?",
                      (lo, until_utc.strftime("%Y-%m-%dT%H:%M:%SZ"))).fetchall()
    if pts:
        tr = Transformer.from_crs(4326, 32643, always_xy=True)
        x, y = tr.transform([p[1] for p in pts], [p[0] for p in pts])
        col, row = (np.asarray(x) - g["X0"]) // g["S"], (g["Y1"] - np.asarray(y)) // g["S"]
        r = int(math.ceil(QUIET_KM * 1000 / g["S"]))
        dr, dc = np.mgrid[-r:r + 1, -r:r + 1]   # +-10 squares, a box as in the PC's tested rule (corners reach ~7 km)
        dr, dc = dr.ravel(), dc.ravel()
        for rr, cc in set(zip(row.astype(int), col.astype(int))):
            R, C = rr + dr, cc + dc
            ok = (R >= 0) & (R < g["H"]) & (C >= 0) & (C < g["W"])
            hot[R[ok], C[ok]] = True
    return ~hot      # indexed [row, col]; a cell id is row * W + col


def counts(con, issue_date, div_cells, div_mean, base=None):
    """Danger-scaled count per division (pipeline's forward rule): cells x clip(base x today's mean score / the
    season's mean daily score up to yesterday, 1-40%); plain base share in the season's first week; all times
    config.DAILY_K, which keeps the ground flagged equal to the yardstick's. base is the division's share after last
    season's overshoot shrink (default 10%)."""
    base = base or {}
    prev = {}
    for m in con.execute("SELECT div_mean FROM daily_list_meta WHERE issue_date < ? AND issue_date >= ? ORDER BY issue_date",
                         (issue_date, season_start(issue_date))):
        for d, v in json.loads(m[0]).items():
            prev.setdefault(d, []).append(v)
    out = {}
    for d, n in div_cells.items():
        b = base.get(d, BASE_SHARE)
        hist = prev.get(d, [])
        share = b if len(hist) < FIRST_DAYS or not np.mean(hist) else b * div_mean.get(d, 0) / np.mean(hist)
        out[d] = int(round(config.DAILY_K * n * min(SHARE_MAX, max(SHARE_MIN, share))))
    return out


def season_start(issue_date):
    return issue_date[:4] + "-02-15"


def _take(idx, order_key, k):
    """The k best of idx by order_key (descending)."""
    if k <= 0 or not len(idx):
        return idx[:0]
    return idx[np.lexsort((-order_key[1][idx], -order_key[0][idx]))[:k]]


def _split(pool_q, pool_o, k, key):
    """k flags, QUIET_SHARE quiet and the rest others, spare slots moving to whichever side still has squares."""
    kq = min(int(round(k * QUIET_SHARE)), len(pool_q))
    ko = min(k - kq, len(pool_o))
    kq = min(k - ko, len(pool_q))
    return _take(pool_q, key, kq), _take(pool_o, key, ko)


def select(div, pct, score, quiet, n, rule=None):
    """Pick the day's squares. div, pct, score, quiet: one entry per square; n: count per division.
    Returns (index array, reason array) with reason 'division', 'quiet square' or 'statewide'."""
    rule = rule or RULE
    picked, why = [], []
    by_div = {}
    for i, d in enumerate(div):
        by_div.setdefault(d, []).append(i)
    by_div = {d: np.asarray(v) for d, v in by_div.items()}
    if rule == "division":
        for d, k in n.items():
            if d in by_div:
                s = _take(by_div[d], (score, score), k)
                picked.append(s); why += ["division"] * len(s)
        return (np.concatenate(picked) if picked else np.array([], int)), np.array(why)
    taken = np.zeros(len(div), bool)
    for d, k in n.items():
        if d not in by_div:
            continue
        ix = by_div[d]
        f = int(math.ceil(k * FLOOR))
        q, o = _split(ix[quiet[ix]], ix[~quiet[ix]], f, (score, score))   # within a division the score orders squares
        for s in (q, o):
            taken[s] = True; picked.append(s); why += ["division"] * len(s)
    rest = sum(n.values()) - int(taken.sum())
    free = np.flatnonzero(~taken)
    q, o = _split(free[quiet[free]], free[~quiet[free]], rest, (pct, score))
    picked += [q, o]; why += ["quiet square"] * len(q) + ["statewide"] * len(o)
    return np.concatenate(picked), np.array(why)


def build(con, beats, body, now_utc):
    """Store the day's list from the pipeline's scores. body: issue_date, model_version, cell [ids], pct [calibrated %
    per square, 0-1, previous season's calibration], score [raw model score]; optional division [per row: the division whose model scored it], counts {division: n} (else the
    danger-scaled rule here), base_share {division: share}, rule ('pool' | 'division'), as_of_utc (replays)."""
    day = body["issue_date"]
    datetime.strptime(day, "%Y-%m-%d")
    cid, pct, score = (np.asarray(body[k], dtype=float) for k in ("cell", "pct", "score"))
    n_rows = len(cid)
    if not n_rows or len(pct) != n_rows or len(score) != n_rows or (body.get("division") and len(body["division"]) != n_rows):
        raise ValueError("cell, pct, score (and division) must be non-empty lists of the same length")
    if not (np.isfinite(cid).all() and np.isfinite(pct).all() and np.isfinite(score).all()):
        raise ValueError("cell, pct and score must be numbers")
    g0 = grid()
    if cid.min() < 0 or cid.max() >= g0["H"] * g0["W"]:
        raise ValueError("cell id outside mp_grid")
    cid = cid.astype(np.int64)
    all_c, _, _, all_beat = cells()
    pos = {c: i for i, c in enumerate(all_c)}
    ix = np.array([pos.get(c, -1) for c in cid])
    # with the pipeline's own division per row, every row counts (a boundary square is scored by each division holding
    # it; ~8% of the PC's flags fall on squares outside the beat map); without it, a square needs a beat to get a division
    ok = np.ones(len(cid), bool) if body.get("division") else ix >= 0
    cid, pct, score, ix = cid[ok], pct[ok], score[ok], ix[ok]
    if not len(cid):   # never replace a day's list with an empty one
        raise ValueError("no row is a square in the beat map; send division per row, or check the cell ids")
    beat = np.where(ix >= 0, all_beat[np.maximum(ix, 0)], None)
    if body.get("division"):
        div = np.asarray(body["division"], dtype=object)[ok]
    else:
        div = np.array([beats.by_uid.get(b, {}).get("division", "") for b in beat])
    issue = datetime.fromisoformat(day).replace(tzinfo=IST) + timedelta(hours=16)   # sent with the 4 pm brief
    until = datetime.fromisoformat(body["as_of_utc"].replace("Z", "+00:00")) if body.get("as_of_utc") else min(now_utc, issue)
    until = until.astimezone(timezone.utc)
    g = grid()
    quiet = quiet_mask(con, until)[cid // g["W"], cid % g["W"]]
    div_cells = {d: int((div == d).sum()) for d in set(div) if d}
    div_mean = {d: float(score[div == d].mean()) for d in div_cells}
    n = body.get("counts") or counts(con, day, div_cells, div_mean, body.get("base_share"))
    rule = body.get("rule") or RULE
    sel, why = select(div, pct, score, quiet, n, rule)
    rows = list({(int(cid[i]), div[i]): (day, int(cid[i]), div[i], beat[i], float(pct[i]), float(score[i]), w, int(quiet[i]))
                 for i, w in zip(sel, why)}.values())      # a repeated (square, division) row is kept once, not a 500
    got = {}
    for i in sel:
        got[div[i]] = got.get(div[i], 0) + 1
    short = sorted(d for d, k in n.items() if k and got.get(d, 0) < math.ceil(k * FLOOR) and div_cells.get(d, 0) >= math.ceil(k * FLOOR))
    summary = {"total": int(sum(n.values())), "flagged": len(rows), "rule": rule,
               "by_reason": {r: int((why == r).sum()) for r in ("division", "quiet square", "statewide")},
               "quiet_flags": int(quiet[sel].sum()) if len(sel) else 0, "divisions_below_half": short,
               "squares_scored": int(len(cid)), "quiet_squares": int(quiet.sum()), "as_of_utc": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "stale": [str(x) for x in ((body.get("inputs") or {}).get("stale") or [])]}   # the runner's own input-age check
    con.execute("DELETE FROM daily_list WHERE issue_date=?", (day,))
    con.executemany("INSERT INTO daily_list VALUES (?,?,?,?,?,?,?,?)", rows)
    con.execute("INSERT OR REPLACE INTO daily_list_meta VALUES (?,?,?,?,?,?,?)",
                (day, rule, json.dumps(body.get("model_version")), json.dumps(n), json.dumps(div_mean), json.dumps(summary),
                 now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return summary


def division_view(con, day, division, beats):
    """One division's list for the brief and the API: counts by reason, by range, and the squares."""
    m = con.execute("SELECT counts, summary FROM daily_list_meta WHERE issue_date=?", (day,)).fetchone()
    if not m:
        return None
    rows = [dict(r) for r in con.execute(
        "SELECT cell, beat_uid, pct, score, reason, quiet FROM daily_list WHERE issue_date=? AND division=? ORDER BY pct DESC, score DESC",
        (day, division))]
    own = json.loads(m["counts"]).get(division, 0)
    by_range = {}
    for r in rows:
        r["range"] = beats.by_uid.get(r["beat_uid"], {}).get("range", "")
        r["beat"] = beats.by_uid.get(r["beat_uid"], {}).get("beat", "")
        x = by_range.setdefault(r["range"], {"range": r["range"], "squares": 0, "quiet": 0, "beats": set()})
        x["squares"] += 1; x["quiet"] += r["quiet"]; x["beats"].add(r["beat_uid"])
    rng = sorted(({**x, "beats": len(x["beats"])} for x in by_range.values()), key=lambda x: -x["squares"])
    return {"issue_date": day, "division": division, "own_count": own, "squares": len(rows),
            "by_reason": {k: sum(r["reason"] == k for r in rows) for k in ("division", "quiet square", "statewide")},
            "by_range": rng, "cells": rows, "statewide": json.loads(m["summary"])}
