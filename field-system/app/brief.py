"""Officials' daily brief: one page per division, made at 16:00 IST (research list-timing test, 18 Oct 2026: a 4 pm
list from the FSI fast alerts catches as many fires as 8 pm with ~4 h more warning). It only gathers what the app
already shows on the alert cards (big-fire points, runway, 30 m arrow, still-burning chance, visits) and adds the
division's normal for the date. It never changes alert order for guards or holds back an alert."""
import html
import json
from datetime import datetime, timedelta, timezone

from . import big_fire, config, direction, firms, runway, still_burning
from .hint import safe

BRIEF_HOUR_IST = 16
IST = timedelta(hours=5, minutes=30)
NORMALS = config.BASE / "data/brief/normal_snpp.json"
_N = None


def _normals():
    global _N
    if _N is None:
        _N = json.load(open(NORMALS))["daily"] if NORMALS.exists() else {}
    return _N


def brief_clock(day):
    """16:00 IST on an IST date (YYYY-MM-DD), as UTC."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return d + timedelta(hours=BRIEF_HOUR_IST) - IST


def clock_for(day, now_utc):
    """The brief's clock: 16:00 IST of the given IST date, or the latest 16:00 IST already past; never after now."""
    if not day:
        t = now_utc + IST
        day = (t if t.hour >= BRIEF_HOUR_IST else t - timedelta(days=1)).strftime("%Y-%m-%d")
    return min(brief_clock(day), now_utc)


def _ist(s):
    return (firms.parse_utc(s) + IST).strftime("%d %b %H:%M")


def normal_week(con, division, beat_uids, now_utc):
    """S-NPP dots in the division's beats over the last 7 days vs the 2014-25 average for the same 7 days."""
    n = _normals().get(division)
    if not n:
        return None
    lo = now_utc - timedelta(days=7)
    q = ",".join("?" * len(beat_uids))
    seen = con.execute(f"""SELECT count(*) FROM detections WHERE satellite='N' AND instrument='VIIRS' AND acq_utc > ? AND acq_utc <= ?
                           AND beat_uid IN ({q})""", [firms.iso(lo), firms.iso(now_utc)] + beat_uids).fetchone()[0]
    days = [(now_utc + IST - timedelta(days=i)).timetuple().tm_yday - 1 for i in range(7)]
    norm = sum(n[min(d, 365)] for d in days)
    return {"seen": seen, "normal": round(norm, 1), "ratio": round(seen / norm, 1) if norm >= 1 else None}


def build(con, division, now_utc, beats):
    """Everything on one division's page at now_utc."""
    nu = firms.iso(now_utc)
    lo24, lo72 = firms.iso(now_utc - timedelta(hours=24)), firms.iso(now_utc - timedelta(hours=72))
    uids = [p["beat_uid"] for p in beats.props if p.get("division") == division]
    q = ",".join("?" * len(uids))
    rows = con.execute(f"""SELECT i.*, (SELECT max(acq_utc) FROM detections d WHERE d.incident_id=i.id AND d.acq_utc <= ?) AS seen_last
                           FROM incidents i WHERE COALESCE(i.kind,'alert')='alert' AND i.beat_uid IN ({q})
                           AND i.first_seen_utc <= ? AND i.last_seen_utc >= ?""", [nu] + uids + [nu, lo72]).fetchall()
    fires = []
    for r in rows:
        if not r["seen_last"] or r["seen_last"] < lo72:
            continue
        p = beats.by_uid.get(r["beat_uid"], {})
        b = safe(big_fire.check, con, r, nu)   # one broken hint is left off, the brief is still made
        visited = (r["first_report_utc"] or "9") <= nu     # as of the brief's clock, also for a past day
        fires.append({
            "id": r["id"], "beat": p.get("beat", r["beat_uid"]), "range": p.get("range", ""), "lat": r["lat"], "lon": r["lon"],
            "first_seen_utc": r["first_seen_utc"], "seen_last_utc": r["seen_last"], "new": r["first_seen_utc"] >= lo24,
            "visited": visited, "overdue": not visited and r["due_utc"] < nu,
            "big_fire": b, "points": b["points"] if b and b.get("new_fire") else None, "guard_flag": bool(b and b.get("guard_flag")),
            "_order": safe(big_fire.order_key, con, r, nu, default=(2, 0.0)),
            "runway": safe(runway.for_incident, con, r["id"]), "direction": safe(direction.for_incident, con, r["id"], now_utc),
            "still_burning": safe(still_burning.check, con, r["id"], now_utc), "sensors": r["sensors"]})
    new = [f for f in fires if f["new"]]
    new.sort(key=lambda f: (f["_order"], f["first_seen_utc"]))    # points + size score (big_fire.order_key)
    for f in fires:
        f.pop("_order", None)
    burning = [f for f in fires if not f["new"] and f["seen_last_utc"] >= lo24]
    dark = sorted([f for f in fires if f["still_burning"] and f["still_burning"]["chance"] >= 0.16],
                  key=lambda f: -f["still_burning"]["chance"])
    overdue = sorted([f for f in fires if f["overdue"]], key=lambda f: f["first_seen_utc"])
    ranges = {}
    for f in fires:
        g = ranges.setdefault(f["range"] or "-", {"range": f["range"] or "-", "new": 0, "burning": 0, "not_visited": 0, "big": 0})
        g["new"] += f["new"]; g["burning"] += (not f["new"] and f["seen_last_utc"] >= lo24)
        g["not_visited"] += f["overdue"]; g["big"] += f["guard_flag"] and f["new"]
    return {"division": division, "clock_utc": nu, "clock_ist": (now_utc + IST).strftime("%d %b %Y, %H:%M IST"),
            "counts": {"new": len(new), "burning": len(burning), "lost_from_view": len(dark), "not_visited": len(overdue),
                       "big_flags": sum(f["guard_flag"] for f in new)},
            "normal_week": normal_week(con, division, uids, now_utc),
            "new": new, "burning": burning, "dark": dark, "overdue": overdue,
            "ranges": sorted(ranges.values(), key=lambda g: (-g["new"], -g["burning"], g["range"])),
            "check_list": _check_list(con, division, now_utc, beats)}


def _check_list(con, division, now_utc, beats):
    """The newest 2-day check list for the division (app/daily_list.py): the evening list is issued at
    17:00-18:00 IST, so a morning brief shows last evening's list. Lists older than yesterday are not shown."""
    from . import daily_list
    today = (now_utc + IST).strftime("%Y-%m-%d")
    yday = (now_utc + IST - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        r = con.execute("SELECT MAX(issue_date) FROM daily_list_meta WHERE issue_date BETWEEN ? AND ?",
                        (yday, today)).fetchone()
        if not r or not r[0]:     # say so instead of leaving the section out
            return {"missing": today, "why": "not received yet (the evening run posts it at about 17:30 IST)"}
        v = daily_list.division_view(con, r[0], division, beats)
    except Exception:
        import logging; logging.getLogger("brief").exception("check list for %s %s", division, today)
        return {"missing": today, "why": "could not be read"}
    if not v:
        return {"missing": today, "why": "not received yet (the evening run posts it at about 17:30 IST)"}
    v.pop("cells")
    return v


def statewide(con, now_utc, beats):
    """One line per division with anything open, busiest first (for the state control room)."""
    out = []
    for d in sorted({p.get("division") for p in beats.props if p.get("division")}):
        b = build(con, d, now_utc, beats)
        if b["counts"]["new"] or b["counts"]["burning"] or b["counts"]["not_visited"]:
            out.append({"division": d, **b["counts"], "normal_week": b["normal_week"]})
    return sorted(out, key=lambda x: (-x["new"], -x["burning"]))


# ---------- page ----------
E = html.escape
CSS = """
:root{--ink:#1d1d1b;--mute:#5f5e5a;--line:#d8d6cf;--bg:#fbfaf7;--red:#b42318;--amber:#9a5b00;--chip:#efede6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#ecebe6;--mute:#a9a7a0;--line:#3b3a36;--bg:#1b1b19;--red:#ff8a7a;--amber:#f2b453;--chip:#2a2926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}h1{font-size:22px;margin:0}h2{font-size:16px;margin:22px 0 6px;border-bottom:1px solid var(--line);padding-bottom:4px}
.sub{color:var(--mute);font-size:13px}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:14px 0}
.kpi{border:1px solid var(--line);border-radius:8px;padding:8px 10px}.kpi b{display:block;font-size:22px}.kpi span{font-size:12px;color:var(--mute)}
.fire{border-top:1px solid var(--line);padding:8px 0}.fire:first-child{border-top:0}.fire .t{font-weight:600}
.pts{display:inline-block;min-width:28px;text-align:center;background:var(--chip);border-radius:10px;padding:0 6px;font-weight:600;margin-right:6px}
.flag{color:var(--red);font-weight:600}.h{color:var(--mute);font-size:13px}.warn{color:var(--amber)}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left}th{color:var(--mute);font-weight:500}
td.n,th.n{text-align:right}.note{font-size:12px;color:var(--mute);margin-top:18px}
@media print{body{background:#fff;color:#000;font-size:10.5px;line-height:1.3}main{padding:0;max-width:none}.kpis{grid-template-columns:repeat(5,1fr);margin:6px 0}.kpi{padding:4px 6px}.kpi b{font-size:16px}.fire{padding:3px 0}h2{margin:10px 0 3px;font-size:13px}td,th{padding:2px 4px}.h{font-size:10px}h2{break-after:avoid}.fire{break-inside:avoid}}
"""


def _fire_line(f, why=True):
    pts = f'<span class="pts">{f["points"]}</span>' if f["points"] is not None else '<span class="pts">-</span>'
    head = f'{pts}<span class="t">{E(f["beat"])}</span> <span class="h">({E(f["range"])}) · first seen {_ist(f["first_seen_utc"])} · {f["lat"]:.4f}, {f["lon"]:.4f}</span>'
    bits = []
    if f["guard_flag"]:
        bits.append('<span class="flag">Guards told: may become a big fire</span>')
    if f["runway"]:
        bits.append(E(f["runway"]["text"]))
    if f["direction"]:
        bits.append(E(f["direction"]["text"]))
    if f["still_burning"]:
        bits.append(f'<span class="warn">{E(f["still_burning"]["text"])}</span>')
    if f["points"] is None and why:
        bits.append("Points after the first VIIRS look" if "VIIRS" not in (f["sensors"] or "") else "Part of a fire seen in the last 30 h")
    bits.append("Visited" if f["visited"] else ("<b>Not visited, past due</b>" if f["overdue"] else "Visit due"))
    return f'<div class="fire">{head}<div class="h">{" · ".join(bits)}</div></div>'


def _check_html(v):
    if not v:
        return ""
    if v.get("missing"):
        return f'<h2>Check in the next 2 days</h2><p class="h warn">The list for {E(v["missing"])} is {E(v["why"])}.</p>'
    st = (v.get("statewide") or {}).get("stale")
    stale = f'<p class="h warn">Some inputs were old or missing for this list: {E(", ".join(map(str, st)))}.</p>' if st else ""
    r = v["by_reason"]
    rows = "".join(f'<tr><td>{E(g["range"] or "-")}</td><td class="n">{g["squares"]}</td><td class="n">{g["beats"]}</td>'
                   f'<td class="n">{g["quiet"]}</td></tr>' for g in v["by_range"][:12])
    return (f'<h2>Check in the next 2 days</h2><div class="sub">{v["squares"]} squares of 500 m (own count {v["own_count"]}): '
            f'{r["division"]} kept for the division, {r["quiet square"]} quiet squares (no fire within 5 km for 7 days), '
            f'{r["statewide"]} from the statewide pool. Busy divisions borrow checks from quiet ones; every division '
            f'keeps at least half its own count.</div><table><tr><th>Range</th><th class="n">Squares</th><th class="n">Beats</th>'
            f'<th class="n">Quiet</th></tr>{rows}</table>{stale}')


def render(b, top=8, few=5):
    c, nw = b["counts"], b["normal_week"]
    norm = ""
    if nw:
        r = f'{nw["ratio"]}x' if nw["ratio"] is not None else "n/a"
        norm = (f'<div class="kpi"><b>{r}</b><span>last 7 days vs normal ({nw["seen"]} S-NPP dots; 2014-25 average '
                f'{nw["normal"]})</span></div>')
    k = (f'<div class="kpis"><div class="kpi"><b>{c["new"]}</b><span>new fires, last 24 h</span></div>'
         f'<div class="kpi"><b>{c["big_flags"]}</b><span>new fires guards were told may become big</span></div>'
         f'<div class="kpi"><b>{c["burning"]}</b><span>older fires still seen burning</span></div>'
         f'<div class="kpi"><b>{c["not_visited"]}</b><span>alerts not visited, past due</span></div>{norm}</div>')
    new = "".join(_fire_line(f) for f in b["new"][:top]) or '<p class="h">No new fires.</p>'
    more = f'<p class="h">And {len(b["new"]) - top} more new fires lower in this order: see the alert list.</p>' if len(b["new"]) > top else ""
    sized = any((f.get("big_fire") or {}).get("order_basis") == "points + size score" for f in b["new"])
    basis = ("from the big-fire points of the first VIIRS look together with the square's size score from the night before"
             if sized or not b["new"] else "from the big-fire points of the first VIIRS look (no size score arrived for the night before)")
    shown = {f["id"] for f in b["new"][:top]}
    dk = [f for f in b["dark"] if f["id"] not in shown][:few]
    shown |= {f["id"] for f in dk}
    ov = [f for f in b["overdue"] if f["id"] not in shown][:few]
    dark = "".join(_fire_line(f, False) for f in dk) or '<p class="h">None beyond the fires above.</p>'
    od = "".join(_fire_line(f, False) for f in ov) or '<p class="h">None beyond the fires above.</p>'
    od += f'<p class="h">{len(b["overdue"])} alerts not visited in all, oldest first; see the range table.</p>' if len(b["overdue"]) > len(ov) else ""
    rng = "".join(f'<tr><td>{E(g["range"])}</td><td class="n">{g["new"]}</td><td class="n">{g["big"]}</td><td class="n">{g["burning"]}</td>'
                  f'<td class="n">{g["not_visited"]}</td></tr>' for g in b["ranges"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fire brief {E(b["division"])}</title><style>{CSS}</style></head><body><main>
<h1>Fire brief: {E(b["division"].replace("_", " "))} division</h1><div class="sub">{b["clock_ist"]} · for range and division officers</div>{k}
<h2>New fires, most likely to grow first</h2><div class="sub">Ordered by how likely each is to pass 200 ha, {basis}. It is an order, not a %.</div>{new}{more}
<h2>Lost from view, may still be burning</h2>{dark}
<h2>Not visited, past due</h2>{od}
{_check_html(b.get("check_list"))}
<h2>By range</h2><table><tr><th>Range</th><th class="n">New</th><th class="n">Told big</th><th class="n">Still burning</th><th class="n">Not visited</th></tr>{rng}</table>
<p class="note">Hints are for officials. "Likely to burn farther toward" was right 2 times in 3 on 4,104 past fronts (chance 1 in 2). The 30 m arrow pointed the right way about 2 times in 3. Still-burning chances come from 30 m scenes of past fires VIIRS had stopped seeing. Guards keep searching all sides. Every alert still goes to its beat.</p>
</main></body></html>"""


def render_state(rows, clock_ist):
    tr = "".join(f'<tr><td>{E(x["division"].replace("_", " "))}</td><td class="n">{x["new"]}</td><td class="n">{x["big_flags"]}</td>'
                 f'<td class="n">{x["burning"]}</td><td class="n">{x["lost_from_view"]}</td><td class="n">{x["not_visited"]}</td>'
                 f'<td class="n">{(str(x["normal_week"]["ratio"]) + "x") if x["normal_week"] and x["normal_week"]["ratio"] is not None else "-"}</td></tr>'
                 for x in rows)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fire brief MP</title><style>{CSS}</style></head><body><main>
<h1>Fire brief: Madhya Pradesh</h1><div class="sub">{clock_ist} · divisions with open fires, busiest first</div>
<div style="overflow-x:auto"><table><tr><th>Division</th><th class="n">New 24 h</th><th class="n">Told big</th><th class="n">Still burning</th>
<th class="n">Lost from view</th><th class="n">Not visited</th><th class="n">7 days vs normal</th></tr>{tr}</table></div>
<p class="note">"7 days vs normal": S-NPP VIIRS dots in the division's beats over the last 7 days, against the 2014-25 average for the same week.</p>
</main></body></html>"""
