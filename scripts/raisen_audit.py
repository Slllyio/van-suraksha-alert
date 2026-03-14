import sys
from pathlib import Path
from datetime import date, timedelta
import logging
import os

# Project imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from src.data.firms_ingest import fetch_viirs_detections, summarise_detections

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("RaisenAudit")

# Raisen Bounding Box (Approx)
RAISEN_BBOX = (77.35, 22.78, 78.82, 23.55)

def run_raisen_fetch():
    api_key = os.environ.get("FIRMS_MAP_KEY")
    if not api_key:
        print("ERROR: FIRMS_MAP_KEY not found in environment.")
        return

    today = date.today()
    start_date = today - timedelta(days=3)
    
    print(f"\n--- 🛰️ FETCHING RAISEN DIVISION HOTSPOTS (Last 72 hrs) ---")
    print(f"BBOX: {RAISEN_BBOX}")
    print(f"Period: {start_date} to {today}")
    
    try:
        # Fetch from Suomi-NPP (SNPP)
        gdf = fetch_viirs_detections(
            api_key=api_key,
            start_date=start_date,
            end_date=today,
            bbox=RAISEN_BBOX,
            source="VIIRS_SNPP_NRT"
        )
        
        if gdf.empty:
            print("\nRAISEN PERFORMANCE STATUS: [SECURE]")
            print(f"Period: {start_date} to {today}")
            print("False Positives: 0 (No noise detected)")
            print("Active Fires: 0")
        else:
            summary = summarise_detections(gdf)
            print("\n====================================================")
            print(f"📊 LIVE PERFORMANCE AUDIT: RAISEN DIVISION")
            print("====================================================")
            print(f"Total Hotspots:        {summary.get('total_detections', 0)}")
            print(f"Peak FRP:              {summary.get('max_frp_mw', 0):.2f} MW")
            print(f"High Confidence %:     {summary.get('high_confidence_pct', 0)}%")
            print("-" * 40)
            print(f"Status:               ACTIVE MONITORING")
            print("====================================================")
            
            # Save a specific CSV for the dashboard to pick up
            out_path = ROOT / "data_lake" / "fire_detections" / "firms_viirs_nrt" / "raisen_recent_72h.csv"
            gdf.to_csv(out_path, index=False)
            print(f"Saved Raisen hotspots to: {out_path}")

    except Exception as e:
        print(f"Fetch failed: {e}")

if __name__ == "__main__":
    run_raisen_fetch()
