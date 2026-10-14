"""Metadata-only WeatherNext probe (no collection-wide aggregates)."""
import ee, json
from pathlib import Path

ee.Initialize(project="van-suraksha-alert")
OUT = Path(r"E:\FIRE\ratapani\ee\weathernext_probe.txt")
lines = []
for name in ["weathernext_3_0_0_0p1deg", "weathernext_2_0_0"]:
    path = f"projects/gcp-public-data-weathernext/assets/{name}"
    try:
        meta = ee.data.getAsset(path)
        lines.append(f"{path}: ACCESS OK type={meta.get('type')}")
        first = ee.data.listAssets({"parent": path, "pageSize": 1}).get("assets", [])
        if first:
            a = first[0]
            lines.append(f"  first listed: {a['id']} start={a.get('startTime')}")
        for since in ["2026-10-12", "2026-10-05", "2026-09-01"]:
            r, tok = [], None
            while True:
                q = {"parent": path, "pageSize": 1000, "filter": f'startTime >= "{since}T00:00:00Z"'}
                if tok:
                    q["pageToken"] = tok
                resp = ee.data.listAssets(q)
                r += resp.get("assets", [])
                tok = resp.get("nextPageToken")
                if not tok:
                    break
            if r:
                last = max(r, key=lambda a: a.get("startTime", ""))
                inits = sorted({a["id"].rsplit("/", 1)[1][:12] for a in r})
                lines.append(f"  latest image (all {len(r)} since {since}): {last['id']} start={last.get('startTime')}")
                lines.append(f"  latest init time (id prefix): {inits[-1]}")
                img = ee.data.getAsset(last["id"])
                bands = [b["id"] for b in img.get("bands", [])]
                lines.append(f"  bands({len(bands)}): {bands[:40]}")
                lines.append(f"  properties: {json.dumps(img.get('properties', {}))[:600]}")
                break
    except Exception as e:
        lines.append(f"{path}: FAILED {type(e).__name__}: {str(e)[:300]}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
