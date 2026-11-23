"""Build scar reference v2 from v1 + the edge redraws (redraw_edge.csv).
FIRMS: a redrawn outline is first split by fire (split_scars.one: each pixel goes to the nearest fire burning in the
image gap; the event keeps ground nearest its own chained alerts/fire pixels), because a 6-12 km chip takes in
neighbouring fires that burned in the same gap. FSI: no seed chain exists for FSI-only points, so the redraw is
used only when it grew <= 3x (else v1 kept and flagged). Outlines that did not touch the 3 km edge are unchanged.
Out: reference/v2_2026-10-16/{firms,fsi}_event_scars.geojson + v2_changes.csv"""
import os, sys, json
import numpy as np, pandas as pd
os.chdir("/tmp"); sys.path.insert(0, "/mnt/project-files/fire-alert-scars/scripts")
import split_scars as SP
from concurrent.futures import ProcessPoolExecutor
B = "/mnt/project-files/fire-alert-scars/reference/"
V2 = B + "v2_2026-10-16/"; os.makedirs(V2, exist_ok=True)
D = pd.read_csv(B + "v2_work/redraw_edge.csv").drop_duplicates("key", keep="last")
D = D[D.status.isin(["scar", "scar_faint"]) & D.geometry.notna()]
def split_one(r):
    o = SP.one(dict(event_id=r["event_id"], geometry=r["geometry"], pre_date=r["pre_date"], post_date=r["post_date"],
                    date=r["date"], scar_ha=r["scar_ha"]))
    return (r["key"], o)
if __name__ == "__main__":
    rows = []
    for src in ("firms", "fsi"):
        fc = json.load(open(B + f"v1_2026-10-15/{src}_event_scars.geojson"))
        F = {f["properties"]["event_id"]: f for f in fc["features"]}
        d = D[D.src == src].copy()
        d["date"] = d.event_id.map(lambda e: F[e]["properties"]["date"] if e in F else None)
        res = {}
        if src == "firms":
            with ProcessPoolExecutor(4) as ex:
                res = dict(ex.map(split_one, d.to_dict("records"), chunksize=20))
        for r in d.itertuples():
            if r.event_id not in F: continue
            f = F[r.event_id]; p = f["properties"]; ha1 = p["scar_ha"]
            if src == "firms":
                o = res.get(r.key)
                if not o or not o.get("geometry_split"):
                    rows.append(dict(src=src, event_id=r.event_id, ha_v1=ha1, ha_v2=ha1, action="kept_v1_no_own_seed")); continue
                geom, ha2, act = json.loads(o["geometry_split"]), o["scar_ha_split"], "redrawn_split"
                if ha2 < ha1:   # never smaller than v1: the split can trim ground v1 already had; keep v1 then
                    rows.append(dict(src=src, event_id=r.event_id, ha_v1=ha1, ha_v2=ha1, ha_redraw=r.scar_ha, action="kept_v1_split_smaller")); continue
            else:
                if r.scar_ha > 3 * ha1:
                    p["grew_into_large_burn_v2"] = True
                    rows.append(dict(src=src, event_id=r.event_id, ha_v1=ha1, ha_v2=ha1, ha_redraw=r.scar_ha, action="kept_v1_grew_gt3x")); continue
                geom, ha2, act = json.loads(r.geometry), r.scar_ha, "redrawn"
            f["geometry"] = geom
            p.update(scar_ha_v1=ha1, scar_ha=ha2, chip_km=r.chip_km, still_at_edge=bool(r.touches_edge == True), v2_action=act,
                     pre_date=r.pre_date, post_date=r.post_date, check_date=r.check_date if isinstance(r.check_date, str) else None)
            rows.append(dict(src=src, event_id=r.event_id, ha_v1=ha1, ha_v2=ha2, ha_redraw=r.scar_ha, chip_km=r.chip_km,
                             still_at_edge=r.touches_edge, action=act))
        json.dump(fc, open(V2 + f"{src}_event_scars.geojson", "w"))
    C = pd.DataFrame(rows); C.to_csv(V2 + "v2_changes.csv", index=False)
    for (s, a), g in C.groupby(["src", "action"]):
        print(s, a, len(g), "v1 ha", round(g.ha_v1.sum()), "v2 ha", round(g.ha_v2.sum()), "median ratio", round((g.ha_v2 / g.ha_v1).median(), 2))
