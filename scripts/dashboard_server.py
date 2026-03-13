import os
import sys
import json
import yaml
import uvicorn
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.proj_fix import setup_proj_env; setup_proj_env()

log = logging.getLogger("dashboard_v4")
app = FastAPI(title="VanAagni Real-Time Command")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Paths
JVALA_DIR = ROOT / "outputs" / "checkpoints" / "outputs" / "jvala"
INDEX_HTML = ROOT / "dashboard" / "v2" / "index.html"

app.mount("/data", StaticFiles(directory=str(ROOT / "data")), name="data")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return INDEX_HTML.read_text(encoding="utf-8")

@app.get("/api/real-data")
async def get_real_data(date: str = None):
    data = {
        "total_beats": 139,
        "total_firms_fires": 0,
        "bulletin_severity": "HIGH",
        "available_dates": ["2026-03-11", "2026-02-27"],
        "division_fwi": {"ffmc": 91.2, "dmc": 45.5, "dc": 360.1, "isi": 15.2, "bui": 68.4, "value": 32.1},
        "beats": [],
        "fires": []
    }

    if JVALA_DIR.exists():
        # If no date provided, get the LATEST available files
        files = list(JVALA_DIR.glob("*_sop.json"))
        files.sort(key=os.path.getmtime, reverse=True)
        
        for sf in files[:100]: # Top 100 recent
            try:
                sop = json.loads(sf.read_text(encoding="utf-8"))
                data["beats"].append({
                    "beat_id": sop.get("beat_id"),
                    "fused_tier": sop.get("tier", "CLEAR"),
                    "risk_score": sop.get("risk_score", 0),
                    "p_ignition": sop.get("p_ignition", 0),
                    "lat": sop.get("centroid_lat"),
                    "lon": sop.get("centroid_lon"),
                    "last_processed_date": sop.get("timestamp")
                })
            except: continue
    
    data["total_firms_fires"] = len([b for b in data["beats"] if b["fused_tier"] in ["HIGH", "CRITICAL"]])
    data["beats"].sort(key=lambda x: x["risk_score"], reverse=True)
    return data

@app.get("/api/beat-sops")
async def get_beat_sops():
    index = {}
    if JVALA_DIR.exists():
        for sf in JVALA_DIR.glob("*_sop.json"):
            try:
                sop = json.loads(sf.read_text(encoding="utf-8"))
                if sop.get("beat_id"): index[sop["beat_id"]] = sop
            except: continue
    return index

@app.get("/api/precision-layers")
async def get_precision_layers():
    combined_fc = {"type": "FeatureCollection", "features": []}
    if JVALA_DIR.exists():
        for gf in JVALA_DIR.glob("*_cfl.geojson"):
            try:
                fc = json.loads(gf.read_text(encoding="utf-8"))
                combined_fc["features"].extend(fc.get("features", []))
            except: continue
    return combined_fc

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
