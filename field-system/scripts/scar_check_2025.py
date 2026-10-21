# Weekly scar check replayed on the 2025 season (all MP) from the burn-scar thread's history files: events (alert
# clusters, forest only) from mp/out/mp_events.csv, scars from mp/out/scars_mp_hist.csv. Writes docs/scar_check/.
import json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import scar_check
O = Path("/mnt/project-files/fire-alert-scars/mp/out"); D = Path(__file__).resolve().parent.parent / "docs/scar_check"; D.mkdir(exist_ok=True)
e = pd.read_csv(O / "mp_events.csv", usecols=["event_id", "acq_date", "acq_time", "latitude", "longitude", "Division", "Range", "Beat", "forest"])
e = e[(e.event_id.str[1:5] == "2025") & e.forest.astype(str).eq("True")]
e = e[(e.acq_date >= "2025-02-15") & (e.acq_date <= "2025-06-15")]
h = pd.read_csv(O / "scars_mp_hist.csv", usecols=["event_id", "status", "scar_ha"])
F = {"scar": "yes", "scar_faint": "faint", "no_scar_seen": "none_visible"}
e = e.merge(h, on="event_id", how="left")
e["scar_found"] = e.status.map(F).fillna("unknown")
# outlines (each event's grown scar), metres; read only through the burn-scar thread's reader
sys.path.insert(0, "/mnt/project-files/fire-alert-scars/mp/scripts")
from read_geom import read_hist_geom
from shapely import wkt
from shapely.ops import transform
from pyproj import Transformer
G = read_hist_geom(); G = G[G.event_id.isin(set(e.event_id))]
T = Transformer.from_crs(4326, 32644, always_xy=True).transform
GM = {k: transform(T, wkt.loads(g)).buffer(0) for k, g in zip(G.event_id, G.geometry) if isinstance(g, str)}
print("outlines", len(GM), flush=True)
rows = [{"division": r.Division, "range": r.Range, "beat": r.Beat, "scar_found": r.scar_found,
         "scar_ha": None if pd.isna(r.scar_ha) else float(r.scar_ha), "event_id": r.event_id, "outcome": None, "geom": GM.get(r.event_id) if r.scar_found in ("yes", "faint") else None,
         "week": pd.Timestamp(r.acq_date).to_period("W-SUN").start_time.strftime("%Y-%m-%d"),
         "first_seen_utc": f"{r.acq_date}T{int(r.acq_time):04d}"[:13] + ":" + f"{int(r.acq_time):04d}"[2:] + ":00Z",
         "lat": r.latitude, "lon": r.longitude} for r in e.itertuples()]
weeks = sorted({r["week"] for r in rows})
W = []
for w in weeks:
    s = scar_check.summarize([r for r in rows if r["week"] == w])
    sc = sum(x["scar"] for x in s); ck = sc + sum(x["none_visible"] for x in s)
    W.append({"week_from": w, "alerts": sum(x["alerts"] for x in s), "scar_share": round(sc / ck, 2) if ck else None,
              "burnt_ha": round(sum(x["burnt_ha"] for x in s)), "ranges_with_fire": len(s),
              "top10_ranges_share_of_ha": round(sum(x["burnt_ha"] for x in s[:10]) / max(sum(x["burnt_ha"] for x in s), 1), 2)})
season = scar_check.summarize(rows)
tot = sum(x["burnt_ha"] for x in season); n = len(season)
from shapely import union_all
state_union = round(union_all([g for g in (r["geom"] for r in rows) if g is not None]).area / 1e4)
sum_own = round(sum(r["scar_ha"] or 0 for r in rows if r["scar_found"] in ("yes", "faint")))
top = sorted(season, key=lambda x: -x["burnt_ha"])
conc = {f"top_{p}pct_ranges": round(sum(x["burnt_ha"] for x in top[:max(1, round(n * p / 100))]) / tot, 2) for p in (5, 10, 20)}
# does last week's hectares rank tell which ranges burn most next week? (rank correlation over ranges, week to week)
import numpy as np
piv = pd.DataFrame([{"w": w, "k": (x["division"], x["range"]), "ha": x["burnt_ha"]} for w in weeks for x in scar_check.summarize([r for r in rows if r["week"] == w])])
piv = piv.pivot_table(index="k", columns="w", values="ha", fill_value=0)
rho = [pd.Series(piv[a]).rank().corr(pd.Series(piv[b]).rank()) for a, b in zip(piv.columns[:-1], piv.columns[1:])]
out = {"events": len(rows), "ranges": n, "burnt_ha": round(tot), "burnt_ha_statewide_union": state_union, "sum_of_each_scar_ha": sum_own, "scar_share_checked": round(sum(x["scar"] for x in season) / sum(x["scar"] + x["none_visible"] for x in season), 2),
       "waiting_or_unchecked": sum(x["waiting"] for x in season), "concentration": conc,
       "week_to_week_rank_corr_median": round(float(np.nanmedian(rho)), 2), "weeks": W}
json.dump(out, open(D / "season_2025.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "weeks"}, indent=1))
for x in W: print(x)
# example page: the week with most hectares, its busiest division
bw = max(W, key=lambda x: x["burnt_ha"])["week_from"]
wr = [r for r in rows if r["week"] == bw]
dv = pd.Series([r["division"] for r in wr]).value_counts().index[0]
we = (pd.Timestamp(bw) + pd.Timedelta(days=6)).strftime("%Y-%m-%d")
page = {"week_ist": [bw, we], "division": dv, "ranges": scar_check.summarize([r for r in wr if r["division"] == dv]), "no_fire_but_scar": [],
        "note": "No scar visible is not a false alert: small litter fires and fires under green canopy leave no scar a 20 m sensor sees."}
open(D / f"{dv}_{bw}.html", "w").write(scar_check.render(page, f"Scar check: {dv.replace('_', ' ')} division"))
print("page", dv, bw)
