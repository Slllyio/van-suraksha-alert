import json, os, sys, math, asyncio
import pandas as pd
from playwright.async_api import async_playwright
S = os.path.dirname(os.path.abspath(__file__)); BASE = sys.argv[1]; OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
P = "/mnt/project-files/fire-alert-scars/"
ev = pd.concat([pd.read_csv(P + "fsi/fsi_alert_events.csv"), pd.read_csv(P + "out/event_scars.csv"),
                pd.read_csv(P + "live/events.csv").assign(geometry=None).pipe(lambda d: d.assign(lat=d.latitude, lon=d.longitude))], ignore_index=True)
geo = {}
try:
    for f in json.load(open(P + "live/scars.geojson"))["features"]:
        geo[f["properties"]["event_id"]] = f["geometry"]
except Exception as e: print("live geo", e)

async def main():
    async with async_playwright() as p:
        prox = os.environ.get("HTTPS_PROXY")
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None, proxy={"server": prox, "bypass": "localhost,127.0.0.1"} if prox else None, args=["--ignore-certificate-errors"])
        async def ctx(staff, pin, w, h):
            c = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2, ignore_https_errors=True)
            r = await c.request.post(BASE + "/api/login", data={"staff_id": staff, "pin": pin}); print("login", r.status)
            return c
        c = await ctx(1, "1111", 1500, 900); pg = await c.new_page()
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(4000)
        inc = await (await c.request.get(BASE + "/api/incidents?days=7")).json()
        feats = []
        for i in inc:
            d = await (await c.request.get(BASE + f"/api/incidents/{i['id']}")).json()
            s = d.get("burn_scar") or {}
            if not s: continue
            g = None
            if s.get("event_id"):
                m = ev[ev.event_id == s["event_id"]]
                for _, r in m.iterrows():
                    if math.hypot(r.lat - i["lat"], r.lon - i["lon"]) < 0.03:
                        g = geo.get(r.event_id) or (json.loads(r.geometry) if isinstance(r.geometry, str) else None); break
            feats.append({"type": "Feature", "geometry": g, "properties": {"id": i["id"], "lat": i["lat"], "lon": i["lon"], **s}})
        json.dump(feats, open(OUT + "/scar_feats.json", "w"))
        print("feats", len(feats), sum(f["geometry"] is not None for f in feats))
        async def shot(name, sel=None):
            await pg.wait_for_timeout(2500); await pg.screenshot(path=f"{OUT}/{name}.png"); print("shot", name)
        targets = json.loads(sys.argv[3])     # {"name": incident_id}
        for name, iid in targets.items():
            await pg.evaluate(f"openInc({iid})"); await shot("asis_" + name)
        # proposed: scar outlines on the map + legend, using the same drawer
        await pg.evaluate("""feats => {
          const C = {yes: '#7a1f0f', faint: '#c77d1a', none_visible: '#666', unknown: '#999'};
          const lay = L.layerGroup().addTo(map);
          feats.forEach(f => { const p = f.properties, prov = p.provisional, wait = p.live_status === 'waiting' || p.live_status === 'no_pre';
            if (f.geometry) L.geoJSON(f.geometry, {style: {color: C[p.scar_found], weight: 2, dashArray: prov ? '6 5' : null,
               fillColor: C[p.scar_found], fillOpacity: prov ? .15 : .35}}).bindTooltip(`Burn scar ${p.scar_ha} ha${prov ? ' (provisional)' : ''} · images ${p.pre_date} to ${p.post_date}`).addTo(lay);
            else L.circle([p.lat, p.lon], {radius: 250, color: wait ? '#4aa3ff' : '#ffffff', weight: 3, dashArray: '3 6', fill: false})
               .bindTooltip(wait ? 'Waiting for a clear image' : 'No scar visible from satellite').addTo(lay); });
          lay.eachLayer(l => l.bringToBack && l.bringToBack());
          const lg = L.control({position: 'topleft'}); lg.onAdd = () => { const d = L.DomUtil.create('div');
            d.style.cssText = 'background:#fff;padding:6px 9px;border-radius:6px;font:12px system-ui;line-height:1.7;box-shadow:0 1px 4px #0004';
            d.innerHTML = '<b>Burn scar (Sentinel-2 / Landsat)</b><br><span style="display:inline-block;width:14px;height:10px;background:#7a1f0f88;border:2px solid #7a1f0f"></span> scar seen, confirmed<br><span style="display:inline-block;width:14px;height:10px;background:#7a1f0f22;border:2px dashed #7a1f0f"></span> scar seen, provisional<br><span style="display:inline-block;width:14px;height:10px;background:#c77d1a55;border:2px solid #c77d1a"></span> faint scar<br><span style="display:inline-block;width:12px;height:12px;border-radius:50%;border:2px dashed #999"></span> no scar visible (not a false alert)<br><span style="display:inline-block;width:12px;height:12px;border-radius:50%;border:2px dashed #4aa3ff"></span> waiting for a clear image';
            return d; }; lg.addTo(map); map.removeLayer(osm); sat.addTo(map); sat.bringToBack(); }""", feats)
        for name, iid in targets.items():
            await pg.evaluate(f"openInc({iid})"); await pg.wait_for_timeout(1200)
            f = next(x for x in feats if x["properties"]["id"] == iid)
            await pg.evaluate("""f => { let b = L.latLng(f.properties.lat, f.properties.lon).toBounds(1200);
              if (f.geometry) b = b.extend(L.geoJSON(f.geometry).getBounds());
              map.fitBounds(b, {paddingTopLeft: [300, 40], paddingBottomRight: [620, 40], maxZoom: 15}); }""", f)
            await shot("proposed_" + name)
        await pg.evaluate("document.getElementById('drawer').classList.remove('open'); void map.setView([22.98,77.85],11)"); await shot("proposed_overview")
        await b.close()
asyncio.run(main())
