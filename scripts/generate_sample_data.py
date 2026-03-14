"""Generate realistic sample data for Van Suraksha dashboard demo."""
import json, random
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
random.seed(42); np.random.seed(42)

def generate_firms_data():
    out_dir = ROOT / "data_lake" / "fire_detections" / "firms_viirs_snpp_sp"
    out_dir.mkdir(parents=True, exist_ok=True)
    for year in range(2019, 2026):
        n = random.randint(60, 180)
        rows = []
        for _ in range(n):
            r = random.random()
            month = random.choice([3,3,4,4,4,5,5,6]) if r<0.70 else (random.choice([10,11,12]) if r<0.90 else random.choice([1,2,7,8,9]))
            day = random.randint(1, 28)
            lat = np.clip(np.random.normal(24.15, 0.25), 23.82, 24.93)
            lon = np.clip(np.random.normal(77.15, 0.30), 76.47, 77.83)
            frp = np.clip(np.random.lognormal(2.0, 0.8), 0.5, 80.0)
            rows.append({
                "latitude": round(lat,5), "longitude": round(lon,5),
                "bright_ti4": round(np.random.uniform(310,370),1),
                "scan": round(np.random.uniform(0.39,1.2),2),
                "track": round(np.random.uniform(0.39,1.2),2),
                "acq_date": f"{year}-{month:02d}-{day:02d}",
                "acq_time": f"{random.randint(0,23):02d}{random.randint(0,59):02d}",
                "satellite": "Suomi NPP", "instrument": "VIIRS",
                "confidence": random.choices(["low","nominal","high"], weights=[0.15,0.45,0.40])[0],
                "version": "2.0NRT",
                "bright_ti5": round(np.random.uniform(290,330),1),
                "frp": round(frp,1),
                "daynight": random.choice(["D","D","D","N"]),
            })
        df = pd.DataFrame(rows)
        df.to_parquet(out_dir / f"viirs_snpp_sp_{year}_annual.parquet", index=False)
        print(f"  {year}: {len(df)} detections")

def generate_burn_scars():
    out_dir = ROOT / "data_lake" / "burn_scars"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for year in range(2019, 2026):
        for _ in range(random.randint(10, 20)):
            month = random.choice([3,4,4,5,5,6]); day = random.randint(1,28)
            scene_date = f"{year}-{month:02d}-{day:02d}"
            has_fire = random.random() < 0.75
            if has_fire:
                gap = random.randint(0,14)
                fd = datetime(year,month,day) - timedelta(days=gap)
                fire_date, fire_time = fd.strftime("%Y-%m-%d"), f"{random.randint(0,23):02d}:{random.randint(0,59):02d} IST"
                fire_frp = round(np.random.lognormal(2.0,0.8),1)
                dist = round(np.random.exponential(800),0)
                spatial = dist < 375
                conf = "HIGH" if gap<=3 and dist<500 else ("MEDIUM-HIGH" if gap<=7 and dist<1000 else ("LOW-MEDIUM" if gap<=14 else "NONE"))
            else:
                fire_date=fire_time=fire_frp=dist=gap=None; spatial=False; conf="NONE"
            lat = round(np.random.normal(24.15,0.25),5); lon = round(np.random.normal(77.15,0.30),5)
            rows.append({"scene_date":scene_date,"tile":f"T{random.choice(['44Q','43Q','44R'])}MH",
                "burn_area_ha":round(np.random.lognormal(3.5,1.0),1),"fire_date":fire_date,
                "fire_time_ist":fire_time,"fire_frp_mw":fire_frp,"daynight":random.choice(["D","N"]) if has_fire else None,
                "dist_to_burn_m":dist,"days_gap":gap,"confidence":conf,"spatial_hit":spatial,
                "fire_lat":lat if has_fire else None,"fire_lon":lon if has_fire else None})
    pd.DataFrame(rows).to_csv(out_dir / "fire_links.csv", index=False)
    print(f"  fire_links.csv: {len(rows)} rows")

def generate_land_cover():
    out = ROOT / "data_lake" / "land_cover" / "land_cover_stats.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = {
        "10":{"class_code":10,"label":"Tree cover","area_ha":182000,"pct_of_area":28.0},
        "20":{"class_code":20,"label":"Shrubland","area_ha":32500,"pct_of_area":5.0},
        "30":{"class_code":30,"label":"Grassland","area_ha":52000,"pct_of_area":8.0},
        "40":{"class_code":40,"label":"Cropland","area_ha":357500,"pct_of_area":55.0},
        "50":{"class_code":50,"label":"Built-up","area_ha":13000,"pct_of_area":2.0},
        "60":{"class_code":60,"label":"Bare/sparse veg","area_ha":3250,"pct_of_area":0.5},
        "80":{"class_code":80,"label":"Water","area_ha":9750,"pct_of_area":1.5},
        "_summary":{"total_area_ha":650000,"forest_ha":182000,"forest_pct":28.0,"agriculture_ha":357500,"scrub_ha":32500}
    }
    with open(out, "w") as f: json.dump(stats, f, indent=2)
    print("  land_cover_stats.json created")

def generate_terrain():
    out_dir = ROOT / "data_lake" / "terrain"; out_dir.mkdir(parents=True, exist_ok=True)
    stats = {
        "elevation_m":{"min":320,"max":648,"mean":442,"std":58},
        "slope_deg":{"mean":4.5,"std":5.2,"pct_ge_15":8.2,"pct_ge_30":2.1,"pct_ge_45":0.3},
        "aspect_octants_pct":{"N":13.2,"NE":12.5,"E":12.8,"SE":13.1,"S":12.4,"SW":12.0,"W":11.8,"NW":12.2},
        "terrain_risk_pct":{"flat_low":75.0,"south_facing_mod":15.0,"steep_high":7.0,"steep_south_extreme":3.0}
    }
    with open(out_dir / "terrain_stats.json", "w") as f: json.dump(stats, f, indent=2)
    print("  terrain_stats.json created")

if __name__ == "__main__":
    print("Generating sample data...")
    print("\n1. FIRMS data:"); generate_firms_data()
    print("\n2. Burn scars:"); generate_burn_scars()
    print("\n3. Land cover:"); generate_land_cover()
    print("\n4. Terrain:"); generate_terrain()
    print("\nDone!")
