"""List every Sentinel-2 / Landsat 8-9 scene over Ratapani (same query as fire-alert-scars af_scan.py: cloud < 80%),
with scene time and cloud cover, so 'looked at 30 m and saw no hot pixel' can be told from 'no scene'.
-> results/s2ls_scenes.csv"""
import json, requests, pandas as pd
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv')
BB = [A.longitude.min()-0.02, A.latitude.min()-0.02, A.longitude.max()+0.02, A.latitude.max()+0.02]
print('bbox', BB)
U = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
rows = []
for season in range(2017, 2027):
    for col in ("sentinel-2-l2a", "landsat-c2-l2"):
        q = {"eo:cloud_cover": {"lt": 80}}
        if col.startswith("landsat"):
            q["platform"] = {"in": ["landsat-8", "landsat-9"]}
        body = dict(collections=[col], bbox=BB, datetime=f"{season-1}-12-01T00:00:00Z/{season}-06-20T23:59:59Z",
                    query=q, limit=500)
        url, n = U, 0
        while url:
            r = requests.post(url, json=body, timeout=120).json()
            for f in r["features"]:
                p = f["properties"]
                rows.append(dict(season=season, sensor="s2" if col.startswith("sent") else "ls", scene=f["id"],
                                 t=p["datetime"], cloud=p.get("eo:cloud_cover"),
                                 bbox=json.dumps(f["bbox"])))
                n += 1
            nxt = [l for l in r.get("links", []) if l.get("rel") == "next"]
            if nxt:
                url, body = nxt[0]["href"], nxt[0].get("body", body)
            else:
                url = None
        print(season, col, n, flush=True)
pd.DataFrame(rows).to_csv("/mnt/project-files/research/fire-continuity/results/s2ls_scenes.csv", index=False)
