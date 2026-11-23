"""Officials' weekly scar check: for each range, how many of a week's alerts left a burn scar and how many hectares burnt,
from the burn-scar thread's daily MP run (scars.py). The week checked ended 7 days before the report, because a scar
usually shows within 3-5 days of the fire. "No scar visible" is not a false alert: small litter fires and fires under
green canopy leave nothing a 20 m sensor can see (84% of real fires get a scar). Officials only; a scar never
overrules a visit. The one thing worth a second look is a visit that said "no fire" where a clear scar was found."""
import html
from datetime import datetime, timedelta, timezone

from . import firms, scars

IST = timedelta(hours=5, minutes=30)
LAG_DAYS = 7


def summarize(rows):
    """rows: {division, range, scar_found, scar_ha, event_id, outcome, geom?}. One line per (division, range), most
    hectares first. Hectares count burnt ground once: neighbouring alerts' outlines overlap, so when rows carry outlines
    (shapely, metres) the area of their union is used; otherwise each scar's own hectares, once per scar."""
    g = {}
    for r in rows:
        k = (r["division"] or "-", r["range"] or "-")
        x = g.setdefault(k, {"division": k[0], "range": k[1], "alerts": 0, "scar": 0, "none_visible": 0, "waiting": 0,
                             "_ev": {}, "no_fire_but_scar": 0})
        x["alerts"] += 1
        f = r.get("scar_found") or "unknown"
        if f in ("yes", "faint"):
            x["scar"] += 1
            if r.get("scar_ha"):
                x["_ev"][r.get("event_id") or id(r)] = r["scar_ha"]
            if r.get("geom") is not None:
                x.setdefault("_g", {})[r.get("event_id") or id(r)] = r["geom"]
            if r.get("outcome") == "no_fire" and f == "yes":
                x["no_fire_but_scar"] += 1
        elif f == "none_visible":
            x["none_visible"] += 1
        else:
            x["waiting"] += 1
    out = []
    for x in g.values():
        ev, gs = x.pop("_ev"), x.pop("_g", None)
        if gs:
            from shapely import union_all
            ev = {k: g.area / 1e4 for k, g in gs.items()}
            x["burnt_ha"] = round(union_all(list(gs.values())).area / 1e4, 1)
        checked = x["scar"] + x["none_visible"]
        x["scar_share"] = round(x["scar"] / checked, 2) if checked else None
        x.setdefault("burnt_ha", round(sum(ev.values()), 1))
        x["largest_ha"] = round(max(ev.values()), 1) if ev else None
        out.append(x)
    return sorted(out, key=lambda x: (-x["burnt_ha"], -x["alerts"]))


def _metres(g):
    """GeoJSON outline (lon/lat) -> shapely in UTM 44N metres, or None."""
    if not g:
        return None
    from shapely.geometry import shape
    from shapely.ops import transform
    from pyproj import Transformer
    global _T
    if _T is None:
        _T = Transformer.from_crs(4326, 32644, always_xy=True).transform
    return transform(_T, shape(g)).buffer(0)


_T = None


def week(con, beats, end_day, division=None):
    """Alerts first seen in the IST week [end_day - 13 d, end_day - 7 d], matched to scars as of now."""
    end = datetime.strptime(end_day, "%Y-%m-%d").replace(tzinfo=timezone.utc) - IST - timedelta(days=LAG_DAYS - 1)
    lo = end - timedelta(days=7)
    rows, detail = [], []
    for r in con.execute("""SELECT * FROM incidents WHERE COALESCE(kind,'alert')='alert' AND first_seen_utc >= ? AND first_seen_utc < ?""",
                         (firms.iso(lo), firms.iso(end))):
        p = beats.by_uid.get(r["beat_uid"], {})
        if division and p.get("division") != division:
            continue
        pts = [dict(x) for x in con.execute("SELECT lat, lon, acq_utc FROM detections WHERE incident_id=?", (r["id"],))]
        s = scars.for_points(pts, with_geometry=True) or {}
        row = {"id": r["id"], "division": p.get("division"), "range": p.get("range"), "beat": p.get("beat"),
               "first_seen_utc": r["first_seen_utc"], "lat": r["lat"], "lon": r["lon"], "outcome": r["outcome"],
               "scar_found": s.get("scar_found", "unknown"), "scar_ha": s.get("scar_ha"), "event_id": s.get("event_id"),
               "geom": _metres(s.get("geometry"))}
        rows.append(row)
        if row["outcome"] == "no_fire" and row["scar_found"] == "yes":
            detail.append({k: v for k, v in row.items() if k != "geom"})
    return {"week_ist": [(lo + IST).strftime("%Y-%m-%d"), (end + IST - timedelta(days=1)).strftime("%Y-%m-%d")],
            "division": division, "ranges": summarize(rows), "no_fire_but_scar": detail,
            "note": "No scar visible is not a false alert: small litter fires and fires under green canopy leave no scar a 20 m sensor sees."}


E = html.escape


def _ha(v):
    return "-" if v is None else f"{v:,.0f}"


def render(w, title):
    from .brief import CSS
    tr = "".join(f'<tr><td>{E(x["range"])}</td><td class="n">{x["alerts"]}</td><td class="n">{x["scar"]}</td>'
                 f'<td class="n">{"-" if x["scar_share"] is None else str(round(x["scar_share"] * 100)) + "%"}</td>'
                 f'<td class="n">{x["burnt_ha"]:,.0f}</td><td class="n">{_ha(x["largest_ha"])}</td>'
                 f'<td class="n">{x["waiting"]}</td><td class="n">{x["no_fire_but_scar"]}</td></tr>' for x in w["ranges"])
    nf = "".join(f'<div class="fire"><span class="t">{E(r["beat"] or "")}</span> <span class="h">({E(r["range"] or "")}) · '
                 f'first seen {(firms.parse_utc(r["first_seen_utc"]) + IST):%d %b %H:%M} · {r["lat"]:.4f}, {r["lon"]:.4f} · '
                 f'scar {r["scar_ha"] or 0:,.1f} ha</span></div>' for r in w["no_fire_but_scar"]) or '<p class="h">None.</p>'
    tot = sum(x["burnt_ha"] for x in w["ranges"]); al = sum(x["alerts"] for x in w["ranges"])
    sc = sum(x["scar"] for x in w["ranges"]); ck = sc + sum(x["none_visible"] for x in w["ranges"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scar check</title><style>{CSS}</style></head><body><main>
<h1>{E(title)}</h1><div class="sub">Alerts first seen {w["week_ist"][0]} to {w["week_ist"][1]} · for division and state officials</div>
<div class="kpis"><div class="kpi"><b>{al}</b><span>alerts that week</span></div><div class="kpi"><b>{sc}</b><span>left a burn scar ({round(100 * sc / ck) if ck else 0}% of those checked)</span></div>
<div class="kpi"><b>{tot:,.0f} ha</b><span>burnt (overlapping scars merged)</span></div></div>
<h2>By range, most hectares first</h2><div style="overflow-x:auto"><table><tr><th>Range</th><th class="n">Alerts</th><th class="n">Scar</th><th class="n">Scar share</th>
<th class="n">Burnt ha</th><th class="n">Largest ha</th><th class="n">Waiting</th><th class="n">"No fire" visits, scar</th></tr>{tr}</table></div>
<h2>Visits that said "no fire" where a clear scar was found</h2>{nf}
<p class="note">Waiting: no clear image since the fire yet. {E(w["note"])} A scar supports a visit and never overrules one; these are for a second look only.</p>
</main></body></html>"""
