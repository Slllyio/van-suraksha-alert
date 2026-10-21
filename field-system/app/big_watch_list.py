"""Officials' big-fire watch list: a short daily layer next to the 2-day list (Akkshay, 20 Oct 2026: "keep the daily
list, and add the big-fire model as a separate short watch list of the top 1-2% of squares").

The large-fires model (research/large-fires/watch/big_watch.py) ranks each division's squares for the first look of a
200 ha+ fire in the next 2 days. On 2025 its top 1% caught 53% of 200 ha+ fires and its top 2% caught 68%; the
PC daily models caught 40% and 57% at the same shares. About 1 in 100 flagged square-days got a big-fire start.
Shown as rank only, with no % (Akkshay, 18 Oct, for officials' big-fire info). It never changes the daily list or
guards' alerts."""
import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS big_watch (
  issue_date TEXT NOT NULL, cell INTEGER NOT NULL, division TEXT NOT NULL, beat_uid TEXT, rank INTEGER NOT NULL,
  tier INTEGER NOT NULL, PRIMARY KEY (issue_date, cell, division));
CREATE TABLE IF NOT EXISTS big_watch_meta (issue_date TEXT PRIMARY KEY, model_version TEXT, summary TEXT NOT NULL,
  received_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS size_score (issue_date TEXT NOT NULL, cell INTEGER NOT NULL, score REAL NOT NULL,
  PRIMARY KEY (issue_date, cell)) WITHOUT ROWID;
"""
KEEP_SIZE_DAYS = 3
# officials' new-fire order (Akkshay's card, 20 Oct): logistic on big-fire points + logit(size score of the first-look squares
# from the night before), fitted on the app's 2025 replay (VIIRS truth, 200 ha+), tested on 2026: AUC 0.87 vs points 0.80,
# size alone 0.84; big fires in the day's top 10% of new fires 52% vs 42% / 39%. Rank only: the value is never shown.
ORDER_COEF = (-2.638, 0.5788, 0.1730)      # intercept, logit(size), points


def store(con, body, now_utc):
    """body: issue_date, model_version, cell [ids], division [per row], rank_in_division, top1 [bool], top2 [bool];
    optional size_cell + size_score (every square: chance a fire starting there passes 200 ha, for the new-fire order).
    Only top-2% rows are kept; tier 1 = top 1%, tier 2 = the next 1%. Sending a day again replaces it."""
    from .daily_list import cells
    day = body["issue_date"]                  # tables come from db.init(); executescript() would COMMIT the caller's work
    all_c, _, _, all_beat = cells()
    beat_of = dict(zip(all_c.tolist(), all_beat.tolist()))
    rows = [(day, int(c), d, beat_of.get(int(c)), int(r), 1 if t1 else 2)
            for c, d, r, t1, t2 in zip(body["cell"], body["division"], body["rank_in_division"], body["top1"], body["top2"])
            if t2 and d]
    con.execute("DELETE FROM big_watch WHERE issue_date=?", (day,))
    con.executemany("INSERT INTO big_watch VALUES (?,?,?,?,?,?)", rows)
    summary = {"top1": sum(r[5] == 1 for r in rows), "top2": len(rows), "divisions": len({r[2] for r in rows})}
    if body.get("size_cell"):
        con.execute("DELETE FROM size_score WHERE issue_date=?", (day,))
        con.executemany("INSERT INTO size_score VALUES (?,?,?)",
                        ((day, int(c), float(v)) for c, v in zip(body["size_cell"], body["size_score"])))
        old = [r[0] for r in con.execute("SELECT DISTINCT issue_date FROM size_score ORDER BY issue_date DESC")][KEEP_SIZE_DAYS:]
        con.executemany("DELETE FROM size_score WHERE issue_date=?", ((d,) for d in old))
        summary["size_squares"] = len(body["size_cell"])
        summary["size_mean_logit"] = _mean_logit(body["size_score"])
    con.execute("INSERT OR REPLACE INTO big_watch_meta VALUES (?,?,?,?)",
                (day, json.dumps(body.get("model_version")), json.dumps(summary), now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return summary


def division_view(con, day, division, beats):
    """One division's watch list, best rank first, with beat and range. Rank only, no %."""
    if not con.execute("SELECT 1 FROM big_watch_meta WHERE issue_date=?", (day,)).fetchone():
        return None
    rows = [dict(r) for r in con.execute(
        "SELECT cell, beat_uid, rank, tier FROM big_watch WHERE issue_date=? AND division=? ORDER BY rank", (day, division))]
    for r in rows:
        b = beats.by_uid.get(r["beat_uid"], {})
        r["beat"], r["range"] = b.get("beat", ""), b.get("range", "")
    return {"issue_date": day, "division": division, "top1": sum(r["tier"] == 1 for r in rows), "top2": len(rows),
            "note": "may see a big fire (200 ha+) in the next 2 days; about 1 in 100 of these squares gets one", "cells": rows}


def size_at(con, latlons, issue_date):
    """highest size score of the squares under and around (3 x 3) the given first-look dots, from that issue day's run;
    None when that night's run did not arrive."""
    import math
    from pyproj import Transformer
    from .daily_list import grid
    g = grid()
    x, y = Transformer.from_crs(4326, 32643, always_xy=True).transform([p[1] for p in latlons], [p[0] for p in latlons])
    cells = {(int((g["Y1"] - yy) // g["S"]) + a) * g["W"] + int((xx - g["X0"]) // g["S"]) + b
             for xx, yy in zip(x, y) for a in (-1, 0, 1) for b in (-1, 0, 1)}
    q = ",".join("?" * len(cells))
    r = con.execute(f"SELECT max(score) FROM size_score WHERE issue_date=? AND cell IN ({q})", [issue_date] + sorted(cells)).fetchone()
    return None if r is None or r[0] is None else float(r[0])


def _logit(v):
    import math
    p = min(max(float(v), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _mean_logit(scores):
    return round(sum(_logit(v) for v in scores) / len(scores), 4) if len(scores) else None


_MEAN = {}


def mean_logit(con, issue_date):
    """mean logit(size score) over that night's squares (else the newest night before it, else any): the stand-in for a
    fire whose first-look squares have no score. None when no night was ever received."""
    import json as _j
    r = con.execute("SELECT max(issue_date) FROM size_score WHERE issue_date<=?", (issue_date,)).fetchone()[0] \
        or con.execute("SELECT max(issue_date) FROM size_score").fetchone()[0]
    if not r:
        return None
    m = con.execute("SELECT summary, received_utc FROM big_watch_meta WHERE issue_date=?", (r,)).fetchone()
    v = _j.loads(m["summary"]).get("size_mean_logit") if m else None
    if v is not None:
        return v
    key = (r, m["received_utc"] if m else None)
    if key not in _MEAN:       # nights stored before the mean was kept with them
        _MEAN[key] = _mean_logit([x[0] for x in con.execute("SELECT score FROM size_score WHERE issue_date=?", (r,))])
    return _MEAN[key]


def order_value(points, size, mean_logit=None):
    """the combined order key (higher = order first). With no size score for the fire's squares, logit(size) is
    replaced by its mean (mean_logit), so the fire is ordered by its points on the same scale; None when neither."""
    import math
    if size is None and mean_logit is None:
        return None
    a, bs, bp = ORDER_COEF
    return 1 / (1 + math.exp(-(a + bs * (_logit(size) if size is not None else mean_logit) + bp * points)))
