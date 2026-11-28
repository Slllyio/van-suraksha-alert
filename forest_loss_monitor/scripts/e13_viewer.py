"""TimeSync-style review pack: per point a Sentinel-2 NDVI time series, 10 m before/after chips and a Google Earth link,
in one offline HTML page where the reader confirms or corrects my pre-labels and saves a CSV. Also writes a KML of all points.
The map class is not shown, so review stays blind. Usage: e13_viewer.py assets | html"""
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import matplotlib
import numpy as np
import pandas as pd
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import *
from common import _sentinel2

D = OUT / os.environ.get("FLM_VAL", "validation")
KEY = D / "validation_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"
A = D / "review"
PX = 96


def s2_chip(s, year, half=480):
    roi = ee.Geometry.Point([s.lon, s.lat]).buffer(800)
    img = _sentinel2(year, ("10-01", "12-15"), roi).map(lambda i: i.toFloat()).median().select(["swir2", "nir", "red"]) \
        .visualize(min=[0.0, 0.05, 0.0], max=[0.30, 0.45, 0.18])
    raw = ee.data.computePixels(dict(expression=img, fileFormat="NPY", grid=dict(
        dimensions=dict(width=PX, height=PX), crsWkt=WKT,
        affineTransform=dict(scaleX=half * 2 / PX, shearX=0, translateX=s.x - half, shearY=0, scaleY=-half * 2 / PX, translateY=s.y + half))))
    a = np.load(io.BytesIO(raw))
    return np.dstack([a["vis-red"], a["vis-green"], a["vis-blue"]]).astype("uint8")


def ndvi_series(s):
    pt = ee.Geometry.Point([s.lon, s.lat])
    c = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(pt).filterDate("2017-01-01", "2026-01-01") \
        .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"), ["cs_cdf"]) \
        .map(lambda i: i.normalizedDifference(["B8", "B4"]).rename("ndvi").updateMask(i.select("cs_cdf").gte(0.6)).copyProperties(i, ["system:time_start"]))
    r = c.getRegion(pt, 30).getInfo()
    d = pd.DataFrame(r[1:], columns=r[0]).dropna(subset=["ndvi"])
    return pd.to_datetime(d.time, unit="ms"), d.ndvi.astype(float)


def asset(s):
    f = A / f"{s.sample_id:04d}.png"
    if f.exists():
        return
    year = 2021
    for attempt in range(4):
        try:
            before, after = s2_chip(s, 2019), s2_chip(s, 2025)
            t, v = ndvi_series(s)
            break
        except Exception as e:
            if attempt == 3:
                print("fail", s.sample_id, str(e)[:120], flush=True)
                return
            time.sleep(2 ** attempt)
    fig, ax = plt.subplots(1, 3, figsize=(10, 2.6), gridspec_kw=dict(width_ratios=[1, 1, 3]))
    for a_, im, y in ((ax[0], before, 2019), (ax[1], after, 2025)):
        a_.imshow(im, interpolation="nearest")
        a_.scatter([PX / 2], [PX / 2], s=60, facecolors="none", edgecolors="yellow")
        a_.set_title(str(y), fontsize=9)
        a_.axis("off")
    ax[2].plot(t, v, ".", ms=2, color="#2e7d32")
    ax[2].set_ylim(-.1, 1)
    ax[2].set_ylabel("NDVI", fontsize=8)
    ax[2].tick_params(labelsize=7)
    ax[2].spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(f, dpi=90)
    plt.close(fig)


def assets():
    A.mkdir(parents=True, exist_ok=True)
    init()
    df = pd.read_csv(KEY)
    with ThreadPoolExecutor(5) as ex:
        list(ex.map(asset, df.itertuples()))
    print("assets", len(list(A.glob("*.png"))))


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Validation Review</title>
<style>:root{--bg:#fff;--fg:#1a1a1a;--line:#ddd}@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15181a;--fg:#e8e8e8;--line:#333}}
:root[data-theme=dark]{--bg:#15181a;--fg:#e8e8e8;--line:#333}
body{background:var(--bg);color:var(--fg);font:14px system-ui;margin:0;padding:12px 16px}header{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line)}
.c{border-bottom:1px solid var(--line);padding:10px 0}img{max-width:100%;height:auto}select,input,button{font:inherit;margin-right:8px}a{color:inherit}</style></head><body>
<header><b>Validation review</b>: confirm or correct each point. Labels save in this browser. <button id="save">Download CSV</button> <span id="n"></span></header><div id="l"></div>
<script>const R=__DATA__;const O=[["L","Clear loss"],["D","Partial canopy loss"],["T","Temporary then recovered"],["N","No change, forest"],["A","Farmland, mine or non-forest"],["W","Water"],["U","Cannot tell"]];
let S={};try{S=JSON.parse(localStorage.getItem("val")||"{}")}catch(e){}
const L=document.getElementById("l");for(const r of R){const d=document.createElement("div");d.className="c";const v=S[r.id]||r.pre||"";d.innerHTML=`<b>#${r.id}</b> ${r.div} / ${r.rng} / ${r.beat} <a href="https://earth.google.com/web/@${r.lat},${r.lon},600a,1500d,35y,0h,0t,0r" target="_blank">Google Earth</a> <a href="https://www.google.com/maps/@${r.lat},${r.lon},1500m/data=!3m1!1e3" target="_blank">Maps</a><br><img loading="lazy" src="review/${String(r.id).padStart(4,"0")}.png" alt="Point ${r.id}"><br><img loading="lazy" src="chips/${String(r.id).padStart(4,"0")}.png" alt="Point ${r.id} four years"><br><label>Label <select data-id="${r.id}">${O.map(o=>`<option value="${o[0]}"${o[0]==v?" selected":""}>${o[1]}</option>`).join("")}</select></label> <small>pre-label: ${r.pre||"none"}</small>`;L.appendChild(d)}
function cnt(){document.getElementById("n").textContent=Object.keys(S).length+" changed or confirmed of "+R.length}cnt();
L.addEventListener("change",e=>{if(e.target.dataset.id){S[e.target.dataset.id]=e.target.value;try{localStorage.setItem("val",JSON.stringify(S))}catch(x){}cnt()}});
document.getElementById("save").onclick=()=>{const a=document.createElement("a");const rows=R.map(r=>r.id+","+(S[r.id]||r.pre||""));a.href=URL.createObjectURL(new Blob(["sample_id,label_change\\n"+rows.join("\\n")],{type:"text/csv"}));a.download="labels_filled.csv";a.click()};</script></body></html>"""


def html():
    k = pd.read_csv(KEY)
    labs = D / "prelabels.csv"
    pre = pd.read_csv(labs).set_index("sample_id").label if labs.exists() else {}
    rows = [dict(id=int(s.sample_id), div=s.Division, rng=s.Range, beat=s.Beat, lat=s.lat, lon=s.lon, pre=str(pre.get(s.sample_id, "")) if len(pre) else "") for s in k.itertuples()]
    (D / "review.html").write_text(PAGE.replace("__DATA__", json.dumps(rows)), encoding="utf-8")
    kml = "".join(f"<Placemark><name>{r['id']}</name><Point><coordinates>{r['lon']},{r['lat']}</coordinates></Point></Placemark>" for r in rows)
    (D / "validation_points.kml").write_text(f'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>{kml}</Document></kml>', encoding="utf-8")
    print("wrote", D / "review.html")


if __name__ == "__main__":
    assets() if sys.argv[1] == "assets" else html()
