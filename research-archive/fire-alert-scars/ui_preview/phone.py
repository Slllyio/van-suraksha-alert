# Guard phone view, as is and with a proposed burn-scar sketch on each alert card.
import json, sys, os, math, asyncio
from shapely.geometry import shape, Point
from pyproj import Transformer
from playwright.async_api import async_playwright
BASE, OUT, FEATS, STAFF, PIN = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
feats = json.load(open(FEATS)); TO = Transformer.from_crs(4326, 32643, always_xy=True)
DIRS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
def sketch(p, g):
    S = p["properties"]; px, py = TO.transform(S["lon"], S["lat"])
    W = 260; head = ""
    wait = S.get("live_status") in ("waiting", "no_pre") or S["scar_found"] == "unknown"
    if S["scar_found"] in ("yes", "faint") and g:
        poly = shape(g); xs = []
        rings = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
        pts = [[TO.transform(x, y) for x, y in r.exterior.coords] for r in rings]
        allp = [q for r in pts for q in r]
        far = max(allp, key=lambda q: math.hypot(q[0]-px, q[1]-py)); dfar = math.hypot(far[0]-px, far[1]-py)
        ang = (math.degrees(math.atan2(far[0]-px, far[1]-py)) + 360) % 360
        half = max(400, dfar * 1.15); k = (W/2) / half
        path = " ".join("M" + " L".join(f"{(x-px)*k+W/2:.1f},{W/2-(y-py)*k:.1f}" for x, y in r) + " Z" for r in pts)
        bar = 500 if half > 600 else 200; bl = bar * k
        prov = S.get("provisional")
        col = "#7a1f0f" if S["scar_found"] == "yes" else "#c77d1a"
        svg = f'''<svg viewBox="0 0 {W} {W}" width="100%" style="max-width:{W}px;background:#eef3ec;border-radius:8px;display:block;margin:8px 0">
          <path d="{path}" fill="{col}" fill-opacity="{.18 if prov else .45}" stroke="{col}" stroke-width="1.5" {'stroke-dasharray="5 4"' if prov else ''} fill-rule="evenodd"/>
          <circle cx="{W/2}" cy="{W/2}" r="6" fill="#d7301f" stroke="#fff" stroke-width="2"/>
          <text x="{W-18}" y="22" font-size="13" font-weight="700" text-anchor="middle" fill="#333">N</text><path d="M{W-18} 26 l-5 12 h10 z" fill="#333"/>
          <rect x="10" y="{W-16}" width="{bl:.0f}" height="4" fill="#333"/><text x="10" y="{W-22}" font-size="11" fill="#333">{bar} m</text></svg>'''
        msg = (f'<b>Burn scar seen from satellite: {S["scar_ha"]} ha</b>{" (faint)" if S["scar_found"]=="faint" else ""}<br>'
               f'It reaches about {dfar/1000:.1f} km {DIRS[int((ang+22.5)//45)%8]} of the alert point. '
               f'Images {S["pre_date"][5:]} and {S["post_date"][5:]}.'
               + (' <i>Provisional: a later clear image will confirm it.</i>' if prov else ''))
        return f'<div class="scarbox" style="margin-top:8px;padding:8px;border-top:1px solid #ddd">{msg}{svg}</div>'
    if wait:
        return '<div class="scarbox muted" style="margin-top:8px;padding:8px;border-top:1px solid #ddd">Burn scar: waiting for a clear satellite image (usually within 5 days).</div>'
    return ('<div class="scarbox muted" style="margin-top:8px;padding:8px;border-top:1px solid #ddd">Burn scar: none visible from satellite. '
            'Small, litter-only or under-canopy fires often leave none, so please still visit.</div>')
async def main():
    async with async_playwright() as p:
        prox = os.environ.get("HTTPS_PROXY")
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium", proxy={"server": prox, "bypass": "localhost,127.0.0.1"} if prox else None)
        c = await b.new_context(viewport={"width": 400, "height": 860}, device_scale_factor=2, is_mobile=True)
        print("login", (await c.request.post(BASE + "/api/login", data={"staff_id": STAFF, "pin": PIN})).status)
        pg = await c.new_page(); await pg.goto(BASE + "/field"); await pg.wait_for_timeout(3000)
        await pg.screenshot(path=f"{OUT}/phone_asis.png")
        blocks = {str(f["properties"]["id"]): sketch(f, f["geometry"]) for f in feats}
        n = await pg.evaluate("""B => { let n = 0; document.querySelectorAll('.card.alert').forEach(c => {
            const btn = c.querySelector('button[onclick^="form("]'); if (!btn) return;
            const id = btn.getAttribute('onclick').match(/\\d+/)[0];
            if (B[id]) { c.querySelector('.acts').insertAdjacentHTML('beforebegin', B[id]); n++; } }); return n; }""", blocks)
        print("cards", n)
        await pg.screenshot(path=f"{OUT}/phone_proposed.png")
        await b.close()
asyncio.run(main())
