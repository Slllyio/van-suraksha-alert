"""
Van Suraksha — Forest Fire Monitoring Dashboard
================================================
Streamlit dashboard for Guna Division, Madhya Pradesh.

Tabs:
  1. Live Alert       — today's fire alert bulletin + FWI gauge
  2. 3D Digital Twin  — CesiumJS globe visualization
  3. Fire History     — FIRMS fire detections on interactive map
  4. Burn Scars       — Prithvi burn scar catalog + causal fire links
  5. FWI Trends       — Canadian FWI time series, annual peaks, seasonality
  6. Weather & Terrain— GFS NWP forecasts + terrain analysis
  7. Land Cover       — ESA WorldCover forest/agriculture breakdown

Run:
  streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# ── Paths & Path Injection (CRITICAL) ────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pydeck as pdk
import plotly.io as pio
import streamlit as st

# Cognitive AI Modules
try:
    from src.analysis.forest_chat import ForestChatEngine
    from src.analysis.maintenance_ai import MaintenanceAI
    from src.analysis.vlm_auditor import VLMAuditor
    from src.analysis.anomaly_scorer import compute_anomaly_score
    from src.analysis.ai_dispatcher import AISignalCorps
except ImportError as e:
    ForestChatEngine = None
    MaintenanceAI = None
    VLMAuditor = None
    compute_anomaly_score = None
    AISignalCorps = None

# ── Path Configuration ────────────────────────────────────────────────────────
ALERT_DIR    = ROOT / "data_lake" / "alerts"
FIRMS_SP     = ROOT / "data_lake" / "fire_detections" / "firms_viirs_snpp_sp"
FIRMS_NRT    = ROOT / "data_lake" / "fire_detections" / "firms_viirs_nrt"
FWI_PATH     = ROOT / "data_lake" / "fire_weather"   / "fwi_daily.parquet"
LINKS_CSV    = ROOT / "data_lake" / "burn_scars"     / "fire_links.csv"
LC_STATS     = ROOT / "data_lake" / "land_cover"     / "land_cover_stats.json"
BOUND_DIR    = ROOT / "data_lake" / "boundaries"
TERRAIN_DIR  = ROOT / "data_lake" / "terrain"
WEATHER_DIR  = ROOT / "data_lake" / "weather_forecasts" / "gfs"

# ── Guna Division spatial extent ──────────────────────────────────────────────
GUNA_BBOX = (76.45, 23.80, 77.85, 24.95)   # min_lon, min_lat, max_lon, max_lat

# ── Clear stale cache on fresh load ──────────────────────────────────────────
if "cache_cleared" not in st.session_state:
    st.cache_data.clear()
    st.session_state["cache_cleared"] = True

# ── Live Demo Mode — Guided Presenter Walkthrough ───────────────────────────
DEMO_STEPS = [
    {
        "tab": "\U0001f6a8 Live Alert",
        "title": "STEP 1 — Fire Detection & Alert",
        "script": (
            "On 14 April 2019, VANAAGNI detected a **CRITICAL-severity** fire in Guna Division. "
            "Fire Radiative Power: **62.8 MW** — classified as **INFERNO**. "
            "The Canadian Fire Weather Index hit **55.5 (Extreme)**. "
            "Temperature 33.5\u00b0C, Humidity just 15.4%. "
            "All six FWI sub-indices are displayed for operational transparency."
        ),
        "highlight": "Observe the CRITICAL banner, FWI gauge, and all weather metrics.",
    },
    {
        "tab": "\U0001f6a8 Live Alert",
        "title": "STEP 2 — AI Tactical Dispatch",
        "script": (
            "The AI computed Byram fire intensity at **31,375 kW/m** and Rate of Spread at "
            "**104.58 m/min**. At this speed, ground crews **cannot outrun the fire**. "
            "The system classified this as **Defensive/Evacuation** and generated "
            "bilingual Hindi/English tactical dispatch orders automatically. "
            "The dispatch directs: aerial support, backfiring equipment, CROWN FIRE safety directive."
        ),
        "highlight": "Scroll to the Prescriptive AI Tactical Dispatch section.",
    },
    {
        "tab": "\U0001f6a8 Live Alert",
        "title": "STEP 3 — Autonomous Fire Verification",
        "script": (
            "The VLM Autonomous Auditor cross-verified the detection using spectral analysis "
            "and FRP thresholds. Verdict: **CONFIRMED FIRE** at **92% confidence**. "
            "This eliminates false-alarm fatigue \u2014 only verified alerts reach field teams. "
            "The reasoning is transparent: high-confidence thermal anomaly with strong spectral signature."
        ),
        "highlight": "See the VLM Visual Audit panel with verdict, confidence, and reasoning.",
    },
    {
        "tab": "\U0001f310 3D Digital Twin",
        "title": "STEP 4 — 3D Fire Spread Simulation",
        "script": (
            "The Command Horizon visualizes the fire on **satellite terrain** using CesiumJS. "
            "Officers can run the **Muhurta-2D** fire spread simulation. "
            "Click **START SIM** \u2014 in 30 modeled minutes, this INFERNO consumed **467 hectares** "
            "with **CROWN FIRE** behavior. The elliptical spread follows the Rothermel model. "
            "This proves why the AI recommended Defensive/Evacuation \u2014 aerial response only."
        ),
        "highlight": "Click START SIM to run the fire spread simulation on the 3D globe.",
    },
    {
        "tab": "\U0001f4ca Fire History",
        "title": "STEP 5 — Historical Fire Intelligence",
        "script": (
            "VIIRS satellite data reveals **164 fire detections** across Guna Division. "
            "The Year \u00d7 Month heatmap shows **April\u2013May** as peak fire months. "
            "2025 recorded **86 detections** \u2014 the highest in recent years. "
            "Dense clustering in northern and central areas reveals persistent fire-prone zones "
            "requiring enhanced patrolling."
        ),
        "highlight": "Note the seasonal patterns and geographic clustering of hotspots.",
    },
    {
        "tab": "\U0001f6f0\ufe0f Burn Scars",
        "title": "STEP 6 — Burn Scar Damage Assessment",
        "script": (
            "IBM-NASA\u2019s **Prithvi-EO-2.0** foundation model processed **484 satellite scenes** "
            "to map burn scars. **80% matched** FIRMS detections. "
            "The causal link analysis classifies each scene\u2019s fire evidence from HIGH to NONE. "
            "Peak FRP matched: **29.2 MW**. Burn areas up to **50,899 hectares** documented."
        ),
        "highlight": "Review the Causal Link Confidence chart and HIGH-confidence fire events.",
    },
    {
        "tab": "\U0001f321\ufe0f FWI Trends",
        "title": "STEP 7 — 13-Year Climate Intelligence",
        "script": (
            "Fire Weather Index analysis spanning **2013\u20132025** reveals a dangerous trend. "
            "Peak FWI reached **91.8** in 2024. Fire season mean: **40.4 (Very High)**. "
            "**38%** of fire season days are classified Very High or worse. "
            "**Every single year** exceeds the Extreme threshold \u2014 Guna Division has a structural fire risk."
        ),
        "highlight": "The annual peak bar chart and Year x Month heatmap tell the climate story.",
    },
    {
        "tab": "\u26f0\ufe0f Weather & Terrain",
        "title": "STEP 8 — Weather Forecasts & Terrain Risk",
        "script": (
            "GFS weather forecasts enable **24/48/72-hour** fire weather prediction via Herbie. "
            "Temperature peaks at **40\u00b0C in May** with humidity dropping to critical lows. "
            "Copernicus DEM 30m terrain analysis: elevation 255\u2013589m, predominantly flat agricultural terrain "
            "with moderate south-facing slope risk."
        ),
        "highlight": "Weather-terrain fusion powers the next-day fire danger forecast.",
    },
    {
        "tab": "\U0001f333 Land Cover",
        "title": "STEP 9 — Forest Mask & Land Classification",
        "script": (
            "ESA WorldCover 2021 maps **6,500 km\u00b2** of Guna Division. "
            "**28% Forest Cover** \u2014 182,000 hectares of Tree Cover. "
            "55% is Cropland, 5% Scrubland. "
            "This forest mask is critical: it **filters out crop burns**, ensuring only true forest fires "
            "trigger alerts. Without it, ~55% of detections would be false positives."
        ),
        "highlight": "The forest mask is the secret to zero false-alarm forest fire detection.",
    },
]

if "demo_active" not in st.session_state:
    st.session_state["demo_active"] = False
if "demo_step" not in st.session_state:
    st.session_state["demo_step"] = 0


def _md_bold_to_html(text: str) -> str:
    """Convert **bold** markdown to <strong> HTML tags."""
    import re
    return re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#f97316">\1</strong>', text)


def demo_narration_banner():
    """Render the demo narration panel at the top of the page when demo is active."""
    if not st.session_state.get("demo_active"):
        return
    step = st.session_state["demo_step"]
    info = DEMO_STEPS[step]
    total = len(DEMO_STEPS)

    st.markdown(f"""
    <div style="background:linear-gradient(135deg, rgba(249,115,22,0.15) 0%, rgba(220,38,38,0.10) 100%);
         border:1px solid rgba(249,115,22,0.4); border-radius:12px; padding:20px 24px; margin-bottom:16px;
         position:relative; overflow:hidden;">
        <div style="position:absolute; top:0; left:0; height:3px; background:linear-gradient(90deg, #f97316, #dc2626);
             width:{((step + 1) / total) * 100:.0f}%;"></div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-size:0.65rem; color:#f97316; font-weight:700; letter-spacing:2px; text-transform:uppercase;">
                LIVE DEMO &bull; {info['title']}</span>
            <span style="font-size:0.6rem; color:#8b949e;">{step + 1} / {total}</span>
        </div>
        <div style="font-size:0.85rem; color:#e6edf3; line-height:1.6; margin-bottom:10px;">
            {_md_bold_to_html(info['script'])}</div>
        <div style="font-size:0.7rem; color:#3b82f6; font-style:italic;">
            {info['highlight']}</div>
    </div>""", unsafe_allow_html=True)

    nav_left, nav_mid, nav_right = st.columns([1, 3, 1])
    with nav_left:
        if step > 0:
            if st.button("\u25c0 Previous", key="demo_prev", use_container_width=True):
                st.session_state["demo_step"] = step - 1
                st.rerun()
    with nav_right:
        if step < total - 1:
            if st.button("Next \u25b6", key="demo_next", use_container_width=True):
                st.session_state["demo_step"] = step + 1
                st.rerun()
        else:
            if st.button("End Demo", key="demo_end", use_container_width=True):
                st.session_state["demo_active"] = False
                st.session_state["demo_step"] = 0
                st.rerun()

# ── Command Horizon Dark Theme ───────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-card: #1c2333;
    --bg-card-hover: #222d3f;
    --border: rgba(255,255,255,0.06);
    --border-accent: rgba(255,255,255,0.1);
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #484f58;
    --amber: #f97316;
    --red: #ef4444;
    --blue: #3b82f6;
    --green: #22c55e;
    --teal: #14b8a6;
}

[data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ── Fullscreen layout — remove vertical padding ── */
[data-testid="stAppViewBlockContainer"] {
    background: var(--bg-primary) !important;
    padding-top: 1rem !important;
    padding-bottom: 0 !important;
    max-width: 100% !important;
}
[data-testid="stAppViewContainer"] > section > div,
[data-testid="stMain"] > div { background: var(--bg-primary) !important; }
.block-container { padding-top: 1rem !important; padding-bottom: 0 !important; max-width: 100% !important; }
header[data-testid="stHeader"] { background: var(--bg-primary) !important; border-bottom: 1px solid var(--border); }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a0f1a 0%, #111827 60%, #0d1117 100%) !important;
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] * { color: var(--text-primary) !important; }
[data-testid="stSidebar"] .stRadio label {
    padding: 10px 14px; border-radius: 8px; transition: all 0.2s; margin-bottom: 2px;
    border: 1px solid transparent;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(249,115,22,0.08); border-color: rgba(249,115,22,0.15);
}
[data-testid="stSidebar"] [data-testid="stCaption"] { color: var(--text-muted) !important; }

/* ── Metric cards ── */
.metric-card {
    background: var(--bg-card); border-radius: 10px; padding: 18px 22px;
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent, var(--blue));
    margin-bottom: 10px; transition: all 0.2s ease;
    position: relative; overflow: hidden;
}
.metric-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(249,115,22,0.2), transparent);
}
.metric-card:hover { background: var(--bg-card-hover); transform: translateY(-1px); }
.metric-card .label {
    font-size: 11px; font-weight: 600; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px;
}
.metric-card .value {
    font-size: 26px; font-weight: 700; color: var(--accent, var(--amber));
    font-family: 'JetBrains Mono', monospace; line-height: 1.2;
}
.metric-card .sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

/* ── Headers ── */
h2 {
    color: var(--text-primary) !important; font-weight: 700 !important;
    letter-spacing: -0.02em; padding-bottom: 10px;
    border-bottom: 1px solid var(--border); margin-bottom: 24px !important;
}
h3 { color: var(--text-secondary) !important; font-weight: 600 !important; }

/* ── Status banner ── */
.status-banner {
    border-radius: 10px; padding: 20px 28px; color: white;
    font-weight: 700; font-size: 22px; letter-spacing: 0.5px;
    box-shadow: 0 0 30px rgba(0,0,0,0.3);
    position: relative; overflow: hidden;
}
.status-banner::after {
    content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, transparent 50%);
    pointer-events: none;
}
.status-banner .subtitle { font-size: 13px; font-weight: 400; opacity: 0.85; margin-top: 6px; }

/* ── Meta panel ── */
.meta-panel {
    background: var(--bg-card); border-radius: 10px; padding: 14px 16px;
    border: 1px solid var(--border); font-size: 13px; color: var(--text-secondary);
}
.meta-panel strong { color: var(--text-primary); }

/* ── Empty state ── */
.empty-state {
    text-align: center; padding: 60px 40px; background: var(--bg-secondary);
    border-radius: 12px; border: 1px dashed rgba(255,255,255,0.1); margin: 20px 0;
}
.empty-state .icon { font-size: 48px; margin-bottom: 16px; opacity: 0.7; }
.empty-state .title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.empty-state .desc {
    font-size: 14px; color: var(--text-secondary); max-width: 500px; margin: 0 auto; line-height: 1.6;
}
.empty-state code {
    background: rgba(249,115,22,0.1); padding: 2px 8px; border-radius: 4px;
    font-size: 13px; color: var(--amber); font-family: 'JetBrains Mono', monospace;
}

/* ── Plotly containers ── */
[data-testid="stPlotlyChart"] {
    background: var(--bg-card); border-radius: 10px; padding: 8px;
    border: 1px solid var(--border); margin-bottom: 16px;
}

/* ── Data frames & tables ── */
[data-testid="stDataFrame"],
[data-testid="stTable"] { border-radius: 10px; overflow: hidden; }

/* ── Buttons ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #f97316 0%, #ea580c 100%) !important;
    border: none !important; border-radius: 8px !important; font-weight: 600 !important;
    color: white !important;
    box-shadow: 0 0 20px rgba(249,115,22,0.25); transition: all 0.2s;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 0 30px rgba(249,115,22,0.4); transform: translateY(-1px);
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
}
[data-testid="stExpander"] summary span { color: var(--text-primary) !important; }

/* ── Selectbox / multiselect / date input ── */
[data-testid="stMultiSelect"], [data-testid="stSelectbox"], [data-testid="stDateInput"] {
    color: var(--text-primary);
}

/* ── Map container ── */
[data-testid="stDeckGlJsonChart"] {
    border-radius: 10px; overflow: hidden; border: 1px solid var(--border);
}

/* ── Alerts ── */
[data-testid="stAlert"] { border-radius: 10px; }

/* ── Misc ── */
hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
#MainMenu {visibility: hidden;} footer {visibility: hidden;}
[data-testid="stDeployButton"] { display: none; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--text-muted); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }
</style>
""", unsafe_allow_html=True)

# ── Colour palette ────────────────────────────────────────────────────────────
SEV_COLORS = {
    "CRITICAL": "#d73027",
    "HIGH":     "#f46d43",
    "MODERATE": "#fdae61",
    "LOW":      "#74c476",
    "WATCH":    "#4393c3",
    "CLEAR":    "#c7e9c0",
}
FWI_COLORS = {
    "Extreme":   "#d73027",
    "Very High": "#f46d43",
    "High":      "#fdae61",
    "Moderate":  "#a6d96a",
    "Low":       "#1a9641",
}

# ─────────────────────────────────────────────────────────────────────────────
# Data loaders (cached)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_latest_alert() -> dict:
    p = ALERT_DIR / "latest_alert.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300)
def load_alert_for_date(d: date) -> dict:
    p = ALERT_DIR / f"{d}_alert.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=600)
def load_fwi() -> pd.DataFrame:
    if not FWI_PATH.exists():
        return pd.DataFrame()
    df = pd.read_parquet(FWI_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=600)
def load_firms_all() -> pd.DataFrame:
    """Load all FIRMS fire detections — annual parquets + NRT CSVs merged."""
    frames = []

    # Annual parquet files (historical)
    for pq in sorted(FIRMS_SP.glob("viirs_snpp_sp_*_annual.parquet")):
        frames.append(pd.read_parquet(pq))

    # NRT daily CSVs (recent — always include alongside historical)
    if FIRMS_NRT.exists():
        for csv in sorted(FIRMS_NRT.glob("viirs_nrt_*.csv")):
            try:
                chunk = pd.read_csv(csv)
                if not chunk.empty:
                    frames.append(chunk)
            except Exception:
                continue

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    
    # ── Clip to Guna AOI ──
    lon_min, lat_min, lon_max, lat_max = GUNA_BBOX
    df = df[
        (df["longitude"] >= lon_min) & (df["longitude"] <= lon_max) &
        (df["latitude"]  >= lat_min) & (df["latitude"]  <= lat_max)
    ]

    # Normalise column names (parquets have 'instrument', CSVs may not)
    if "frp" not in df.columns and "FRP" in df.columns:
        df.rename(columns={"FRP": "frp"}, inplace=True)
    # Deduplicate: same lat/lon/date/time → keep first
    dedup_cols = [c for c in ["latitude", "longitude", "acq_date", "acq_time"] if c in df.columns]
    if dedup_cols:
        df = df.drop_duplicates(subset=dedup_cols, keep="first")
    return df.sort_values("acq_date").reset_index(drop=True)


@st.cache_data(ttl=600)
def load_fire_links() -> pd.DataFrame:
    if not LINKS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(LINKS_CSV, parse_dates=["scene_date", "fire_date"])
    return df


@st.cache_data(ttl=3600)
def load_lc_stats() -> dict:
    if not LC_STATS.exists():
        return {}
    with open(LC_STATS) as f:
        return json.load(f)


@st.cache_data(ttl=3600)
def load_terrain_stats() -> dict:
    p = TERRAIN_DIR / "terrain_stats.json"
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)


@st.cache_data(ttl=3600)
def load_boundary_geojson() -> dict:
    """Load Guna district beat-level GeoJSON boundary."""
    p = BOUND_DIR / "guna_district.geojson"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=600)
def load_gfs_forecast(target_date) -> pd.DataFrame:
    """
    Load GFS fire-weather forecast for *target_date* from data_lake/weather/gfs_0p25/.
    Averages variables spatially over the Guna bbox.
    Returns DataFrame with columns: lead_h, temp_c, rh_pct, wind_kmh, precip_mm.
    """
    # Check both possible directory structures
    date_dir = WEATHER_DIR / str(target_date.year) / f"{target_date.month:02d}" / f"{target_date.day:02d}"
    if not date_dir.exists():
        date_dir = WEATHER_DIR / f"{target_date}"
    if not date_dir.exists():
        return pd.DataFrame()

    rows = []
    try:
        import xarray as xr
        min_lon, min_lat, max_lon, max_lat = GUNA_BBOX
        for nc in sorted(date_dir.glob("gfs_f*.nc")):
            lead = int(nc.stem.replace("gfs_f", ""))
            try:
                ds = xr.open_dataset(nc)
                # Subset to Guna bbox (latitude may be descending in GFS)
                try:
                    ds_s = ds.sel(
                        latitude=slice(max_lat, min_lat),
                        longitude=slice(min_lon, max_lon),
                    )
                except Exception:
                    ds_s = ds  # fallback: global mean

                row = {"lead_h": lead}
                # Temperature
                for vname in ("t2m", "TMP_2maboveground"):
                    if vname in ds_s:
                        row["temp_c"] = float(ds_s[vname].mean().values) - 273.15
                        break
                # Relative humidity
                for vname in ("r2", "RH_2maboveground"):
                    if vname in ds_s:
                        row["rh_pct"] = float(ds_s[vname].mean().values)
                        break
                # Wind speed (derived or component)
                if "wind_speed_10m" in ds_s:
                    row["wind_kmh"] = float(ds_s["wind_speed_10m"].mean().values) * 3.6
                elif "u10" in ds_s and "v10" in ds_s:
                    ws = (ds_s["u10"]**2 + ds_s["v10"]**2) ** 0.5
                    row["wind_kmh"] = float(ws.mean().values) * 3.6
                # Precipitation
                for vname in ("tp", "APCP_surface"):
                    if vname in ds_s:
                        prec_raw = float(ds_s[vname].mean().values)
                        # Convert m -> mm if unit tag says metres
                        units = ds_s[vname].attrs.get("units", "")
                        row["precip_mm"] = prec_raw * 1000 if units.startswith("m") else prec_raw
                        break
                ds.close()
                rows.append(row)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Ignored exception: {e}")
    except ImportError:
        pass

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("lead_h").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helper widgets
# ─────────────────────────────────────────────────────────────────────────────

def sev_badge(sev: str) -> str:
    color = SEV_COLORS.get(sev, "#888")
    return (f'<span style="background:{color};color:white;padding:4px 12px;border-radius:4px;'
            f'font-weight:700;font-size:12px;letter-spacing:0.5px;'
            f'box-shadow:0 0 12px {color}40;text-transform:uppercase">{sev}</span>')


def fwi_color(val: float) -> str:
    if val >= 38:   return "#d73027"
    if val >= 21.3: return "#f46d43"
    if val >= 11.2: return "#fdae61"
    if val >= 5:    return "#a6d96a"
    return "#1a9641"


def metric_card(label: str, value, sub: str = "", color: str = "#3b82f6", icon: str = ""):
    icon_html = f'<span style="font-size:18px;margin-right:4px">{icon}</span>' if icon else ""
    st.markdown(
        f"""<div class="metric-card" style="--accent:{color}">
            <div class="label">{icon_html}{label}</div>
            <div class="value">{value}</div>
            <div class="sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def empty_state(icon: str, title: str, description: str):
    st.markdown(
        f"""<div class="empty-state">
            <div class="icon">{icon}</div>
            <div class="title">{title}</div>
            <div class="desc">{description}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def fullscreen_map_button(deck: "pdk.Deck", map_id: str):
    """Offer a download button for a standalone HTML version of a pydeck map."""
    try:
        html_str = deck.to_html(as_string=True)
        st.download_button(
            "\U0001f5fa\ufe0f Open Map Fullscreen",
            data=html_str,
            file_name=f"van_suraksha_{map_id}.html",
            mime="text/html",
            key=f"dl_map_{map_id}",
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        """<div style="text-align:center;padding:16px 0 8px">
        <div style="width:56px;height:56px;margin:0 auto 8px;border-radius:12px;
             background:linear-gradient(135deg,#f97316 0%,#dc2626 100%);
             display:flex;align-items:center;justify-content:center;
             box-shadow:0 0 24px rgba(249,115,22,0.3)">
            <span style="font-size:28px;line-height:1">🔥</span>
        </div>
        <h1 style="margin:0;font-size:22px;font-weight:700;letter-spacing:1px;
            color:#e6edf3;text-transform:uppercase">Van Suraksha</h1>
        <p style="font-size:10px;color:#8b949e;margin:4px 0 0;letter-spacing:1.5px;
            text-transform:uppercase">\U0001f6e1\ufe0f Command Horizon &bull; Guna Division \U0001f30d</p>
        </div>""",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Live Demo Toggle ──
    demo_col1, demo_col2 = st.columns([1, 1])
    with demo_col1:
        if st.button(
            "STOP DEMO" if st.session_state.get("demo_active") else "LIVE DEMO",
            key="demo_toggle",
            use_container_width=True,
            type="primary" if st.session_state.get("demo_active") else "secondary",
        ):
            st.session_state["demo_active"] = not st.session_state.get("demo_active", False)
            st.session_state["demo_step"] = 0
            st.rerun()
    with demo_col2:
        if st.session_state.get("demo_active"):
            step_i = st.session_state["demo_step"]
            st.caption(f"Step {step_i + 1}/{len(DEMO_STEPS)}")

    tab_names = [
        "\U0001f6a8 Live Alert",
        "\U0001f310 3D Digital Twin",
        "\U0001f4ca Fire History",
        "\U0001f6f0\ufe0f Burn Scars",
        "\U0001f321\ufe0f FWI Trends",
        "\u26f0\ufe0f Weather & Terrain",
        "\U0001f333 Land Cover",
        "\U0001f9ea Ignition ABM",
    ]

    # If demo is active, force-select the tab for the current demo step
    # Must set session_state BEFORE widget renders (index param is ignored if key exists)
    if st.session_state.get("demo_active"):
        _demo_tab = DEMO_STEPS[st.session_state["demo_step"]]["tab"]
        st.session_state["nav_radio"] = _demo_tab

    selected_tab = st.radio("Navigation", tab_names, label_visibility="collapsed", key="nav_radio")

# ── AI Guardian Chat ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("🤖 AI Guardian Chat")
    
    if ForestChatEngine:
        chat_engine = ForestChatEngine()
        
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("Ask about the forest..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            response = chat_engine.ask(prompt)
            st.session_state.messages.append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)
    else:
        st.error("ForestChatEngine not loaded. Check project paths.")

    # ── Path Diagnostic (Expandable) ──
    with st.expander("🛠️ System Diagnostics"):
        st.write(f"**ROOT:** `{ROOT}`")
        st.write(f"**Python:** `{sys.version.split()[0]}`")
        if st.checkbox("Show sys.path"):
            st.write(sys.path)

    st.divider()
    st.caption("FIRMS VIIRS SNPP | NASA POWER | ESA WorldCover 2021 | IBM-NASA Prithvi-EO-2.0")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: 3D Digital Twin
# ─────────────────────────────────────────────────────────────────────────────

if selected_tab == "\U0001f310 3D Digital Twin":
    # Fullscreen CSS — hide Streamlit padding, make map fill viewport
    st.markdown("""<style>
    .block-container { padding: 0 !important; max-width: 100% !important; }
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stBottom"] { display: none !important; }
    footer { display: none !important; }
    iframe { border: none !important; }
    </style>""", unsafe_allow_html=True)

    # Date picker in sidebar — find latest alert with fires as default
    _default_sim = date.today()
    for _af in sorted(ALERT_DIR.glob("*_alert.json"), reverse=True):
        try:
            _ad = json.loads(_af.read_text(encoding="utf-8"))
            if _ad.get("fires"):
                _default_sim = date.fromisoformat(_af.stem.replace("_alert", ""))
                break
        except Exception:
            continue
    with st.sidebar:
        # Demo narration for 3D tab (fullscreen, so banner goes in sidebar)
        if st.session_state.get("demo_active"):
            step_info = DEMO_STEPS[st.session_state["demo_step"]]
            st.markdown(f"""<div style="background:rgba(249,115,22,0.12); border:1px solid rgba(249,115,22,0.3);
                border-radius:8px; padding:12px; margin-bottom:12px; font-size:0.75rem; color:#e6edf3; line-height:1.5;">
                <div style="color:#f97316; font-weight:700; font-size:0.6rem; letter-spacing:1.5px; margin-bottom:6px;">
                    {step_info['title']}</div>
                {_md_bold_to_html(step_info['script'])}
                <div style="color:#3b82f6; font-style:italic; margin-top:6px; font-size:0.65rem;">
                    {step_info['highlight']}</div>
            </div>""", unsafe_allow_html=True)
            nav_l, nav_r = st.columns(2)
            with nav_l:
                if st.session_state["demo_step"] > 0:
                    if st.button("\u25c0 Prev", key="demo_prev_3d"):
                        st.session_state["demo_step"] -= 1
                        st.rerun()
            with nav_r:
                if st.session_state["demo_step"] < len(DEMO_STEPS) - 1:
                    if st.button("Next \u25b6", key="demo_next_3d"):
                        st.session_state["demo_step"] += 1
                        st.rerun()
        st.markdown("**Simulation**")
        sim_date = st.date_input(
            "Date", value=_default_sim,
            min_value=date(2013, 1, 1), max_value=date.today(), key="sim_date",
        )
        st.caption("Muhurta-2D PDE Engine")

    sim_alert = load_alert_for_date(sim_date)
    fire_points_js = "[]"
    sim_ros = 5.0
    sim_intensity = 500.0
    sim_wind_speed = 10.0
    sim_wind_dir = 225.0
    sim_center_lat = 24.640
    sim_center_lon = 77.320
    sim_frp = 0.0
    sim_sev = "CLEAR"
    sim_fwi_val = 0.0
    sim_n_fires = 0
    sim_danger = "—"
    sim_temp = 0.0
    sim_rh = 0.0
    sim_ffmc = 0.0
    sim_dmc = 0.0
    sim_dc = 0.0
    sim_isi = 0.0
    sim_bui = 0.0

    if sim_alert and sim_alert.get("fires"):
        fires = sim_alert["fires"]
        sim_n_fires = len(fires)
        fdata = []
        for f in fires:
            pm = f.get("prescriptive_metrics", {})
            fdata.append({
                "lat": f["fire_lat"], "lon": f["fire_lon"],
                "frp": f.get("frp_mw", 10), "severity": f.get("severity", "HIGH"),
                "category": f.get("frp_category", ""),
                "ros": pm.get("ros_m_min", 5.0) if pm else 5.0,
                "intensity": pm.get("intensity_kw_m", 500.0) if pm else 500.0,
            })
        fire_points_js = json.dumps(fdata)
        sim_center_lat = fires[0]["fire_lat"]
        sim_center_lon = fires[0]["fire_lon"]
        pm0 = fires[0].get("prescriptive_metrics", {})
        if pm0:
            sim_ros = pm0.get("ros_m_min", 5.0)
            sim_intensity = pm0.get("intensity_kw_m", 500.0)
        fwi_d = sim_alert.get("fwi", {})
        sim_wind_speed = fwi_d.get("wind_kmh", 10.0)
        sim_frp = sim_alert.get("peak_frp_mw", 0)
        sim_sev = sim_alert.get("bulletin_severity", "CLEAR")
        sim_fwi_val = fwi_d.get("value", 0)
        sim_danger = fwi_d.get("danger_class", "—")
        sim_temp = fwi_d.get("temp_c", 0)
        sim_rh = fwi_d.get("rh_pct", 0)
        sim_ffmc = fwi_d.get("ffmc", 0)
        sim_dmc = fwi_d.get("dmc", 0)
        sim_dc = fwi_d.get("dc", 0)
        sim_isi = fwi_d.get("isi", 0)
        sim_bui = fwi_d.get("bui", 0)

    # ── 3D Forest Canopy — load 747 compartment polygons ──
    _comp_path = ROOT / "data" / "aoi" / "gunafinal.geojson"
    compartments_js = "[]"
    _n_compartments = 0
    if _comp_path.exists():
        _gj = json.loads(_comp_path.read_text(encoding="utf-8"))
        _comp_list = []
        for feat in _gj.get("features", []):
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            if geom.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            coords_raw = geom["coordinates"]
            if geom["type"] == "MultiPolygon":
                coords_raw = coords_raw[0]
            ring = coords_raw[0]
            # Downsample large rings (keep every Nth point) + round to 4 decimals
            step = max(1, len(ring) // 30)
            sampled = ring[::step]
            if sampled[-1] != ring[-1]:
                sampled.append(ring[-1])  # close ring
            flat = []
            for pt in sampled:
                flat.extend([round(pt[0], 4), round(pt[1], 4)])
            area2015 = float(props.get("area2015", 0) or 0)
            area_orig = float(props.get("areaOrigin", 0) or 0)
            health = (area2015 / area_orig) if area_orig > 0 else 1.0
            if health >= 0.8:
                color = "#22c55e"
            elif health >= 0.6:
                color = "#eab308"
            elif health >= 0.4:
                color = "#f97316"
            else:
                color = "#ef4444"
            # Compute centroid for tree placement
            lons = [pt[0] for pt in sampled]
            lats = [pt[1] for pt in sampled]
            cx = round(sum(lons) / len(lons), 4)
            cy = round(sum(lats) / len(lats), 4)
            _comp_list.append({
                "c": flat,
                "h": max(area2015 * 0.5, 50),
                "cl": color,
                "b": props.get("BEAT", ""),
                "r": props.get("RANGE", ""),
                "a": area2015,
                "ao": area_orig,
                "hl": round(health, 3),
                "f": 0,
                "cx": cx, "cy": cy,
                "sl": 0.0, "asp": 0.0, "el": 0.0,
                "lt": 0, "ls": 0, "lg": 0, "lc": 0, "lb": 0, "lw": 0,
            })
        # Count FIRMS fires per compartment (bbox approximation)
        try:
            _firms_df = load_firms_all()
            if not _firms_df.empty:
                _flons = _firms_df["longitude"].values
                _flats = _firms_df["latitude"].values
                for comp in _comp_list:
                    _rlons = comp["c"][0::2]
                    _rlats = comp["c"][1::2]
                    lo0, lo1 = min(_rlons), max(_rlons)
                    la0, la1 = min(_rlats), max(_rlats)
                    comp["f"] = int((
                        (_flons >= lo0) & (_flons <= lo1) &
                        (_flats >= la0) & (_flats <= la1)
                    ).sum())
        except Exception:
            pass
        # Load precomputed terrain stats (slope, aspect, elevation)
        _terrain_path = ROOT / "data" / "aoi" / "compartment_terrain.json"
        if _terrain_path.exists():
            _terr = json.loads(_terrain_path.read_text(encoding="utf-8"))
            for i, comp in enumerate(_comp_list):
                t = _terr.get(str(i), {})
                comp["sl"] = t.get("slope", 0.0)
                comp["asp"] = t.get("aspect", 0.0)
                comp["el"] = t.get("elev", 0.0)
        # Load precomputed LULC breakdown per compartment
        _lulc_path = ROOT / "data" / "aoi" / "compartment_lulc.json"
        if _lulc_path.exists():
            _lulc = json.loads(_lulc_path.read_text(encoding="utf-8"))
            for i, comp in enumerate(_comp_list):
                lc = _lulc.get(str(i), {})
                comp["lt"] = lc.get("tree", 0)    # % tree
                comp["ls"] = lc.get("shrub", 0)   # % shrub
                comp["lg"] = lc.get("grass", 0)   # % grass
                comp["lc"] = lc.get("crop", 0)    # % crop
                comp["lb"] = lc.get("built", 0)   # % built
                comp["lw"] = lc.get("water", 0)   # % water
        _n_compartments = len(_comp_list)
        compartments_js = json.dumps(_comp_list, separators=(",", ":"))

    # ── FIRMS Fire History (date-filtered, max 2000 by FRP) ──
    firms_js = "[]"
    try:
        _firms_all = load_firms_all()
        if not _firms_all.empty:
            _yr_ago = str(sim_date - timedelta(days=365))
            _today_s = str(sim_date)
            _firms_rng = _firms_all[
                (_firms_all["acq_date"].astype(str) >= _yr_ago)
                & (_firms_all["acq_date"].astype(str) <= _today_s)
            ]
            if len(_firms_rng) > 2000:
                _firms_rng = _firms_rng.nlargest(2000, "frp")
            firms_js = json.dumps([
                {"la": round(float(r.latitude), 4), "lo": round(float(r.longitude), 4),
                 "f": round(float(r.frp), 1) if pd.notna(r.frp) else 0,
                 "d": str(r.acq_date)[:10],
                 "c": str(getattr(r, 'confidence', 'nominal')).lower()}
                for r in _firms_rng.itertuples()
            ], separators=(',', ':'))
    except Exception:
        pass

    # ── Burn Scars ──
    burns_js = "[]"
    try:
        _burns_df = load_fire_links()
        if not _burns_df.empty:
            burns_js = json.dumps([
                {"la": round(float(r.fire_lat), 4), "lo": round(float(r.fire_lon), 4),
                 "a": round(float(r.burn_area_ha), 1),
                 "c": str(r.confidence),
                 "sd": str(r.scene_date)[:10], "fd": str(r.fire_date)[:10]}
                for r in _burns_df.itertuples() if pd.notna(r.fire_lat)
            ], separators=(',', ':'))
    except Exception:
        pass

    # ── Predictive Risk Grid (601 cells → small rectangles from centroids) ──
    pred_js = "[]"
    _pred_path = ROOT / "outputs" / "dashboard_feed" / "unified_alert.geojson"
    if _pred_path.exists():
        try:
            with open(_pred_path, encoding="utf-8") as _pf:
                _pred_gj = json.load(_pf)
            _pred_cells = []
            _cell_half = 0.015  # ~1.5 km half-width
            for feat in _pred_gj.get("features", []):
                props = feat.get("properties", {})
                coords = feat["geometry"]["coordinates"]
                clon, clat = coords[0], coords[1]
                # Build rectangle corners [lon,lat, lon,lat, ...]
                _rect = [
                    round(clon - _cell_half, 4), round(clat - _cell_half, 4),
                    round(clon + _cell_half, 4), round(clat - _cell_half, 4),
                    round(clon + _cell_half, 4), round(clat + _cell_half, 4),
                    round(clon - _cell_half, 4), round(clat + _cell_half, 4),
                ]
                _pred_cells.append({
                    "c": _rect,
                    "s": round(props.get("risk_score", 0), 2),
                    "l": props.get("risk_level", "LOW"),
                    "b": props.get("beat", ""),
                    "r": props.get("range", ""),
                })
            pred_js = json.dumps(_pred_cells, separators=(',', ':'))
        except Exception:
            pass

    _n_firms = firms_js.count('"la"')
    _n_burns = burns_js.count('"la"')
    _n_pred = pred_js.count('"c"')

    # Serve overlay PNGs via HTTP (start once)
    if "overlay_server" not in st.session_state:
        import threading, http.server, functools
        _static_dir = str(ROOT / "dashboard" / "static")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=_static_dir)
        _srv = http.server.HTTPServer(("127.0.0.1", 8777), handler)
        _srv.timeout = 0.1
        _t = threading.Thread(target=_srv.serve_forever, daemon=True)
        _t.start()
        st.session_state["overlay_server"] = True
    _overlay_base = "http://127.0.0.1:8777"
    # Load overlay bounds
    _ov_bounds_path = ROOT / "dashboard" / "static" / "overlay_bounds.json"
    _ov_bounds = json.loads(_ov_bounds_path.read_text(encoding="utf-8")) if _ov_bounds_path.exists() else {}

    # Define the Cesium HTML component with built-in fire spread simulation
    cesium_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <script src="https://unpkg.com/cesium@1.95.0/Build/Cesium/Cesium.js"></script>
        <link href="https://unpkg.com/cesium@1.95.0/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
        <style>
            body {{ margin: 0; padding: 0; overflow: hidden; background: #0a0a0a; font-family: 'Segoe UI', system-ui, sans-serif; }}
            #cesiumContainer {{ width: 100%; height: 100%; position: absolute; top: 0; left: 0; }}

            /* ── Animations ── */
            @keyframes pls {{ 0%,100%{{ opacity:1; }} 50%{{ opacity:0.7; }} }}
            @keyframes pulse-ring {{ 0%{{ transform:scale(1); opacity:0.8; }} 100%{{ transform:scale(2.5); opacity:0; }} }}
            @keyframes glow {{ 0%,100%{{ box-shadow: 0 0 8px rgba(239,68,68,0.4); }} 50%{{ box-shadow: 0 0 20px rgba(239,68,68,0.8); }} }}

            /* ── Glassmorphism base ── */
            .glass {{
                background: rgba(15,23,42,0.85); backdrop-filter: blur(12px);
                border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.4); color: #e6edf3;
            }}

            /* ── Layer Control Panel (left) ── */
            #layerPanel {{
                position: absolute; top: 60px; left: 16px; z-index: 1000;
                width: 240px; padding: 14px; max-height: calc(100vh - 120px); overflow-y: auto;
            }}
            #layerPanel::-webkit-scrollbar {{ width: 4px; }}
            #layerPanel::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.15); border-radius: 2px; }}
            .panel-title {{
                font-size: 0.6rem; font-weight: 800; color: #f97316;
                letter-spacing: 2px; text-transform: uppercase; margin-bottom: 10px;
            }}
            .layer-row {{
                display: flex; align-items: center; gap: 8px; padding: 5px 6px;
                border-radius: 6px; cursor: pointer; transition: background 0.15s;
                font-size: 0.68rem; margin-bottom: 2px;
            }}
            .layer-row:hover {{ background: rgba(255,255,255,0.06); }}
            .layer-row input[type="checkbox"] {{
                accent-color: #f97316; width: 14px; height: 14px; cursor: pointer; flex-shrink: 0;
            }}
            .layer-icon {{ font-size: 0.85rem; flex-shrink: 0; }}
            .layer-label {{ flex: 1; }}
            .layer-count {{
                font-size: 0.55rem; background: rgba(255,255,255,0.08); padding: 1px 6px;
                border-radius: 10px; color: #8b949e;
            }}
            .panel-sep {{ border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 8px 0; }}

            /* FWI badge in layer panel */
            .fwi-badge {{
                display: flex; align-items: center; gap: 8px; padding: 8px 10px;
                border-radius: 8px; margin-bottom: 6px;
            }}
            .fwi-badge-val {{ font-size: 1.2rem; font-weight: 800; }}
            .fwi-badge-label {{ font-size: 0.55rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }}
            .wx-row {{ display: flex; justify-content: space-between; font-size: 0.65rem; margin-bottom: 3px; }}
            .wx-lbl {{ color: #8b949e; }}
            .wx-val {{ font-weight: 600; }}

            /* Simulation buttons */
            .sim-section {{ margin-top: 4px; }}
            .b {{
                display: block; width: 100%; background: rgba(255,255,255,0.06); color: #c9d1d9;
                border: 1px solid rgba(255,255,255,0.1); padding: 7px 4px;
                border-radius: 6px; cursor: pointer; font-size: 0.62rem;
                font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
                transition: all 0.2s; text-align: center; margin-bottom: 3px;
            }}
            .brow {{ display: flex; gap: 4px; }}
            .brow .b {{ margin-bottom: 0; }}
            .b:hover {{ background: rgba(255,255,255,0.12); }}
            .b.active {{ background: rgba(239,68,68,0.3); border-color: #ef4444; color: #ef4444; }}
            .b.running {{ background: rgba(239,68,68,0.8); border-color: #ef4444; color: #fff; animation: pls 1.5s infinite; }}

            /* ── Fire Metrics (right) ── */
            #fmet {{
                position: absolute; top: 60px; right: 16px;
                padding: 14px; width: 200px; z-index: 1000; display: none;
                border-color: rgba(239,68,68,0.3);
            }}
            #fmet h4 {{ margin: 0 0 8px; font-size: 0.65rem; color: #ef4444; letter-spacing: 1.5px; text-transform: uppercase; }}
            .mv {{ text-align: center; margin-bottom: 5px; }}
            .mvn {{ font-size: 1.3rem; font-weight: 800; color: #f97316; }}
            .mvl {{ font-size: 0.55rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }}
            .hr {{ display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 0.72rem; }}
            .hl {{ color: #8b949e; }}
            .hv {{ font-weight: 600; color: #3b82f6; }}
            .hv.red {{ color: #ef4444; }}
            .hv.amber {{ color: #f59e0b; }}
            .hv.green {{ color: #22c55e; }}

            /* ── Status bar (bottom center) ── */
            #sbar {{
                position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
                padding: 6px 20px; font-size: 0.62rem; z-index: 1000; white-space: nowrap;
                border-radius: 20px;
            }}
            .sd {{ display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }}
            .sd.g {{ background: #22c55e; }}
            .sd.r {{ background: #ef4444; animation: pls 1s infinite; }}

            /* ── Top command bar ── */
            #topbar {{
                position: absolute; top: 0; left: 0; right: 0; z-index: 1001;
                background: linear-gradient(180deg, rgba(10,10,15,0.95) 0%, rgba(10,10,15,0.6) 80%, transparent 100%);
                padding: 10px 20px 24px; display: flex; align-items: center; gap: 16px;
            }}
            #topbar .logo {{ font-size: 0.75rem; font-weight: 800; color: #f97316; letter-spacing: 2px; text-transform: uppercase; white-space: nowrap; }}
            #topbar .sep {{ width: 1px; height: 20px; background: rgba(255,255,255,0.15); }}
            .idx {{
                background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px; padding: 4px 10px; text-align: center; min-width: 70px;
            }}
            .idx .iv {{ font-size: 1rem; font-weight: 800; line-height: 1.2; }}
            .idx .il {{ font-size: 0.5rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.8px; }}
            .iv.crit {{ color: #ef4444; }}
            .iv.warn {{ color: #f59e0b; }}
            .iv.info {{ color: #3b82f6; }}
            .iv.ok {{ color: #22c55e; }}

            /* ── Bottom FWI indices strip ── */
            #fwi-strip {{
                position: absolute; bottom: 50px; left: 50%; transform: translateX(-50%);
                z-index: 1000; display: flex; gap: 4px;
            }}
            .fi {{
                border-radius: 6px; padding: 4px 8px; text-align: center; min-width: 44px;
                backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.08);
            }}
            .fi .fv {{ font-size: 0.8rem; font-weight: 700; }}
            .fi .fl {{ font-size: 0.45rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}
            .fi-low {{ background: rgba(34,197,94,0.15); }}
            .fi-low .fv {{ color: #22c55e; }}
            .fi-mod {{ background: rgba(234,179,8,0.15); }}
            .fi-mod .fv {{ color: #eab308; }}
            .fi-high {{ background: rgba(249,115,22,0.15); }}
            .fi-high .fv {{ color: #f97316; }}
            .fi-vhigh {{ background: rgba(239,68,68,0.15); }}
            .fi-vhigh .fv {{ color: #ef4444; }}

            /* ── Legend panel (bottom-right, collapsible) ── */
            #legend-panel {{
                position: absolute; bottom: 50px; right: 16px; z-index: 1000;
                padding: 12px 14px; min-width: 200px; max-height: 340px; overflow-y: auto;
            }}
            #legend-panel::-webkit-scrollbar {{ width: 3px; }}
            #legend-panel::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.15); border-radius: 2px; }}
            .leg-title {{ font-size: 0.58rem; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 5px; }}
            .leg-group {{ margin-bottom: 8px; }}
            .leg-group-label {{ font-size: 0.5rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 3px; }}
            .lg-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 2px; font-size: 0.6rem; }}
            .lg-swatch {{ width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }}
            .lg-circle {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; border: 1px solid rgba(255,255,255,0.2); }}
            .lg-diamond {{ width: 10px; height: 10px; transform: rotate(45deg); flex-shrink: 0; }}
            #legend-toggle {{
                position: absolute; bottom: 50px; right: 16px; z-index: 999;
                width: 32px; height: 32px; border-radius: 8px; cursor: pointer;
                display: flex; align-items: center; justify-content: center;
                font-size: 0.7rem; border: 1px solid rgba(255,255,255,0.1);
                background: rgba(15,23,42,0.85); backdrop-filter: blur(8px); color: #e6edf3;
            }}
        </style>
    </head>
    <body>
        <div id="cesiumContainer"></div>

        <!-- Top command bar with overlapping indices -->
        <div id="topbar">
            <div class="logo">Van Suraksha 3D Command Center</div>
            <div class="sep"></div>
            <div class="idx"><div class="iv crit">{sim_sev}</div><div class="il">Severity</div></div>
            <div class="idx"><div class="iv warn">{sim_frp:.1f}</div><div class="il">FRP (MW)</div></div>
            <div class="idx"><div class="iv crit">{sim_fwi_val:.1f}</div><div class="il">FWI</div></div>
            <div class="idx"><div class="iv info">{sim_wind_speed:.1f}</div><div class="il">Wind km/h</div></div>
            <div class="idx"><div class="iv warn">{sim_temp:.1f}&deg;</div><div class="il">Temp &deg;C</div></div>
            <div class="idx"><div class="iv info">{sim_rh:.1f}%</div><div class="il">Humidity</div></div>
            <div class="idx"><div class="iv crit">{sim_danger}</div><div class="il">Danger</div></div>
            <div class="sep"></div>
            <div class="idx"><div class="iv ok">{sim_n_fires}</div><div class="il">Fires</div></div>
            <div style="margin-left:auto;font-size:0.55rem;color:#8b949e;">{sim_date} &bull; Guna Division, MP</div>
        </div>

        <!-- ═══ Layer Control Panel (left) ═══ -->
        <div id="layerPanel" class="glass">
            <div class="panel-title">Layers</div>

            <label class="layer-row">
                <input type="checkbox" id="chk-nrt" checked onchange="toggleLayerNrt()">
                <span class="layer-icon" style="color:#ef4444;">&#x1f525;</span>
                <span class="layer-label">NRT Fires</span>
                <span class="layer-count" id="cnt-nrt">{sim_n_fires}</span>
            </label>
            <label class="layer-row">
                <input type="checkbox" id="chk-hist" checked onchange="toggleLayerHist()">
                <span class="layer-icon" style="color:#f97316;">&#x1f4cd;</span>
                <span class="layer-label">Fire History</span>
                <span class="layer-count" id="cnt-hist">{_n_firms}</span>
            </label>
            <label class="layer-row">
                <input type="checkbox" id="chk-burn" checked onchange="toggleLayerBurn()">
                <span class="layer-icon" style="color:#dc2626;">&#x1f4a0;</span>
                <span class="layer-label">Burn Scars</span>
                <span class="layer-count" id="cnt-burn">{_n_burns}</span>
            </label>
            <label class="layer-row">
                <input type="checkbox" id="chk-pred" onchange="toggleLayerPred()">
                <span class="layer-icon" style="color:#eab308;">&#x26a0;</span>
                <span class="layer-label">Risk Grid</span>
                <span class="layer-count" id="cnt-pred">{_n_pred}</span>
            </label>
            <label class="layer-row">
                <input type="checkbox" id="chk-forest" checked onchange="toggleForest2()">
                <span class="layer-icon" style="color:#22c55e;">&#x1f333;</span>
                <span class="layer-label">3D Forest</span>
                <span class="layer-count">{_n_compartments}</span>
            </label>
            <label class="layer-row">
                <input type="checkbox" id="chk-lulc" checked onchange="toggleLulc2()">
                <span class="layer-icon" style="color:#84cc16;">&#x1f5fa;</span>
                <span class="layer-label">LULC</span>
            </label>
            <label class="layer-row">
                <input type="checkbox" id="chk-slope" onchange="toggleSlope2()">
                <span class="layer-icon" style="color:#f97316;">&#x26f0;</span>
                <span class="layer-label">Slope</span>
            </label>
            <label class="layer-row">
                <input type="checkbox" id="chk-aspect" onchange="toggleAspect2()">
                <span class="layer-icon" style="color:#3b82f6;">&#x1f9ed;</span>
                <span class="layer-label">Aspect</span>
            </label>

            <hr class="panel-sep">

            <!-- FWI badge -->
            <div class="fwi-badge" style="background:rgba({{"239,68,68" if sim_fwi_val > 30 else "249,115,22" if sim_fwi_val > 15 else "234,179,8" if sim_fwi_val > 5 else "34,197,94"}},0.15);
                border:1px solid rgba({{"239,68,68" if sim_fwi_val > 30 else "249,115,22" if sim_fwi_val > 15 else "234,179,8" if sim_fwi_val > 5 else "34,197,94"}},0.3);">
                <div>
                    <div class="fwi-badge-val" style="color:{{"#ef4444" if sim_fwi_val > 30 else "#f97316" if sim_fwi_val > 15 else "#eab308" if sim_fwi_val > 5 else "#22c55e"}};">{sim_fwi_val:.1f}</div>
                    <div class="fwi-badge-label">FWI &bull; {sim_danger}</div>
                </div>
            </div>
            <div class="wx-row"><span class="wx-lbl">&#x1f321; Temp</span><span class="wx-val" style="color:#f97316;">{sim_temp:.1f}&deg;C</span></div>
            <div class="wx-row"><span class="wx-lbl">&#x1f4a8; Wind</span><span class="wx-val" style="color:#3b82f6;">{sim_wind_speed:.1f} km/h</span></div>
            <div class="wx-row"><span class="wx-lbl">&#x1f4a7; RH</span><span class="wx-val" style="color:#22c55e;">{sim_rh:.1f}%</span></div>

            <hr class="panel-sep">

            <!-- Simulation controls -->
            <div class="sim-section">
                <div style="font-size:0.55rem;color:#8b949e;text-transform:uppercase;letter-spacing:1px;margin-bottom:5px;">Muhurta-2D Simulation</div>
                <div class="hr"><span class="hl">Time</span><span class="hv" id="stime">00:00</span></div>
                <div class="hr"><span class="hl">Intensity</span><span class="hv red" id="intensity-val">-- kW/m</span></div>
                <div class="hr"><span class="hl">Spread</span><span class="hv amber" id="ros-val">-- m/min</span></div>
                <div class="hr"><span class="hl">Flame</span><span class="hv" id="flame-val" style="color:#4ecdc4;">-- m</span></div>
                <div class="hr"><span class="hl">Status</span><span class="hv green" id="sstat">Ready</span></div>
                <div class="hr"><span class="hl">Area</span><span class="hv" id="sarea">0 ha</span></div>
                <div class="hr"><span class="hl">Class</span><span class="hv" id="sfcls">&mdash;</span></div>
                <div class="brow" style="margin-top:6px;">
                    <button class="b" id="simBtn" onclick="toggleSim()">&#x25b6; START</button>
                    <button class="b" id="lnBtn" onclick="setM('FIRELINE')">Fireline</button>
                    <button class="b" id="igBtn" onclick="setM('BACKFIRE')">Ignite</button>
                </div>
                <button class="b" onclick="resetSim()">&#x21ba; Reset</button>
            </div>
        </div>

        <!-- ═══ Fire Behavior Metrics (right, shown during sim) ═══ -->
        <div id="fmet" class="glass">
            <h4>Fire Behavior</h4>
            <div class="mv"><div class="mvn" id="mRos">{sim_ros:.1f}</div><div class="mvl">Rate of Spread (m/min)</div></div>
            <div class="mv"><div class="mvn" id="mInt">{sim_intensity:.0f}</div><div class="mvl">Byram Intensity (kW/m)</div></div>
            <div class="mv"><div class="mvn" id="mWnd">{sim_wind_speed:.1f}</div><div class="mvl">Wind Speed (km/h)</div></div>
            <hr class="panel-sep">
            <div class="hr"><span class="hl">FWI</span><span class="hv red">{sim_fwi_val:.1f}</span></div>
            <div class="hr"><span class="hl">Mode</span><span class="hv red">Defensive</span></div>
        </div>

        <!-- ═══ FWI Indices Strip (bottom center) ═══ -->
        <div id="fwi-strip">
            <div class="fi {"fi-vhigh" if sim_ffmc > 90 else "fi-high" if sim_ffmc > 84 else "fi-mod" if sim_ffmc > 70 else "fi-low"}"><div class="fv">{sim_ffmc:.1f}</div><div class="fl">FFMC</div></div>
            <div class="fi {"fi-vhigh" if sim_dmc > 60 else "fi-high" if sim_dmc > 30 else "fi-mod" if sim_dmc > 15 else "fi-low"}"><div class="fv">{sim_dmc:.1f}</div><div class="fl">DMC</div></div>
            <div class="fi {"fi-vhigh" if sim_dc > 400 else "fi-high" if sim_dc > 200 else "fi-mod" if sim_dc > 80 else "fi-low"}"><div class="fv">{sim_dc:.1f}</div><div class="fl">DC</div></div>
            <div class="fi {"fi-vhigh" if sim_isi > 10 else "fi-high" if sim_isi > 5 else "fi-mod" if sim_isi > 2 else "fi-low"}"><div class="fv">{sim_isi:.1f}</div><div class="fl">ISI</div></div>
            <div class="fi {"fi-vhigh" if sim_bui > 60 else "fi-high" if sim_bui > 30 else "fi-mod" if sim_bui > 15 else "fi-low"}"><div class="fv">{sim_bui:.1f}</div><div class="fl">BUI</div></div>
            <div class="fi {"fi-vhigh" if sim_fwi_val > 30 else "fi-high" if sim_fwi_val > 15 else "fi-mod" if sim_fwi_val > 5 else "fi-low"}"><div class="fv">{sim_fwi_val:.1f}</div><div class="fl">FWI</div></div>
        </div>

        <!-- ═══ Unified Legend (bottom-right) ═══ -->
        <div id="legend-panel" class="glass">
            <div class="leg-title" style="color:#f97316;">Legend</div>

            <div class="leg-group">
                <div class="leg-group-label">NRT Fires</div>
                <div class="lg-row"><div class="lg-circle" style="background:#ef4444;"></div> CRITICAL</div>
                <div class="lg-row"><div class="lg-circle" style="background:#f97316;"></div> HIGH / Other</div>
            </div>
            <div class="leg-group">
                <div class="leg-group-label">FIRMS History</div>
                <div class="lg-row"><div class="lg-circle" style="background:#dc2626;"></div> High conf</div>
                <div class="lg-row"><div class="lg-circle" style="background:#f97316;"></div> Nominal</div>
                <div class="lg-row"><div class="lg-circle" style="background:#eab308;"></div> Low conf</div>
            </div>
            <div class="leg-group">
                <div class="leg-group-label">Burn Scars</div>
                <div class="lg-row"><div class="lg-diamond" style="background:#dc2626;"></div> HIGH</div>
                <div class="lg-row"><div class="lg-diamond" style="background:#f59e0b;"></div> MEDIUM</div>
                <div class="lg-row"><div class="lg-diamond" style="background:#6b7280;"></div> LOW</div>
            </div>
            <div class="leg-group">
                <div class="leg-group-label">Risk Grid</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#dc2626;"></div> CRITICAL</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#f97316;"></div> HIGH</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#eab308;"></div> MODERATE</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#22c55e;"></div> LOW</div>
            </div>
            <div class="leg-group">
                <div class="leg-group-label">Forest Health</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#22c55e;"></div> Healthy (&ge;80%)</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#eab308;"></div> Moderate (60-80%)</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#f97316;"></div> Stressed (40-60%)</div>
                <div class="lg-row"><div class="lg-swatch" style="background:#ef4444;"></div> Degraded (&lt;40%)</div>
            </div>
        </div>

        <div id="sbar">
            <span class="sd g" id="sdot"></span>
            <span id="stxt">3D Command Center &mdash; {sim_n_fires} NRT fires &bull; {_n_firms} FIRMS &bull; {_n_burns} burn scars &bull; {_n_compartments} compartments &bull; {_n_pred} risk cells</span>
        </div>

        <script>
            // ── All data layers (declare first) ──
            const FIRES = {fire_points_js};
            const CMP = {compartments_js};
            const HIST = {firms_js};
            const BURNS = {burns_js};
            const PRED = {pred_js};

            // ── Viewer with real 3D terrain ──
            const viewer = new Cesium.Viewer('cesiumContainer', {{
                imageryProvider: new Cesium.ArcGisMapServerImageryProvider({{
                    url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
                }}),
                terrainProvider: Cesium.createWorldTerrain({{ requestVertexNormals: true }}),
                baseLayerPicker: false, infoBox: true, animation: false, timeline: false,
                geocoder: false, homeButton: false, sceneModePicker: false,
                navigationHelpButton: false, fullscreenButton: false
            }});
            viewer.scene.globe.depthTestAgainstTerrain = true;
            viewer.scene.globe.enableLighting = true;

            // ── LULC overlay (ESA WorldCover 10m) ──
            var lulcBounds = {json.dumps(_ov_bounds.get("lulc", {{}}))};
            var lulcLayer = null;
            if (lulcBounds.w) {{
                lulcLayer = viewer.imageryLayers.addImageryProvider(
                    new Cesium.SingleTileImageryProvider({{
                        url: '{_overlay_base}/lulc.png',
                        rectangle: Cesium.Rectangle.fromDegrees(lulcBounds.w, lulcBounds.s, lulcBounds.e, lulcBounds.n)
                    }})
                );
                lulcLayer.alpha = 0.7;
                lulcLayer.show = true;
            }}

            // ── Slope overlay ──
            var slopeBounds = {json.dumps(_ov_bounds.get("slope", {{}}))};
            var slopeLayer = null;
            if (slopeBounds.w) {{
                slopeLayer = viewer.imageryLayers.addImageryProvider(
                    new Cesium.SingleTileImageryProvider({{
                        url: '{_overlay_base}/slope.png',
                        rectangle: Cesium.Rectangle.fromDegrees(slopeBounds.w, slopeBounds.s, slopeBounds.e, slopeBounds.n)
                    }})
                );
                slopeLayer.alpha = 0.6;
                slopeLayer.show = false;
            }}

            // ── Aspect overlay ──
            var aspectBounds = {json.dumps(_ov_bounds.get("aspect", {{}}))};
            var aspectLayer = null;
            if (aspectBounds.w) {{
                aspectLayer = viewer.imageryLayers.addImageryProvider(
                    new Cesium.SingleTileImageryProvider({{
                        url: '{_overlay_base}/aspect.png',
                        rectangle: Cesium.Rectangle.fromDegrees(aspectBounds.w, aspectBounds.s, aspectBounds.e, aspectBounds.n)
                    }})
                );
                aspectLayer.alpha = 0.6;
                aspectLayer.show = false;
            }}

            // Camera: if fires → zoom to fire, else overview all compartments
            const _hasFires = FIRES.length > 0;
            viewer.camera.flyTo({{
                destination: _hasFires
                    ? Cesium.Cartesian3.fromDegrees({sim_center_lon}, {sim_center_lat} - 0.015, 6000)
                    : Cesium.Cartesian3.fromDegrees(77.15, 24.30, 55000),
                orientation: {{ pitch: Cesium.Math.toRadians(-35), heading: Cesium.Math.toRadians(15) }},
                duration: 2.0
            }});
            const MLAT = 111320;
            const MLON = MLAT * Math.cos({sim_center_lat} * Math.PI / 180);
            const WRAD = ({sim_wind_dir} + 180) * Math.PI / 180;

            // ── State ──
            let fCoords = [], cCoords = [];
            let running = false, timer = null, st = 0, mode = null;

            // ── Outer fire perimeter polygon ──
            viewer.entities.add({{
                name: 'FireOuter',
                polygon: {{
                    hierarchy: new Cesium.CallbackProperty(() => {{
                        return fCoords.length > 2 ? new Cesium.PolygonHierarchy(
                            fCoords.map(c => Cesium.Cartesian3.fromDegrees(c.lon, c.lat))
                        ) : null;
                    }}, false),
                    material: Cesium.Color.ORANGERED.withAlpha(0.55),
                    outline: true, outlineColor: Cesium.Color.YELLOW,
                    heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                }}
            }});

            // ── Inner fire core polygon ──
            viewer.entities.add({{
                name: 'FireCore',
                polygon: {{
                    hierarchy: new Cesium.CallbackProperty(() => {{
                        return cCoords.length > 2 ? new Cesium.PolygonHierarchy(
                            cCoords.map(c => Cesium.Cartesian3.fromDegrees(c.lon, c.lat))
                        ) : null;
                    }}, false),
                    material: Cesium.Color.YELLOW.withAlpha(0.35),
                    heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                }}
            }});

            // ── 3D Forest Digital Twin — LULC-aware compartments + billboards ──
            const forestEntities = [];
            const bbEntities = [];
            let forestVisible = true;

            function aspDir(a) {{
                if (a < 22.5 || a >= 337.5) return 'N';
                if (a < 67.5) return 'NE'; if (a < 112.5) return 'E';
                if (a < 157.5) return 'SE'; if (a < 202.5) return 'S';
                if (a < 247.5) return 'SW'; if (a < 292.5) return 'W'; return 'NW';
            }}
            function sRand(s) {{ var x = Math.sin(s) * 10000; return x - Math.floor(x); }}

            // SVG billboards for each LULC type
            var svgTree = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="48"><polygon points="16,2 4,20 12,18 6,32 12,30 8,42 24,42 20,30 26,32 20,18 28,20" fill="#15803d" stroke="#0a5c2a" stroke-width="1"/><rect x="13" y="42" width="6" height="6" fill="#7c3f00"/></svg>');
            var svgShrub = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><ellipse cx="16" cy="18" rx="13" ry="10" fill="#4d7c0f" stroke="#365314" stroke-width="1"/><ellipse cx="10" cy="14" rx="8" ry="7" fill="#65a30d" opacity="0.7"/><rect x="14" y="26" width="4" height="6" fill="#7c3f00"/></svg>');
            var svgCrop = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="44"><line x1="14" y1="44" x2="14" y2="12" stroke="#a16207" stroke-width="2"/><line x1="14" y1="20" x2="6" y2="14" stroke="#a16207" stroke-width="1.5"/><line x1="14" y1="20" x2="22" y2="14" stroke="#a16207" stroke-width="1.5"/><ellipse cx="14" cy="8" rx="7" ry="6" fill="#eab308" stroke="#ca8a04" stroke-width="1"/><ellipse cx="8" cy="12" rx="4" ry="3" fill="#facc15" opacity="0.6"/><ellipse cx="20" cy="12" rx="4" ry="3" fill="#facc15" opacity="0.6"/></svg>');
            var svgGrass = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28"><path d="M6,28 Q8,12 10,4" stroke="#65a30d" fill="none" stroke-width="2"/><path d="M14,28 Q14,10 14,2" stroke="#4d7c0f" fill="none" stroke-width="2"/><path d="M22,28 Q20,12 18,4" stroke="#65a30d" fill="none" stroke-width="2"/><path d="M10,28 Q12,16 16,8" stroke="#84cc16" fill="none" stroke-width="1.5"/><path d="M18,28 Q16,16 12,8" stroke="#84cc16" fill="none" stroke-width="1.5"/></svg>');
            var svgBuilt = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="28"><rect x="3" y="10" width="18" height="18" fill="#6b7280" stroke="#4b5563" stroke-width="1"/><polygon points="12,2 1,12 23,12" fill="#9ca3af" stroke="#6b7280" stroke-width="1"/><rect x="9" y="18" width="6" height="10" fill="#fbbf24"/></svg>');
            var svgWater = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="20"><path d="M2,10 Q7,4 14,10 Q21,16 26,10" stroke="#3b82f6" fill="none" stroke-width="2.5"/><path d="M2,16 Q7,10 14,16 Q21,22 26,16" stroke="#60a5fa" fill="none" stroke-width="2"/></svg>');

            var lcIcons = [
                {{key:'lt', svg:svgTree,  w:24, h:36}},
                {{key:'ls', svg:svgShrub, w:22, h:22}},
                {{key:'lg', svg:svgGrass, w:20, h:20}},
                {{key:'lc', svg:svgCrop,  w:20, h:32}},
                {{key:'lb', svg:svgBuilt, w:18, h:22}},
                {{key:'lw', svg:svgWater, w:22, h:16}},
            ];

            CMP.forEach(function(d, idx) {{
                try {{
                    // Extruded compartment polygon
                    var pos = Cesium.Cartesian3.fromDegreesArray(d.c);
                    var e = viewer.entities.add({{
                        name: 'FC',
                        polygon: {{
                            hierarchy: new Cesium.PolygonHierarchy(pos),
                            material: Cesium.Color.fromCssColorString(d.cl).withAlpha(0.55),
                            extrudedHeight: d.h,
                            height: 0,
                            outline: true,
                            outlineColor: d.f > 0
                                ? Cesium.Color.RED.withAlpha(0.8)
                                : Cesium.Color.WHITE.withAlpha(0.2),
                        }},
                        description:
                            '<table style="font-size:13px;border-collapse:collapse;">' +
                            '<tr><td style="padding:2px 8px;color:#888;">Beat</td><td><b>' + d.b + '</b></td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#888;">Range</td><td><b>' + d.r + '</b></td></tr>' +
                            '<tr><td colspan="2" style="border-top:1px solid #333;padding-top:4px;font-size:11px;color:#666;">LAND COVER</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#15803d;">&#x1f332; Trees</td><td><b>' + d.lt + '%</b></td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#4d7c0f;">&#x1fab4; Shrubs</td><td>' + d.ls + '%</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#84cc16;">&#x1f33f; Grass</td><td>' + d.lg + '%</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#eab308;">&#x1f33e; Crops</td><td>' + d.lc + '%</td></tr>' +
                            (d.lb > 0 ? '<tr><td style="padding:2px 8px;color:#6b7280;">&#x1f3d8; Built</td><td>' + d.lb + '%</td></tr>' : '') +
                            (d.lw > 0 ? '<tr><td style="padding:2px 8px;color:#3b82f6;">&#x1f4a7; Water</td><td>' + d.lw + '%</td></tr>' : '') +
                            '<tr><td colspan="2" style="border-top:1px solid #333;padding-top:4px;font-size:11px;color:#666;">FOREST STATUS</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#888;">Area</td><td>' + d.a + ' ha (was ' + d.ao + ')</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#888;">Health</td><td style="color:' + d.cl + ';font-weight:700;">' + (d.hl * 100).toFixed(0) + '%</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#888;">Fires</td><td style="color:' + (d.f > 0 ? '#ef4444' : '#22c55e') + ';">' + d.f + '</td></tr>' +
                            '<tr><td colspan="2" style="border-top:1px solid #333;padding-top:4px;font-size:11px;color:#666;">TERRAIN</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#888;">Elevation</td><td>' + d.el + ' m</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#888;">Slope</td><td>' + d.sl + '&deg;</td></tr>' +
                            '<tr><td style="padding:2px 8px;color:#888;">Aspect</td><td>' + d.asp + '&deg; (' + aspDir(d.asp) + ')</td></tr>' +
                            '</table>',
                    }});
                    forestEntities.push(e);

                    // LULC-aware billboard placement — proportional to actual land cover %
                    var lons = d.c.filter(function(_, i) {{ return i % 2 === 0; }});
                    var lats = d.c.filter(function(_, i) {{ return i % 2 === 1; }});
                    var loMin = Math.min.apply(null, lons), loMax = Math.max.apply(null, lons);
                    var laMin = Math.min.apply(null, lats), laMax = Math.max.apply(null, lats);
                    var seed = idx * 31;

                    lcIcons.forEach(function(lc) {{
                        var pct = d[lc.key] || 0;
                        // Scale: 1 billboard per ~12% coverage, min 0, max 8
                        var n = Math.min(Math.round(pct / 12), 8);
                        for (var t = 0; t < n; t++) {{
                            seed++;
                            var tlon = loMin + sRand(seed * 7) * (loMax - loMin);
                            var tlat = laMin + sRand(seed * 11) * (laMax - laMin);
                            var te = viewer.entities.add({{
                                name: 'BB',
                                position: Cesium.Cartesian3.fromDegrees(tlon, tlat, d.h + 3),
                                billboard: {{
                                    image: lc.svg,
                                    width: lc.w,
                                    height: lc.h,
                                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                                    scaleByDistance: new Cesium.NearFarScalar(3000, 1.5, 60000, 0.25),
                                }},
                            }});
                            bbEntities.push(te);
                        }}
                    }});
                }} catch(ex) {{ /* skip bad geometry */ }}
            }});

            // ── Layer toggle functions (wired to checkbox onchange) ──
            function toggleForest2() {{
                forestVisible = document.getElementById('chk-forest').checked;
                forestEntities.forEach(function(e) {{ e.show = forestVisible; }});
                bbEntities.forEach(function(e) {{ e.show = forestVisible; }});
            }}
            function toggleLulc2() {{
                if (!lulcLayer) return;
                lulcLayer.show = document.getElementById('chk-lulc').checked;
            }}
            function toggleSlope2() {{
                if (!slopeLayer) return;
                slopeLayer.show = document.getElementById('chk-slope').checked;
            }}
            function toggleAspect2() {{
                if (!aspectLayer) return;
                aspectLayer.show = document.getElementById('chk-aspect').checked;
            }}

            // ── NRT Fire markers (with pulsing effect) ──
            const nrtEntities = [];
            let pulsePhase = 0;
            FIRES.forEach((f, i) => {{
                const isCrit = f.severity === 'CRITICAL';
                const baseSize = isCrit ? 16 : 12;
                const e = viewer.entities.add({{
                    position: Cesium.Cartesian3.fromDegrees(f.lon, f.lat),
                    point: {{
                        pixelSize: new Cesium.CallbackProperty(() => {{
                            return baseSize + Math.sin(pulsePhase + i) * 4;
                        }}, false),
                        color: isCrit ? Cesium.Color.RED.withAlpha(0.9) : Cesium.Color.ORANGE.withAlpha(0.9),
                        outlineColor: Cesium.Color.WHITE, outlineWidth: 2,
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                    }},
                    label: {{
                        text: (f.category || f.severity) + ' (' + f.frp.toFixed(1) + ' MW)',
                        font: '11px sans-serif bold', fillColor: Cesium.Color.WHITE,
                        style: Cesium.LabelStyle.FILL_AND_OUTLINE, outlineWidth: 3, outlineColor: Cesium.Color.BLACK,
                        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                        pixelOffset: new Cesium.Cartesian2(0, -22),
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                    }},
                    description: '<b>NRT Fire Alert</b><br>Severity: ' + f.severity +
                        '<br>FRP: ' + f.frp.toFixed(1) + ' MW<br>ROS: ' + f.ros.toFixed(1) +
                        ' m/min<br>Intensity: ' + f.intensity.toFixed(0) + ' kW/m'
                }});
                nrtEntities.push(e);
            }});
            // Animate NRT pulse
            viewer.clock.onTick.addEventListener(() => {{ pulsePhase += 0.08; }});

            function toggleLayerNrt() {{
                const vis = document.getElementById('chk-nrt').checked;
                nrtEntities.forEach(e => e.show = vis);
            }}

            // ── FIRMS Fire History layer ──
            const histEntities = [];
            HIST.forEach(h => {{
                const sz = Math.max(4, Math.min(14, h.f / 10));
                const clr = h.c === 'high' ? '#dc2626' : h.c === 'nominal' ? '#f97316' : '#eab308';
                histEntities.push(viewer.entities.add({{
                    position: Cesium.Cartesian3.fromDegrees(h.lo, h.la),
                    point: {{
                        pixelSize: sz,
                        color: Cesium.Color.fromCssColorString(clr).withAlpha(0.7),
                        outlineColor: Cesium.Color.BLACK.withAlpha(0.3), outlineWidth: 1,
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                    }},
                    description: '<b>FIRMS Detection</b><br>Date: ' + h.d +
                        '<br>FRP: ' + h.f + ' MW<br>Confidence: ' + h.c,
                    show: true
                }}));
            }});

            function toggleLayerHist() {{
                const vis = document.getElementById('chk-hist').checked;
                histEntities.forEach(e => e.show = vis);
            }}

            // ── Burn Scars layer (diamond-like markers) ──
            var svgDiamond = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">' +
                '<polygon points="10,1 19,10 10,19 1,10" fill="#dc2626" stroke="#fff" stroke-width="1.5"/></svg>');
            var svgDiamondMed = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">' +
                '<polygon points="10,1 19,10 10,19 1,10" fill="#f59e0b" stroke="#fff" stroke-width="1.5"/></svg>');
            var svgDiamondLow = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">' +
                '<polygon points="10,1 19,10 10,19 1,10" fill="#6b7280" stroke="#fff" stroke-width="1.5"/></svg>');

            const burnEntities = [];
            BURNS.forEach(b => {{
                const sz = Math.max(14, Math.min(28, b.a / 50));
                const svg = b.c.includes('HIGH') ? svgDiamond : b.c.includes('MED') ? svgDiamondMed : svgDiamondLow;
                burnEntities.push(viewer.entities.add({{
                    position: Cesium.Cartesian3.fromDegrees(b.lo, b.la),
                    billboard: {{
                        image: svg, width: sz, height: sz,
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                        scaleByDistance: new Cesium.NearFarScalar(5000, 1.2, 80000, 0.3)
                    }},
                    description: '<b>Burn Scar</b><br>Area: ' + b.a + ' ha' +
                        '<br>Scene: ' + b.sd + '<br>Fire: ' + b.fd + '<br>Confidence: ' + b.c,
                    show: true
                }}));
            }});

            function toggleLayerBurn() {{
                const vis = document.getElementById('chk-burn').checked;
                burnEntities.forEach(e => e.show = vis);
            }}

            // ── Predictive Risk Grid layer ──
            const predEntities = [];
            const riskColors = {{ CRITICAL: '#dc2626', HIGH: '#f97316', MODERATE: '#eab308', LOW: '#22c55e' }};
            PRED.forEach(p => {{
                const clr = riskColors[p.l] || '#22c55e';
                predEntities.push(viewer.entities.add({{
                    polygon: {{
                        hierarchy: new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(p.c)),
                        material: Cesium.Color.fromCssColorString(clr).withAlpha(0.35),
                        height: 0, outline: true,
                        outlineColor: Cesium.Color.fromCssColorString(clr).withAlpha(0.8),
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                    }},
                    description: '<b>Risk Cell</b><br>Beat: ' + p.b +
                        '<br>Range: ' + p.r + '<br>Score: ' + (p.s * 100).toFixed(0) +
                        '%<br>Level: ' + p.l,
                    show: false
                }}));
            }});

            function toggleLayerPred() {{
                const vis = document.getElementById('chk-pred').checked;
                predEntities.forEach(e => e.show = vis);
            }}

            // ── Elliptical fire spread model ──
            function firePeri(ctr, t, ros, scl) {{
                const s = scl || 1.0;
                const hd = ros * t * s, fl = ros * 0.28 * t * s, bk = ros * 0.08 * t * s;
                const a = (hd + bk) / 2, b = fl, off = (hd - bk) / 2;
                const pts = [];
                for (let i = 0; i < 48; i++) {{
                    const th = i / 48 * 2 * Math.PI;
                    let x = a * Math.cos(th) + off, y = b * Math.sin(th);
                    const j = 1.0 + Math.sin(th * 5 + t * 0.7) * 0.06;
                    x *= j; y *= j;
                    const rx = x * Math.cos(WRAD) - y * Math.sin(WRAD);
                    const ry = x * Math.sin(WRAD) + y * Math.cos(WRAD);
                    pts.push({{ lon: ctr.lon + rx / MLON, lat: ctr.lat + ry / MLAT }});
                }}
                return pts;
            }}

            // ── Polygon area (shoelace) in hectares ──
            function pArea(pts) {{
                let a = 0;
                for (let i = 0; i < pts.length; i++) {{
                    const j = (i + 1) % pts.length;
                    a += (pts[j].lon - pts[i].lon) * (pts[j].lat + pts[i].lat);
                }}
                return Math.abs(a / 2) * MLON * MLAT / 10000;
            }}

            // ── Intervention mode ──
            let intCount = 0;
            function setM(m) {{
                mode = m;
                document.getElementById('lnBtn').classList.toggle('active', m === 'FIRELINE');
                document.getElementById('igBtn').classList.toggle('active', m === 'BACKFIRE');
                document.getElementById('sstat').innerText = m === 'FIRELINE' ? 'Click map: place firebreak' : 'Click map: place backfire';
                document.getElementById('sstat').className = 'hv amber';
            }}

            const hndl = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
            hndl.setInputAction((click) => {{
                if (!mode) return;
                // Use pickEllipsoid (works with EllipsoidTerrainProvider)
                const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
                if (!cartesian) return;
                const carto = Cesium.Cartographic.fromCartesian(cartesian);
                const lon = Cesium.Math.toDegrees(carto.longitude);
                const lat = Cesium.Math.toDegrees(carto.latitude);
                intCount++;
                const isFl = mode === 'FIRELINE';
                viewer.entities.add({{
                    name: 'Intervention',
                    position: Cesium.Cartesian3.fromDegrees(lon, lat),
                    point: {{
                        pixelSize: isFl ? 14 : 12,
                        color: isFl ? Cesium.Color.CYAN : Cesium.Color.ORANGERED,
                        outlineColor: Cesium.Color.WHITE, outlineWidth: 2,
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                    }},
                    label: {{
                        text: (isFl ? 'FIRELINE ' : 'BACKFIRE ') + intCount,
                        font: '11px sans-serif bold',
                        fillColor: isFl ? Cesium.Color.CYAN : Cesium.Color.ORANGERED,
                        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                        outlineWidth: 3, outlineColor: Cesium.Color.BLACK,
                        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                        pixelOffset: new Cesium.Cartesian2(0, -18),
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                    }}
                }});
                document.getElementById('sstat').innerText = (isFl ? 'Firebreak' : 'Backfire') + ' #' + intCount + ' placed at ' + lat.toFixed(3) + 'N ' + lon.toFixed(3) + 'E';
            }}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

            // ── Simulation engine (Real-Time WebSocket) ──
            function toggleSim() {{
                if (running) {{
                    running = false; if (socket) socket.close();
                    document.getElementById('simBtn').innerHTML = '&#x25b6; START';
                    document.getElementById('simBtn').classList.remove('running');
                    document.getElementById('sstat').innerText = 'Stopped';
                    document.getElementById('sdot').className = 'sd g';
                    return;
                }}

                running = true;
                document.getElementById('simBtn').innerHTML = '&#x23f9; STOP';
                document.getElementById('simBtn').classList.add('running');
                document.getElementById('sstat').innerText = 'Connecting...';
                document.getElementById('sdot').className = 'sd r';

                // Use 127.0.0.1 for local stability
                socket = new WebSocket("ws://127.0.0.1:8001/ws/simulate");
                
                socket.onopen = () => {{
                    document.getElementById('sstat').innerText = 'Syncing PDE...';
                    socket.send(JSON.stringify({{
                        lat: {sim_center_lat}, lon: {sim_center_lon}, 
                        wind_u: {sim_wind_speed / 3.6}, wind_v: 0.0,
                        interventions: interventions
                    }}));
                }};

                socket.onmessage = (e) => {{
                    const data = JSON.parse(e.data);
                    if (data.polygons && data.polygons.length > 0) {{
                        fCoords = data.polygons[0].map(c => ({{ lon: c[0], lat: c[1] }}));
                    }}
                    
                    // Update HUD
                    document.getElementById('stime').innerText = '+' + data.time_elapsed + ':00';
                    document.getElementById('intensity-val').innerText = data.intensity_kw_m.toFixed(0) + ' kW/m';
                    document.getElementById('ros-val').innerText = data.ros_m_min.toFixed(1) + ' m/min';
                    document.getElementById('flame-val').innerText = data.flame_height_m.toFixed(1) + ' m';
                    
                    document.getElementById('sstat').innerText = 'Streaming Physics';
                    document.getElementById('sstat').className = 'hv red';
                }};

                socket.onerror = () => {{
                    document.getElementById('sstat').innerText = 'WS Error (Port 8001)';
                    running = false;
                }};
            }}

            function resetSim() {{
                running = false; clearInterval(timer); st = 0;
                fCoords = []; cCoords = []; intCount = 0;
                viewer.entities.values.filter(e => e.name === 'Intervention').forEach(e => viewer.entities.remove(e));
                document.getElementById('simBtn').innerText = '&#x25b6; START';
                document.getElementById('simBtn').classList.remove('running');
                document.getElementById('sstat').innerText = 'Ready';
                document.getElementById('sstat').className = 'hv green';
                document.getElementById('stime').innerText = '00:00';
                document.getElementById('sarea').innerText = '0 ha';
                document.getElementById('sfcls').innerText = '\u2014';
                document.getElementById('fmet').style.display = 'none';
                document.getElementById('sdot').className = 'sd g';
                document.getElementById('stxt').innerText = '3D Command Center \u2014 ' + FIRES.length + ' NRT fires \u2022 ' +
                    HIST.length + ' FIRMS \u2022 ' + BURNS.length + ' burn scars \u2022 ' +
                    CMP.length + ' compartments \u2022 ' + PRED.length + ' risk cells';
                mode = null;
            }}
        </script>
    </body>
    </html>
    """
    
    st.components.v1.html(cesium_html, height=1050)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: Live Alert (includes NRT Hotspot Feed)
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "\U0001f6a8 Live Alert":
    demo_narration_banner()
    st.header("\U0001f6a8 Live Fire Alert Bulletin")

    # Date picker — demo mode defaults to the INFERNO event
    _live_default = date(2019, 4, 14) if st.session_state.get("demo_active") else date.today()
    col_date, col_run = st.columns([2, 1])
    with col_date:
        alert_date = st.date_input(
            "Alert date",
            value=_live_default,
            min_value=date(2013, 1, 1),
            max_value=date.today(),
        )
    with col_run:
        st.write("")
        if st.button("Run Alert Pipeline", type="primary"):
            with st.spinner("Running alert pipeline..."):
                import subprocess, sys
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "nrt_alert_pipeline.py"),
                     "--date", str(alert_date)],
                    capture_output=True, text=True, cwd=str(ROOT)
                )
            st.cache_data.clear()
            if result.returncode == 0:
                st.success("Alert generated!")
            else:
                st.error(f"Pipeline error: {result.stderr[:300]}")

    alert = load_alert_for_date(alert_date)
    if not alert:
        alert = load_latest_alert()

    if not alert:
        st.warning("No alert data found. Click 'Run Alert Pipeline' to generate one.")
        st.stop()

    # ── Top banner ────────────────────────────────────────────────────────────
    sev = alert.get("bulletin_severity", "CLEAR")
    col_banner, col_meta = st.columns([3, 1])
    with col_banner:
        st.markdown(
            f'<div class="status-banner" style="background:{SEV_COLORS.get(sev,"#888")}">'
            f'{sev} &mdash; {alert.get("target_date","")}'
            f'<div class="subtitle">Guna Division, Madhya Pradesh</div></div>',
            unsafe_allow_html=True,
        )
    with col_meta:
        gen_at = alert.get('generated_at', '')[:19]
        forest_used = alert.get("forest_mask_used", False)
        forest_icon = "&#9989;" if forest_used else "&#9888;&#65039;"
        st.markdown(
            f'<div class="meta-panel">'
            f'<strong>Generated</strong><br>{gen_at}<br><br>'
            f'<strong>Forest Mask</strong><br>'
            f'{forest_icon} {"Active" if forest_used else "Not loaded"}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── FWI + fire counts ─────────────────────────────────────────────────────
    fwi_data = alert.get("fwi", {})
    fwi_val  = fwi_data.get("value", 0) or 0
    fires    = alert.get("fires", [])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card("FWI", f"{fwi_val:.1f}",
                    fwi_data.get("danger_class",""),
                    fwi_color(fwi_val), icon="\U0001f321\ufe0f")
    with c2:
        metric_card("Active Fires", alert.get("fires_detected", 0),
                    "in Guna bbox", "#e34a33", icon="\U0001f525")
    with c3:
        metric_card("Forest Fires",
                    alert.get("n_forest_fires", "\u2014"),
                    "in/near forest", "#d73027", icon="\U0001f332")
    with c4:
        metric_card("Agri Fires",
                    alert.get("n_agri_fires", "\u2014"),
                    "cropland burns", "#f46d43", icon="\U0001f33e")
    with c5:
        metric_card("Peak FRP",
                    f"{alert.get('peak_frp_mw', 0):.1f} MW",
                    "fire radiative power", "#fc8d59", icon="\u26a1")

    # ── FWI components ────────────────────────────────────────────────────────
    st.subheader("Fire Weather Index Components")
    fwi_cols = st.columns(6)
    for col, (key, label) in zip(fwi_cols,
        [("ffmc","FFMC"),("dmc","DMC"),("dc","DC"),
         ("isi","ISI"),("bui","BUI"),("value","FWI")]):
        val = fwi_data.get(key)
        color = fwi_color(fwi_val) if key == "value" else "#4393c3"
        with col:
            metric_card(label, f"{val:.1f}" if val is not None else "—",
                        color=color)

    # ── Conditions row ────────────────────────────────────────────────────────
    if fwi_data.get("temp_c") is not None:
        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            metric_card("Temperature", f"{fwi_data['temp_c']}\u00b0C", color="#fd8d3c", icon="\U0001f321\ufe0f")
        with cc2:
            metric_card("Rel. Humidity", f"{fwi_data['rh_pct']}%", color="#6baed6", icon="\U0001f4a7")
        with cc3:
            metric_card("Wind Speed", f"{fwi_data['wind_kmh']} km/h", color="#74c476", icon="\U0001f4a8")
        with cc4:
            metric_card("Danger Class", fwi_data.get("danger_class",""), color=fwi_color(fwi_val), icon="\u26a0\ufe0f")

    # ── Fire table (with terrain enrichment) ─────────────────────────────────
    if fires:
        st.subheader(f"Fire Detections ({len(fires)} total)")
        fire_df = pd.DataFrame(fires)

        # Enrich with terrain info if rasters are available
        terrain_available = (TERRAIN_DIR / "terrain_stats.json").exists()
        if terrain_available:
            try:
                import sys
                sys.path.insert(0, str(ROOT / "scripts"))
                from fetch_dem import get_terrain_at_point
                terrains = [
                    get_terrain_at_point(r["fire_lat"], r["fire_lon"])
                    for _, r in fire_df.iterrows()
                ]
                fire_df["elevation_m"]     = [t.get("elevation_m",  np.nan) for t in terrains]
                fire_df["slope_deg"]       = [t.get("slope_deg",    np.nan) for t in terrains]
                fire_df["terrain_risk"]    = [t.get("terrain_risk_label", "—") for t in terrains]
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Ignored exception: {e}")

        display_cols = [c for c in
            ["severity","fire_lat","fire_lon","frp_mw","fire_time_ist",
             "daynight","land_cover","in_forest",
             "elevation_m","slope_deg","terrain_risk","viirs_confidence"]
            if c in fire_df.columns]
        style_kwargs = {"subset": ["severity"]} if "severity" in display_cols else {}
        st.dataframe(
            fire_df[display_cols].style.map(
                lambda v: f"background-color:{SEV_COLORS.get(v,'')};color:white"
                if v in SEV_COLORS else "",
                **style_kwargs
            ),
            use_container_width=True, height=350
        )

        # ── Spread predictions ──────────────────────────────────────────────
        fires_with_spread = [f for f in fires if f.get("predicted_spread")]
        if fires_with_spread:
            st.subheader(f"Predicted Fire Spread ({len(fires_with_spread)} fires)")
            spread_rows = []
            for f in fires_with_spread:
                sp = f["predicted_spread"]
                spread_rows.append({
                    "Severity": f["severity"],
                    "Lat": f["fire_lat"],
                    "Lon": f["fire_lon"],
                    "FRP (MW)": f["frp_mw"],
                    "6h Area (ha)": sp["spread_6h"]["area_ha"],
                    "12h Area (ha)": sp["spread_12h"]["area_ha"],
                    "24h Area (ha)": sp["spread_24h"]["area_ha"],
                    "Intensity (kW/m)": sp["byram_intensity_kw_m"],
                    "Flame (m)": sp["flame_length_m"],
                    "Mode": sp["mode"],
                })
            st.dataframe(pd.DataFrame(spread_rows), use_container_width=True, height=200)
            st.caption("Spread polygons shown on map: yellow=6h, orange=12h, red=24h")

        # ── Map ────────────────────────────────────────────────────────────
        st.subheader("Fire Locations")
        map_cols = [c for c in ["fire_lat","fire_lon","frp_mw","severity"] if c in fire_df.columns]
        if len(map_cols) < 2:
            st.info("Insufficient location data for map.")
        else:
            if "frp_mw" not in fire_df.columns:
                fire_df["frp_mw"] = 5.0
            if "severity" not in fire_df.columns:
                fire_df["severity"] = "MODERATE"
            map_df = fire_df[["fire_lat","fire_lon","frp_mw","severity"]].copy()
            map_df.columns = ["lat","lon","frp_mw","severity"]
            sev_rgb = {"CRITICAL":[215,48,39],"HIGH":[244,109,67],"MODERATE":[253,174,97],"LOW":[116,196,118]}
            map_df["color"] = map_df["severity"].map(lambda s: sev_rgb.get(s, [200,200,200]))
            fire_layer = pdk.Layer(
                "ScatterplotLayer", data=map_df,
                get_position=["lon","lat"], get_radius="frp_mw * 50 + 400",
                get_fill_color="color", pickable=True,
            )
            layers = [fire_layer]

            # Add spread polygon layers (6h=yellow, 12h=orange, 24h=red)
            _spread_colors = {
                "spread_6h":  [255, 255, 0, 60],   # yellow, transparent
                "spread_12h": [255, 165, 0, 50],    # orange
                "spread_24h": [255, 0, 0, 40],      # red
            }
            for horizon_key, fill_color in _spread_colors.items():
                spread_features = []
                for f in fires:
                    sp = f.get("predicted_spread")
                    if not sp:
                        continue
                    poly = sp.get(horizon_key, {}).get("polygon")
                    if poly and poly.get("coordinates"):
                        spread_features.append({
                            "type": "Feature",
                            "geometry": poly,
                            "properties": {
                                "area_ha": sp[horizon_key].get("area_ha", 0),
                                "horizon": horizon_key,
                            },
                        })
                if spread_features:
                    geojson_fc = {"type": "FeatureCollection", "features": spread_features}
                    layers.append(pdk.Layer(
                        "GeoJsonLayer", data=geojson_fc,
                        get_fill_color=fill_color,
                        get_line_color=fill_color[:3] + [180],
                        line_width_min_pixels=1,
                        pickable=True,
                    ))

            boundary = load_boundary_geojson()
            if boundary:
                layers.insert(0, pdk.Layer(
                    "GeoJsonLayer", data=boundary,
                    get_line_color=[249,115,22,100], get_fill_color=[0,0,0,0],
                    line_width_min_pixels=1, pickable=True,
                ))
            _deck_alert = pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(latitude=24.4,longitude=77.15,zoom=9,pitch=0),
                map_style="dark",
                tooltip={"text": "{severity} \u2014 FRP: {frp_mw} MW\n{horizon}: {area_ha} ha"},
            )
            st.pydeck_chart(_deck_alert)
            fullscreen_map_button(_deck_alert, "live_alert")
    else:
        if sev == "WATCH":
            st.info(f"No active fires detected. FWI={fwi_val:.1f} ({fwi_data.get('danger_class','')}). "
                    f"Fire weather conditions are DANGEROUS — heightened patrol advised.")
        else:
            st.success("No fires detected. Conditions are safe.")

    # ── Download Alert ──────────────────────────────────────────────────────
    st.divider()
    st.download_button(
        "\U0001f4e5 Download Alert JSON",
        data=json.dumps(alert, indent=2, default=str),
        file_name=f"alert_{alert.get('target_date', 'latest')}.json",
        mime="application/json",
        key="dl_alert_json",
    )

    # ── Live NRT Hotspot Feed (Clipped to Guna) ─────────────────────────────
    st.divider()
    st.subheader("\U0001f4e1 Live NRT Hotspot Feed (Last 48 Hours)")
    with st.spinner("Fetching latest satellite hotspots..."):
        all_firms = load_firms_all()
        if not all_firms.empty:
            # Filter for last 48 hours
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=2)
            recent_fires = all_firms[all_firms["acq_date"] >= cutoff].copy()
            
            if not recent_fires.empty and "frp" in recent_fires.columns:
                st.caption(f"Detected {len(recent_fires)} raw hotspots in Guna AOI since {cutoff.date()}")

                map_recent = recent_fires[["latitude","longitude","frp"]].rename(columns={"latitude":"lat","longitude":"lon"})
                recent_layer = pdk.Layer(
                    "ScatterplotLayer", data=map_recent,
                    get_position=["lon","lat"], get_radius="frp * 30 + 500",
                    get_fill_color=[255, 165, 0, 160], pickable=True,
                )
                
                boundary = load_boundary_geojson()
                layers_recent = [recent_layer]
                if boundary:
                    layers_recent.insert(0, pdk.Layer(
                        "GeoJsonLayer", data=boundary,
                        get_line_color=[255, 255, 255, 80], get_fill_color=[0,0,0,0],
                        line_width_min_pixels=1,
                    ))
                
                st.pydeck_chart(pdk.Deck(
                    layers=layers_recent,
                    initial_view_state=pdk.ViewState(latitude=24.4,longitude=77.15,zoom=8,pitch=0),
                    map_style="dark",
                    tooltip={"text": "Live Hotspot - FRP: {frp} MW"},
                ), height=400)
            else:
                st.info("No satellite hotspots detected in the last 48 hours.")
        else:
            st.info("No FIRMS data available.")

    # ── Messages & Tactical Dispatch ──────────────────────────────────────────
    if fires:
        st.divider()
        st.subheader("🛡️ Prescriptive AI Tactical Dispatch")
        
        for f in fires:
            with st.expander(f"Tactical Order for Fire at {f['fire_lat']:.3f}N, {f['fire_lon']:.3f} ({f['severity']})", expanded=(f['severity'] in ["CRITICAL", "HIGH"])):
                col_phys, col_order = st.columns([1, 2])
                
                # Physics Panel
                with col_phys:
                    pm = f.get("prescriptive_metrics", {})
                    if pm:
                        st.markdown("**Fire Physics**")
                        intensity = pm.get("intensity_kw_m", 0)
                        ros = pm.get("ros_m_min", 0)
                        
                        # Intensity Gauge (Color coded)
                        i_color = "#d73027" if intensity > 3460 else ("#fdae61" if intensity > 346 else "#74c476")
                        st.metric("Byram Intensity", f"{intensity:,.0f} kW/m", delta=pm.get("attack_mode"), delta_color="off")
                        st.metric("Rate of Spread", f"{ros:.2f} m/min")
                        
                        if intensity > 3460:
                            st.warning("🔥 EXTREME SURFACE FIRE — High heat radiation.")
                        
                        if pm.get("evacuation_trigger"):
                            st.error("⚠️ EVACUATION TRIGGERED")
                    else:
                        st.info("Physics metrics pending deep analysis.")

                # Tactical Order Panel
                with col_order:
                    order_text = f.get("tactical_order", "No tactical order generated.")
                    st.markdown("**Dispatch Order (Hindi/English)**")
                    
                    if AISignalCorps:
                        corps = AISignalCorps()
                        hindi_order = corps.translate_to_hindi(order_text)
                        _trans_method = "Gemini LLM" if corps._gemini_available else "Rule-based"
                    else:
                        hindi_order = order_text
                        _trans_method = "Unavailable"

                    st.code(hindi_order, language="text")
                    st.caption(f"Translation: {_trans_method} | AISignalCorps Dispatcher")

                    # ── NEW: Logistics & Acceleration Display ──
                    evac = f.get("evacuation_route", "No specific guidance generated.")
                    accel = f.get("acceleration_status", "Stable")
                    
                    l_col, a_col, s_col = st.columns(3)
                    with l_col:
                        st.markdown(f"🚩 **Evacuation:** {evac}")
                    with a_col:
                        a_clr = "#ef4444" if "ACCELERATING" in accel else "#22c55e"
                        st.markdown(f"📈 **Trend:** <span style='color:{a_clr}'>{accel}</span>", unsafe_allow_html=True)
                    with s_col:
                        # Real anomaly score from FRP percentile + FWI deviation
                        if compute_anomaly_score:
                            _anom = compute_anomaly_score(
                                frp_mw=f.get("frp_mw", 0),
                                fwi_value=fwi_val,
                                severity=f["severity"],
                                month=int(f.get("fire_date", "2025-04-01").split("-")[1]) if f.get("fire_date") else 4,
                                n_nearby_fires=len(fires),
                            )
                            anomaly_score = _anom["anomaly_score"]
                        else:
                            anomaly_score = min(1.0, f.get("frp_mw", 5) / 80.0)
                        st.markdown(f"🧠 **Anomaly Score:** {anomaly_score:.2f}")
                        st.caption(f"FRP percentile + FWI deviation")


                # ── VLM Autonomous Auditing Panel ──
                st.divider()
                st.markdown("🔍 **VLM Visual Audit (Autonomous)**")

                # Use real VLM Auditor (Gemini Vision if available, else heuristics)
                _frp = f.get("frp_mw", 0)
                _lc = f.get("land_cover", "unknown")
                if VLMAuditor:
                    _auditor = VLMAuditor()
                    _chip_path = ROOT / "outputs" / "chips" / f"chip_{f.get('fire_lat', 0):.4f}_{f.get('fire_lon', 0):.4f}.png"
                    audit_res = _auditor.audit_alert(
                        image_path=_chip_path,
                        alert_metadata={
                            "severity": f.get("severity", "MODERATE"),
                            "frp_mw": _frp,
                            "land_cover": _lc,
                            "lat": f.get("fire_lat", 0),
                            "lon": f.get("fire_lon", 0),
                        },
                    )
                    # Map VLM verdicts to display labels
                    _verdict_map = {"VALID": "CONFIRMED FIRE", "FALSE_POSITIVE": "AGRICULTURAL BURN", "AMBIGUOUS": "REQUIRES VERIFICATION"}
                    audit_res["verdict"] = _verdict_map.get(audit_res.get("verdict", ""), audit_res.get("verdict", "UNKNOWN"))
                    _method_label = "Gemini Vision" if audit_res.get("method") == "gemini_vision" else "Metadata Heuristics"
                else:
                    # Minimal fallback if VLMAuditor import failed
                    audit_res = {"verdict": "REQUIRES VERIFICATION", "confidence": 0.50,
                        "reasoning": f"VLM module unavailable. FRP={_frp:.1f} MW on {_lc}."}
                    _method_label = "Offline"

                v_col, r_col = st.columns([1, 3])
                with v_col:
                    _vrd = audit_res['verdict']
                    v_clr = "#22c55e" if "CONFIRMED" in _vrd else "#f59e0b" if "LIKELY" in _vrd else "#3b82f6" if "AGRI" in _vrd else "#ef4444"
                    st.markdown(f"<div style='text-align:center; padding:10px; border-radius:8px; background:{v_clr}20; border:1px solid {v_clr}40; color:{v_clr}; font-weight:bold;'>{_vrd}</div>", unsafe_allow_html=True)
                    st.caption(f"Confidence: {audit_res['confidence']*100:.0f}%")
                    st.caption(f"Method: {_method_label}")
                with r_col:
                    st.info(audit_res['reasoning'])

        st.subheader("Alert Messages")
        for f in fires:
            col_sev, col_msg = st.columns([1, 5])
            with col_sev:
                sev = f.get("severity", "UNKNOWN")
                st.markdown(sev_badge(sev), unsafe_allow_html=True)
            with col_msg:
                st.write(f.get("message", f"Fire at {f.get('fire_lat','?')}, {f.get('fire_lon','?')}"))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Fire History
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "\U0001f4ca Fire History":
    demo_narration_banner()
    st.header("\U0001f4ca FIRMS MODIS/VIIRS Fire Detection History (2013\u20132025)")
    st.caption("Source: Real NASA FIRMS MODIS SP + VIIRS NRT satellite detections for Guna Division")

    firms = load_firms_all()
    if firms.empty:
        empty_state(
            "&#128752;",
            "No FIRMS Fire Detection Data Available",
            "VIIRS SNPP fire detection data has not been downloaded yet.<br>"
            "Run <code>python scripts/download_firms.py</code> to fetch historical FIRMS data, "
            "or the data will populate automatically after the next NRT alert pipeline run."
        )
        st.stop()

    # ── Sidebar filters ───────────────────────────────────────────────────────
    col_yr, col_mon, col_conf = st.columns(3)
    with col_yr:
        years = sorted(firms["acq_date"].dt.year.unique())
        sel_years = st.multiselect("Year", years, default=years[-min(3, len(years)):])
    with col_mon:
        months = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                  7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        sel_months = st.multiselect("Month", list(months.keys()),
                                    format_func=lambda x: months[x],
                                    default=[3,4,5,6])
    with col_conf:
        conf_opts = firms["confidence"].unique().tolist()
        sel_conf = st.multiselect("VIIRS Confidence", conf_opts, default=conf_opts)

    filt = firms[
        firms["acq_date"].dt.year.isin(sel_years) &
        firms["acq_date"].dt.month.isin(sel_months) &
        firms["confidence"].isin(sel_conf)
    ].copy()

    if not sel_years or not sel_months or not sel_conf:
        st.warning("Select at least one option in each filter.")
        st.stop()

    st.caption(f"Showing {len(filt):,} of {len(firms):,} detections")

    # ── Map ───────────────────────────────────────────────────────────────────
    st.subheader("Detection Map")
    if not filt.empty and "frp" in filt.columns:
        map_df = filt[["latitude","longitude","frp"]].rename(
            columns={"latitude":"lat","longitude":"lon"})
        # Fire detection layer
        fire_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["lon", "lat"],
            get_radius="frp * 40 + 300",
            get_fill_color=[239, 68, 68, 200],
            pickable=True,
        )
        layers = [fire_layer]
        # Beat boundary overlay
        boundary = load_boundary_geojson()
        if boundary:
            boundary_layer = pdk.Layer(
                "GeoJsonLayer",
                data=boundary,
                get_line_color=[249, 115, 22, 120],
                get_fill_color=[0, 0, 0, 0],
                line_width_min_pixels=1,
                pickable=True,
            )
            layers.insert(0, boundary_layer)

        view = pdk.ViewState(latitude=24.4, longitude=77.15, zoom=8, pitch=0)
        _deck_history = pdk.Deck(
            layers=layers,
            initial_view_state=view,
            map_style="dark",
            tooltip={"text": "FRP: {frp} MW"},
        )
        st.pydeck_chart(_deck_history)
        fullscreen_map_button(_deck_history, "fire_history")

    # ── H3 Hexagonal Fire Density ────────────────────────────────────────────
    try:
        from src.utils.h3_index import add_h3_index, aggregate_to_h3
        import geopandas as _gpd
        from shapely.geometry import Point as _Point

        if not filt.empty and "latitude" in filt.columns:
            with st.expander("H3 Fire Density Heatmap", expanded=False):
                h3_res = st.select_slider(
                    "H3 Resolution", options=[5, 6, 7, 8, 9],
                    value=7, help="7=range-level (~5km²), 9=beat-level (~0.1km²)",
                    key="h3_res_slider",
                )
                _filt_gdf = _gpd.GeoDataFrame(
                    filt,
                    geometry=[_Point(lon, lat) for lon, lat in zip(filt["longitude"], filt["latitude"])],
                    crs="EPSG:4326",
                )
                h3_agg = aggregate_to_h3(_filt_gdf, resolution=h3_res, agg_col="frp", agg_func="mean")
                h3_agg["hex_coords"] = h3_agg.geometry.apply(
                    lambda g: list(g.exterior.coords) if g else []
                )
                h3_layer = pdk.Layer(
                    "PolygonLayer",
                    data=h3_agg,
                    get_polygon="hex_coords",
                    get_fill_color="[255, (1 - value/value.max()) * 255, 0, 140]",
                    get_line_color=[255, 255, 255, 80],
                    line_width_min_pixels=1,
                    pickable=True,
                    extruded=False,
                )
                st.pydeck_chart(pdk.Deck(
                    layers=[h3_layer],
                    initial_view_state=pdk.ViewState(latitude=24.4, longitude=77.15, zoom=8, pitch=0),
                    map_style="dark",
                    tooltip={"text": "Hex: {h3_res" + str(h3_res) + "}\nFires: {value}\nMean FRP: {value:.1f} MW"},
                ))
                st.caption(f"{len(h3_agg)} hexagons at resolution {h3_res}")
    except ImportError:
        pass  # h3 not installed — skip heatmap

    # ── Monthly heatmap ───────────────────────────────────────────────────────
    st.subheader("Annual Fire Counts by Month")
    try:
        import plotly.graph_objects as go

        pivot = (filt.assign(
                    year=filt["acq_date"].dt.year,
                    month=filt["acq_date"].dt.month)
                 .groupby(["year","month"]).size().unstack(fill_value=0))

        month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec"]
        z_data = [[pivot.loc[y, m] if m in pivot.columns else 0
                   for m in range(1,13)]
                  for y in sorted(pivot.index)]

        fig = go.Figure(go.Heatmap(
            z=z_data,
            x=month_labels,
            y=[str(y) for y in sorted(pivot.index)],
            colorscale="YlOrRd",
            colorbar=dict(title="Fires"),
        ))
        fig.update_layout(title="Fire Detections Heatmap (Year × Month)",
                          xaxis_title="Month", yaxis_title="Year",
                          height=400, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        # Annual total bar
        annual = filt.groupby(filt["acq_date"].dt.year).size().reset_index()
        annual.columns = ["year", "count"]
        fig2 = go.Figure(go.Bar(
            x=annual["year"], y=annual["count"],
            marker_color="#e34a33", text=annual["count"], textposition="outside",
        ))
        fig2.update_layout(title="Total Annual Fire Detections — Guna Division",
                           xaxis_title="Year", yaxis_title="Detections",
                           height=350, template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)

    except ImportError:
        st.info("Install plotly for charts: pip install plotly")
        fallback_cols = [c for c in ["acq_date","latitude","longitude","frp","confidence","daynight"]
                         if c in filt.columns]
        st.dataframe(filt[fallback_cols].sort_values("acq_date", ascending=False).head(200),
                     use_container_width=True)

    # ── Stats table ───────────────────────────────────────────────────────────
    with st.expander("Summary Statistics"):
        st.write(f"Total detections in filter: **{len(filt):,}**")
        col_a, col_b = st.columns(2)
        with col_a:
            if "confidence" in filt.columns:
                st.write("**By confidence:**")
                st.dataframe(filt["confidence"].value_counts().rename("count"),
                             use_container_width=True)
        with col_b:
            if "daynight" in filt.columns:
                st.write("**By day/night:**")
                st.dataframe(filt["daynight"].value_counts().rename("count"),
                             use_container_width=True)

    # ── Range Scorecard ────────────────────────────────────────────────────────
    st.subheader("\U0001f3af Range Scorecard")
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        range_dir = ROOT / "data" / "aoi"
        range_files = sorted(range_dir.glob("guna_range_*.geojson"))
        if range_files and not filt.empty:
            ranges_gdf = pd.concat(
                [gpd.read_file(f).assign(range_name=f.stem.replace("guna_range_", "").replace("_", " ").title())
                 for f in range_files],
                ignore_index=True,
            )
            fires_gdf = gpd.GeoDataFrame(
                filt,
                geometry=[Point(xy) for xy in zip(filt["longitude"], filt["latitude"])],
                crs="EPSG:4326",
            )
            joined = gpd.sjoin(fires_gdf, ranges_gdf, how="inner", predicate="within")

            scorecard_rows = []
            for rng in sorted(ranges_gdf["range_name"].unique()):
                rng_fires = joined[joined["range_name"] == rng]
                count = len(rng_fires)
                peak_frp = rng_fires["frp"].max() if not rng_fires.empty and "frp" in rng_fires.columns else 0
                last_date = rng_fires["acq_date"].max() if not rng_fires.empty else None
                if count >= 20:
                    risk = "\U0001f534 High"
                elif count >= 5:
                    risk = "\U0001f7e0 Medium"
                else:
                    risk = "\U0001f7e2 Low"
                scorecard_rows.append({
                    "Range": rng,
                    "Fire Count": count,
                    "Peak FRP (MW)": f"{peak_frp:.1f}" if peak_frp and not pd.isna(peak_frp) else "\u2014",
                    "Last Fire": str(last_date.date()) if last_date and not pd.isna(last_date) else "\u2014",
                    "Risk Level": risk,
                })
            sc_df = pd.DataFrame(scorecard_rows)
            st.dataframe(sc_df, use_container_width=True, hide_index=True)
        else:
            st.info("Range GeoJSON files not found or no fire data in filter.")
    except ImportError:
        st.info("Install geopandas for range scorecard: pip install geopandas")
    except Exception as e:
        st.warning(f"Range scorecard unavailable: {e}")

    # ── Download Fire History ──────────────────────────────────────────────────
    st.divider()
    export_cols = [c for c in ["acq_date","latitude","longitude","frp","confidence","daynight"]
                   if c in filt.columns]
    st.download_button(
        "\U0001f4e5 Download Fire History CSV",
        data=filt[export_cols].to_csv(index=False),
        file_name="fire_history_guna.csv",
        mime="text/csv",
        key="dl_fire_csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: Burn Scars
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "\U0001f6f0\ufe0f Burn Scars":
    demo_narration_banner()
    st.header("\U0001f6f0\ufe0f Prithvi-EO-2.0 Burn Scar Analysis")

    links = load_fire_links()
    if links.empty:
        empty_state(
            "&#127755;",
            "No Burn Scar Data Available",
            "Prithvi-EO-2.0 burn scar analysis has not been run yet.<br>"
            "Run <code>python scripts/link_fires_to_burnscars.py</code> to process "
            "satellite imagery and link burn scars to FIRMS fire detections."
        )
        st.stop()

    # ── Summary metrics ───────────────────────────────────────────────────────
    total = len(links)
    matched = links[links["fire_date"].notna()]
    spatial = links[links["spatial_hit"] == True]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metric_card("Burn Scar Scenes", total, "processed by Prithvi", "#e34a33", icon="\U0001f6f0\ufe0f")
    with m2:
        metric_card("FIRMS Matched", len(matched),
                    f"{100*len(matched)/max(total,1):.0f}% match rate", "#fc8d59", icon="\U0001f525")
    with m3:
        metric_card("Spatial Hits", len(spatial),
                    f"{100*len(spatial)/max(total,1):.0f}% (fire ON burned pixel)", "#fd8d3c", icon="\U0001f4cd")
    with m4:
        peak = matched["fire_frp_mw"].dropna().max() if not matched.empty else 0
        metric_card("Peak FRP", f"{peak:.1f} MW", "highest confirmed fire", "#d73027", icon="\u26a1")

    # ── Confidence breakdown ──────────────────────────────────────────────────
    st.subheader("Causal Link Confidence")
    try:
        import plotly.express as px
        conf_counts = links["confidence"].value_counts().reset_index()
        conf_counts.columns = ["confidence","count"]
        conf_order = ["HIGH","MEDIUM-HIGH","MEDIUM","LOW-MEDIUM","LOW","NONE"]
        conf_colors = {"HIGH":"#d73027","MEDIUM-HIGH":"#f46d43",
                       "MEDIUM":"#fdae61","LOW-MEDIUM":"#fee08b",
                       "LOW":"#a6d96a","NONE":"#aaa"}
        conf_counts["confidence"] = pd.Categorical(
            conf_counts["confidence"], categories=conf_order, ordered=True)
        conf_counts = conf_counts.sort_values("confidence")

        fig = px.bar(conf_counts, x="confidence", y="count",
                     color="confidence",
                     color_discrete_map=conf_colors,
                     title="Burn Scar Scenes by Causal Link Confidence",
                     template="plotly_dark")
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.dataframe(links["confidence"].value_counts(), use_container_width=True)

    # ── HIGH/MEDIUM-HIGH events ───────────────────────────────────────────────
    st.subheader("HIGH & MEDIUM-HIGH Confidence Fire Events")
    high = links[links["confidence"].isin(["HIGH","MEDIUM-HIGH"])].copy()
    if not high.empty:
        display = high[[
            "scene_date","tile","burn_area_ha","fire_date",
            "fire_time_ist","fire_frp_mw","daynight",
            "dist_to_burn_m","days_gap","confidence"
        ]].sort_values("scene_date", ascending=False)
        st.dataframe(display.style.map(
            lambda v: "background-color:#d73027;color:white"
            if v == "HIGH" else
            ("background-color:#f46d43;color:white" if v == "MEDIUM-HIGH" else ""),
            subset=["confidence"]
        ), use_container_width=True, height=400)

    # ── Burn area time series ─────────────────────────────────────────────────
    try:
        import plotly.graph_objects as go
        st.subheader("Burn Area Over Time")
        plot_df = links[links["burn_area_ha"] > 0].copy()
        plot_df["scene_date"] = pd.to_datetime(plot_df["scene_date"])

        fig = go.Figure()
        for conf, color in [("HIGH","#d73027"),("MEDIUM-HIGH","#f46d43"),
                            ("MEDIUM","#fdae61"),("LOW","#a6d96a")]:
            sub = plot_df[plot_df["confidence"]==conf]
            if not sub.empty:
                fig.add_trace(go.Scatter(
                    x=sub["scene_date"], y=sub["burn_area_ha"],
                    mode="markers", name=conf,
                    marker=dict(color=color, size=8, opacity=0.8),
                    hovertemplate="%{x}<br>%{y:.0f} ha<extra></extra>",
                ))
        fig.update_layout(title="Burn Scar Area vs Scene Date",
                          xaxis_title="Scene Date", yaxis_title="Burn Area (ha)",
                          height=400, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        pass

    # ── Full table ────────────────────────────────────────────────────────────
    with st.expander("Full burn scar catalog"):
        st.dataframe(links.sort_values("scene_date", ascending=False),
                     use_container_width=True, height=400)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: FWI Trends
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "\U0001f321\ufe0f FWI Trends":
    demo_narration_banner()
    st.header("\U0001f321\ufe0f Fire Weather Index \u2014 Guna Division (2013\u20132025)")

    fwi_df = load_fwi()
    if fwi_df.empty:
        st.warning("FWI data not found. Run scripts/compute_fwi.py first.")
        st.stop()

    # ── Overall stats ─────────────────────────────────────────────────────────
    fire_szn = fwi_df[fwi_df["date"].dt.month.isin([3,4,5,6])]
    extreme  = (fwi_df["fwi"] >= 38).sum()
    vh_plus  = (fwi_df["fwi"] >= 21.3).sum()

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        metric_card("Peak FWI (all time)", f"{fwi_df['fwi'].max():.1f}",
                    str(fwi_df.loc[fwi_df['fwi'].idxmax(),'date'].date()),
                    "#d73027", icon="\U0001f321\ufe0f")
    with s2:
        metric_card("Fire Season Mean", f"{fire_szn['fwi'].mean():.1f}",
                    "Mar-Jun average", "#f46d43", icon="\U0001f525")
    with s3:
        metric_card("Extreme days", int(extreme),
                    f"{100*extreme/len(fwi_df):.1f}% of all days", "#d73027", icon="\u26a0\ufe0f")
    with s4:
        metric_card("Very High+ days", int(vh_plus),
                    f"{100*vh_plus/len(fwi_df):.1f}% of all days", "#f46d43", icon="\U0001f4c8")

    try:
        import plotly.graph_objects as go
        import plotly.express as px

        # ── Annual peak FWI bar chart ─────────────────────────────────────
        st.subheader("Annual Peak FWI (Fire Season: Mar-Jun)")
        annual_peak = (fire_szn.assign(year=fire_szn["date"].dt.year)
                       .groupby("year")["fwi"].max().reset_index())

        def bar_color(v):
            if v >= 38:   return "#d73027"
            if v >= 21.3: return "#f46d43"
            if v >= 11.2: return "#fdae61"
            return "#a6d96a"

        fig = go.Figure(go.Bar(
            x=annual_peak["year"],
            y=annual_peak["fwi"],
            marker_color=[bar_color(v) for v in annual_peak["fwi"]],
            text=annual_peak["fwi"].round(1),
            textposition="outside",
        ))
        fig.add_hline(y=38,   line_dash="dash", line_color="#d73027",
                      annotation_text="Extreme (38)")
        fig.add_hline(y=21.3, line_dash="dash", line_color="#f46d43",
                      annotation_text="Very High (21.3)")
        fig.update_layout(xaxis_title="Year", yaxis_title="Peak FWI",
                          height=400, template="plotly_dark",
                          yaxis=dict(range=[0, annual_peak["fwi"].max()*1.15]))
        st.plotly_chart(fig, use_container_width=True)

        # ── Monthly heatmap ───────────────────────────────────────────────
        st.subheader("Mean Monthly FWI (Year x Month)")
        fwi_df2 = fwi_df.assign(year=fwi_df["date"].dt.year,
                                 month=fwi_df["date"].dt.month)
        pivot = fwi_df2.groupby(["year","month"])["fwi"].mean().unstack(fill_value=0)
        month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec"]
        years = sorted(pivot.index)
        z = [[pivot.loc[y, m] if m in pivot.columns else 0
              for m in range(1,13)] for y in years]

        fig2 = go.Figure(go.Heatmap(
            z=z, x=month_labels, y=[str(y) for y in years],
            colorscale="YlOrRd", colorbar=dict(title="Mean FWI"),
            zmin=0, zmax=60,
        ))
        fig2.update_layout(title="Mean Monthly FWI (2013-2025)",
                           height=420, template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)

        # ── FWI × Fire Correlation ───────────────────────────────────────
        st.subheader("\U0001f525 FWI \u00d7 Fire Detection Correlation")
        firms_all = load_firms_all()
        if not firms_all.empty:
            firms_monthly = (firms_all
                .assign(ym=firms_all["acq_date"].dt.to_period("M"))
                .groupby("ym").size()
                .reset_index(name="fire_count"))
            firms_monthly["date"] = firms_monthly["ym"].dt.to_timestamp()

            fwi_monthly = (fwi_df
                .assign(ym=fwi_df["date"].dt.to_period("M"))
                .groupby("ym")["fwi"].mean()
                .reset_index())
            fwi_monthly["date"] = fwi_monthly["ym"].dt.to_timestamp()

            merged = pd.merge(fwi_monthly, firms_monthly, on="date", how="outer").fillna(0)
            merged = merged.sort_values("date")

            from plotly.subplots import make_subplots
            fig_corr = make_subplots(specs=[[{"secondary_y": True}]])
            fig_corr.add_trace(
                go.Scatter(x=merged["date"], y=merged["fwi"],
                           name="Mean FWI", line=dict(color="#f46d43", width=2)),
                secondary_y=False,
            )
            fig_corr.add_trace(
                go.Bar(x=merged["date"], y=merged["fire_count"],
                       name="Fire Detections", marker_color="rgba(231,76,60,0.5)"),
                secondary_y=True,
            )
            fig_corr.update_layout(
                title="Monthly FWI vs Fire Detections \u2014 Guna Division",
                height=420, template="plotly_dark",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            fig_corr.update_yaxes(title_text="Mean FWI", secondary_y=False)
            fig_corr.update_yaxes(title_text="Fire Detections", secondary_y=True)
            st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.info("FIRMS data not available for correlation chart.")

        # ── Daily FWI time series (selected year) ─────────────────────────
        st.subheader("Daily FWI Time Series")
        sel_year = st.selectbox("Select year", sorted(fwi_df["date"].dt.year.unique(),
                                                       reverse=True))
        yr_df = fwi_df[fwi_df["date"].dt.year == sel_year]

        fig3 = go.Figure()
        # Danger bands
        fig3.add_hrect(y0=38,   y1=100,  fillcolor="#d73027", opacity=0.12, line_width=0)
        fig3.add_hrect(y0=21.3, y1=38,   fillcolor="#f46d43", opacity=0.12, line_width=0)
        fig3.add_hrect(y0=11.2, y1=21.3, fillcolor="#fdae61", opacity=0.12, line_width=0)
        fig3.add_hrect(y0=5,    y1=11.2, fillcolor="#a6d96a", opacity=0.12, line_width=0)

        fig3.add_trace(go.Scatter(
            x=yr_df["date"], y=yr_df["fwi"],
            fill="tozeroy", mode="lines",
            line=dict(color="#e34a33", width=1.5),
            name="FWI",
        ))
        fig3.add_hline(y=38,   line_dash="dash", line_color="#d73027", line_width=1)
        fig3.add_hline(y=21.3, line_dash="dash", line_color="#f46d43", line_width=1)
        fig3.update_layout(xaxis_title="Date", yaxis_title="FWI",
                           height=380, template="plotly_dark",
                           annotations=[
                               dict(x=0.01, y=50, xref="paper", text="Extreme", showarrow=False,
                                    font=dict(color="#d73027", size=11)),
                               dict(x=0.01, y=29, xref="paper", text="Very High", showarrow=False,
                                    font=dict(color="#f46d43", size=11)),
                           ])
        st.plotly_chart(fig3, use_container_width=True)

        # ── Top 20 FWI days ───────────────────────────────────────────────
        with st.expander("Top 20 Highest FWI Days (2013-2025)"):
            top20 = fwi_df.nlargest(20,"fwi")[
                ["date","temp_c","rh_pct","wind_kmh","precip_mm","fwi","danger_class"]
            ]
            st.dataframe(top20, use_container_width=True)

    except ImportError:
        st.info("Install plotly: pip install plotly")
        st.dataframe(fwi_df.tail(30), use_container_width=True)

    # ── Download FWI Data ──────────────────────────────────────────────────────
    st.divider()
    fwi_export_cols = [c for c in ["date","temp_c","rh_pct","wind_kmh","precip_mm","fwi","danger_class"]
                       if c in fwi_df.columns]
    st.download_button(
        "\U0001f4e5 Download FWI Data CSV",
        data=fwi_df[fwi_export_cols].to_csv(index=False),
        file_name="fwi_guna_division.csv",
        mime="text/csv",
        key="dl_fwi_csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 6: Weather & Terrain
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "\u26f0\ufe0f Weather & Terrain":
    demo_narration_banner()
    st.header("\u26f0\ufe0f Weather Forecasts & Terrain Analysis \u2014 Guna Division")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION A: GFS Weather Forecast
    # ══════════════════════════════════════════════════════════════════════════
    st.subheader("GFS NWP Weather Forecast")

    col_wdate, col_wrun = st.columns([2, 1])
    with col_wdate:
        wx_date = st.date_input("Forecast run date", value=date.today(),
                                min_value=date(2024, 1, 1), max_value=date.today(),
                                key="wx_date")
    with col_wrun:
        st.write("")
        if st.button("Download GFS Forecast", type="primary"):
            with st.spinner("Fetching GFS 24/48/72 h forecasts via Herbie ..."):
                import subprocess, sys
                result = subprocess.run(
                    [sys.executable, "-m", "src.data.weather_ingest",
                     "--date", str(wx_date), "--leads", "24", "48", "72",
                     "--subset-bbox"],
                    capture_output=True, text=True, cwd=str(ROOT)
                )
            st.cache_data.clear()
            if result.returncode == 0:
                st.success("GFS forecast downloaded!")
            else:
                st.error(f"Download error:\n{result.stderr[:400]}")

    gfs_df = load_gfs_forecast(wx_date)

    if not gfs_df.empty:
        # ── Forecast metrics at each lead time ────────────────────────────────
        leads = gfs_df["lead_h"].tolist()
        cols  = st.columns(len(leads))
        for col, (_, row) in zip(cols, gfs_df.iterrows()):
            with col:
                st.markdown(f"**+{int(row['lead_h'])} h forecast**")
                if "temp_c"    in row: metric_card("Temperature", f"{row['temp_c']:.1f}\u00b0C",   color="#fd8d3c", icon="\U0001f321\ufe0f")
                if "rh_pct"    in row: metric_card("Rel. Humidity", f"{row['rh_pct']:.1f}%",  color="#6baed6", icon="\U0001f4a7")
                if "wind_kmh"  in row: metric_card("Wind", f"{row['wind_kmh']:.1f} km/h",     color="#74c476", icon="\U0001f4a8")
                if "precip_mm" in row: metric_card("Precip.", f"{row['precip_mm']:.2f} mm",   color="#4393c3", icon="\U0001f327\ufe0f")

        # ── Forecast trend chart ──────────────────────────────────────────────
        try:
            import plotly.graph_objects as go
            fig = go.Figure()
            if "temp_c" in gfs_df.columns:
                fig.add_trace(go.Scatter(x=gfs_df["lead_h"], y=gfs_df["temp_c"],
                                         name="Temp (°C)", line=dict(color="#fd8d3c")))
            if "rh_pct" in gfs_df.columns:
                fig.add_trace(go.Scatter(x=gfs_df["lead_h"], y=gfs_df["rh_pct"],
                                         name="RH (%)", line=dict(color="#6baed6"),
                                         yaxis="y2"))
            if "wind_kmh" in gfs_df.columns:
                fig.add_trace(go.Scatter(x=gfs_df["lead_h"], y=gfs_df["wind_kmh"],
                                         name="Wind (km/h)", line=dict(color="#74c476",
                                         dash="dash")))
            fig.update_layout(
                title=f"GFS Fire-Weather Forecast — Guna Division ({wx_date})",
                xaxis_title="Lead time (hours)",
                yaxis=dict(title="Temp (°C) / Wind (km/h)"),
                yaxis2=dict(title="Relative Humidity (%)", overlaying="y", side="right",
                            range=[0, 100]),
                height=380, template="plotly_dark", legend=dict(orientation="h"),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Precipitation bar
            if "precip_mm" in gfs_df.columns and gfs_df["precip_mm"].sum() > 0:
                fig2 = go.Figure(go.Bar(x=gfs_df["lead_h"], y=gfs_df["precip_mm"],
                                        marker_color="#4393c3", name="Precipitation"))
                fig2.update_layout(title="Accumulated Precipitation Forecast (mm)",
                                   xaxis_title="Lead time (h)", yaxis_title="mm",
                                   height=250, template="plotly_dark")
                st.plotly_chart(fig2, use_container_width=True)
        except ImportError:
            st.dataframe(gfs_df, use_container_width=True)

    else:
        empty_state(
            "&#9925;",
            f"No GFS Forecast for {wx_date}",
            f"Click <strong>Download GFS Forecast</strong> above to fetch 24/48/72 h NWP data via Herbie.<br>"
            f"Data will be saved to <code>data_lake/weather_forecasts/gfs/{wx_date}/</code>"
        )
        # Show the weather variables that will be downloaded
        with st.expander("Variables fetched from GFS 0.25°"):
            st.markdown("""
| Variable | GRIB pattern | Derived |
|----------|-------------|---------|
| Temperature at 2 m | `TMP:2 m above ground` | → °C |
| Relative Humidity at 2 m | `RH:2 m above ground` | % |
| U-wind at 10 m | `UGRD:10 m above ground` | → wind speed (km/h) |
| V-wind at 10 m | `VGRD:10 m above ground` | → wind direction |
| Total Precipitation | `APCP:surface` | → mm |
            """)

    # Show historical weather from FWI parquet as fallback
    fwi_df_wx = load_fwi()
    if not fwi_df_wx.empty:
        st.divider()
        st.subheader("Historical Fire-Weather Climatology (2013–2025)")
        st.caption("Source: NASA POWER reanalysis — same variables used for Canadian FWI computation")

        months_wx = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                     7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        monthly = (fwi_df_wx.assign(month=fwi_df_wx["date"].dt.month)
                   .groupby("month")[["temp_c","rh_pct","wind_kmh","precip_mm"]].mean()
                   .reset_index())
        monthly["month_name"] = monthly["month"].map(months_wx)

        try:
            import plotly.graph_objects as go
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(x=monthly["month_name"], y=monthly["temp_c"],
                                   name="Mean Temp (°C)", marker_color="#fd8d3c",
                                   yaxis="y"))
            fig3.add_trace(go.Scatter(x=monthly["month_name"], y=monthly["rh_pct"],
                                       name="Mean RH (%)", line=dict(color="#6baed6"),
                                       yaxis="y2", mode="lines+markers"))
            fig3.update_layout(
                title="Mean Monthly Temperature & Relative Humidity — Guna Division",
                xaxis_title="Month",
                yaxis=dict(title="Temperature (°C)", range=[0, 45]),
                yaxis2=dict(title="Relative Humidity (%)", overlaying="y", side="right",
                            range=[0, 100]),
                height=360, template="plotly_dark",
                legend=dict(orientation="h"),
            )
            st.plotly_chart(fig3, use_container_width=True)

            fig4 = go.Figure()
            fig4.add_trace(go.Bar(x=monthly["month_name"], y=monthly["wind_kmh"],
                                   name="Wind Speed (km/h)", marker_color="#74c476"))
            fig4.add_trace(go.Bar(x=monthly["month_name"], y=monthly["precip_mm"],
                                   name="Precipitation (mm)", marker_color="#4393c3",
                                   yaxis="y2"))
            fig4.update_layout(
                title="Mean Monthly Wind Speed & Precipitation — Guna Division",
                xaxis_title="Month",
                yaxis=dict(title="Wind (km/h)"),
                yaxis2=dict(title="Precipitation (mm/day)", overlaying="y", side="right"),
                barmode="group", height=320, template="plotly_dark",
                legend=dict(orientation="h"),
            )
            st.plotly_chart(fig4, use_container_width=True)
        except ImportError:
            st.dataframe(monthly, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION B: Terrain Analysis
    # ══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("Terrain Analysis — Copernicus DEM 30 m")

    terrain = load_terrain_stats()

    if not terrain:
        empty_state(
            "&#9968;",
            "Terrain Data Not Available",
            "Run <code>python scripts/fetch_dem.py</code> to download the Copernicus DEM 30m "
            "and compute slope, aspect, and terrain fire-risk layers for Guna Division."
        )
        with st.expander("What terrain layers are generated?"):
            st.markdown("""
| Layer | File | Description |
|-------|------|-------------|
| Elevation | `dem_guna_clipped.tif` | Copernicus DEM 30m (m a.s.l.) |
| Slope | `slope_guna_30m.tif` | Degrees — fire spread doubles per 10° |
| Aspect | `aspect_guna_30m.tif` | Compass bearing (N=0°, S=180°) |
| Terrain Risk | `terrain_risk_guna.tif` | 0=Low / 1=Moderate / 2=High / 3=Extreme |
            """)
        with st.expander("Why does terrain matter for fire alerts?"):
            st.markdown("""
- **Slope**: Fire spread rate approximately doubles for each 10° of slope.
  A 30° slope can drive flames 8× faster than flat ground.
- **Aspect**: South-facing slopes (S/SW) receive more solar radiation,
  drying out fuel — fires ignite more easily and burn hotter.
- **Elevation**: Higher ground is cooler and wetter; fire risk drops above 700 m.
  The Vindhya ranges in southern Guna (400-600 m) concentrate risk.
            """)
    else:
        e = terrain.get("elevation_m",     {})
        s = terrain.get("slope_deg",       {})
        r = terrain.get("terrain_risk_pct",{})
        asp = terrain.get("aspect_octants_pct", {})

        # ── Elevation summary ─────────────────────────────────────────────────
        tm1, tm2, tm3, tm4 = st.columns(4)
        with tm1:
            metric_card("Min Elevation",  f"{e.get('min',0):.0f} m",  color="#4393c3", icon="\u26f0\ufe0f")
        with tm2:
            metric_card("Max Elevation",  f"{e.get('max',0):.0f} m",  color="#4393c3", icon="\u26f0\ufe0f")
        with tm3:
            metric_card("Mean Elevation", f"{e.get('mean',0):.0f} m", color="#4393c3", icon="\u26f0\ufe0f")
        with tm4:
            metric_card("Steep (>=30°)", f"{s.get('pct_ge_30',0):.1f}%",
                        "of district area", "#f46d43")

        try:
            import plotly.graph_objects as go
            import plotly.express as px

            tc1, tc2 = st.columns(2)

            # ── Terrain risk donut ─────────────────────────────────────────────
            with tc1:
                risk_labels = [
                    "Low (flat/N-facing)",
                    "Moderate (S-facing)",
                    "High (steep)",
                    "Extreme (steep+S)",
                ]
                risk_vals = [
                    r.get("flat_low", 0),
                    r.get("south_facing_mod", 0),
                    r.get("steep_high", 0),
                    r.get("steep_south_extreme", 0),
                ]
                risk_colors = ["#1a9641", "#fdae61", "#f46d43", "#d73027"]
                fig_r = go.Figure(go.Pie(
                    labels=risk_labels, values=risk_vals,
                    marker_colors=risk_colors, hole=0.38,
                    textinfo="percent+label",
                ))
                fig_r.update_layout(
                    title="Terrain Fire-Risk Distribution",
                    height=380, template="plotly_dark", showlegend=False,
                )
                st.plotly_chart(fig_r, use_container_width=True)

            # ── Aspect rose diagram ────────────────────────────────────────────
            with tc2:
                asp_labels = list(asp.keys())
                asp_vals   = list(asp.values())
                fig_a = go.Figure(go.Barpolar(
                    r=asp_vals,
                    theta=[0, 45, 90, 135, 180, 225, 270, 315],
                    width=[45] * 8,
                    marker_color=[
                        "#74c476",  # N  — low risk
                        "#a6d96a",  # NE
                        "#fdae61",  # E
                        "#f46d43",  # SE — higher risk
                        "#d73027",  # S  — highest risk (south-facing)
                        "#d73027",  # SW — highest risk
                        "#fdae61",  # W
                        "#a6d96a",  # NW
                    ],
                    opacity=0.85,
                ))
                fig_a.update_layout(
                    title="Aspect Distribution (% of area)",
                    polar=dict(
                        angularaxis=dict(
                            direction="clockwise",
                            tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                            ticktext=["N","NE","E","SE","S","SW","W","NW"],
                        ),
                        radialaxis=dict(visible=True),
                    ),
                    height=380, template="plotly_dark",
                )
                st.plotly_chart(fig_a, use_container_width=True)

            # ── Slope class bar ────────────────────────────────────────────────
            slope_classes = ["0-5°\n(flat)", "5-15°\n(gentle)", "15-30°\n(moderate)",
                             ">30°\n(steep)"]
            pct_ge_5 = s.get("pct_ge_5", s.get("pct_ge_15", 0))
            slope_pcts = [
                max(0, 100 - pct_ge_5),
                max(0, pct_ge_5 - s.get("pct_ge_15", 0)),
                max(0, s.get("pct_ge_15", 0) - s.get("pct_ge_30", 0)),
                s.get("pct_ge_30", 0),
            ]
            slope_colors = ["#1a9641", "#a6d96a", "#f46d43", "#d73027"]
            fig_s = go.Figure(go.Bar(
                x=slope_classes, y=slope_pcts,
                marker_color=slope_colors, text=[f"{v:.1f}%" for v in slope_pcts],
                textposition="outside",
            ))
            fig_s.update_layout(
                title="Slope Class Distribution — Guna Division",
                xaxis_title="Slope Class", yaxis_title="% of District Area",
                height=320, template="plotly_dark",
                yaxis=dict(range=[0, max(slope_pcts) * 1.2]),
            )
            st.plotly_chart(fig_s, use_container_width=True)

        except ImportError:
            st.info("Install plotly for charts.")
            st.json(terrain)

        # ── Fire-terrain risk key ──────────────────────────────────────────────
        st.info(
            f"**Fire-terrain risk summary for Guna Division:**  \n"
            f"- **{r.get('steep_south_extreme',0):.1f}%** of the district has *extreme* terrain risk "
            f"(steep slope + south-facing aspect)  \n"
            f"- **{r.get('steep_high',0):.1f}%** has *high* risk (steep only)  \n"
            f"- Mean slope is **{s.get('mean',0):.1f}°**; "
            f"**{s.get('pct_ge_30',0):.1f}%** exceeds the critical 30° threshold  \n"
            f"- Elevation range: **{e.get('min',0):.0f}–{e.get('max',0):.0f} m** "
            f"(Vindhya ranges in the south are the highest-risk zone)"
        )

        # ── Terrain data file status ───────────────────────────────────────────
        with st.expander("Terrain data files"):
            terrain_files = {
                "DEM (clipped)":    TERRAIN_DIR / "dem_guna_clipped.tif",
                "Slope (30m)":      TERRAIN_DIR / "slope_guna_30m.tif",
                "Aspect (30m)":     TERRAIN_DIR / "aspect_guna_30m.tif",
                "Terrain risk":     TERRAIN_DIR / "terrain_risk_guna.tif",
                "Terrain stats":    TERRAIN_DIR / "terrain_stats.json",
            }
            for name, path in terrain_files.items():
                exists = path.exists()
                size   = f"{path.stat().st_size/1024:.0f} KB" if exists else "—"
                st.write(f"{'✅' if exists else '❌'} **{name}** — `{path.name}` ({size})")

    # ── NEW: Virtual Sensor Network Health (Maintenance AI) ──
    st.divider()
    st.subheader("🛰️ Virtual Sensor Network Health")
    st.markdown("""
    The AI guardian monitors the health of the 10-year **Virtual Sensor Network (VSN)** nodes
    to ensure data integrity and prevent sensor-drift false positives.
    """)
    
    try:
        from src.analysis.maintenance_ai import MaintenanceAI
        mai = MaintenanceAI()
        
        # We simulate health checks for 4 key nodes
        nodes = ["NORTH_GUNA_01", "BAMORI_RIDGE_04", "SOUTH_RANGE_09", "VALLEY_STATION_02"]
        # Simulated recent temperatures
        temps = [38.5, 42.1, 65.4, 39.2] 
        
        cols = st.columns(4)
        for i, node in enumerate(nodes):
            status = mai.ingest_telemetry(node, temps[i])
            with cols[i]:
                s_clr = "#22c55e" if status.status == "HEALTHY" else ("#f59e0b" if status.status == "DRIFT_DETECTED" else "#ef4444")
                st.markdown(f"""
                <div style='background:var(--bg-card); border:1px solid var(--border); border-radius:8px; padding:12px; border-top:3px solid {s_clr}'>
                    <div style='font-size:10px; color:var(--text-muted);'>{node}</div>
                    <div style='font-size:18px; font-weight:700; color:{s_clr}'>{status.status}</div>
                    <div style='font-size:11px; margin-top:4px;'>{status.message}</div>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Maintenance AI offline: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 7: Land Cover
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "\U0001f333 Land Cover":
    demo_narration_banner()
    st.header("\U0001f333 Land Cover \u2014 Guna Division (ESA WorldCover 2021)")
    st.caption("Source: ESA WorldCover 10m classification + India State of Forest Report reference data")

    stats = load_lc_stats()
    if not stats:
        empty_state(
            "&#127795;",
            "No Land Cover Data Available",
            "ESA WorldCover 2021 land cover stats have not been generated yet.<br>"
            "Run <code>python scripts/fetch_forest_boundary.py</code> to download "
            "WorldCover tiles and compute land cover statistics for Guna Division."
        )
        st.stop()

    summary = stats.get("_summary", {})

    # ── Summary metrics ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metric_card("Total District Area",
                    f"{summary.get('total_area_ha',0)/100:,.0f} km\u00b2",
                    f"{summary.get('total_area_ha',0):,.0f} ha", "#4393c3", icon="\U0001f4d0")
    with m2:
        metric_card("Forest Cover",
                    f"{summary.get('forest_pct',0):.1f}%",
                    f"{summary.get('forest_ha',0):,.0f} ha (Tree cover)", "#1a9641", icon="\U0001f333")
    with m3:
        metric_card("Agriculture",
                    f"{100*summary.get('agriculture_ha',0)/max(summary.get('total_area_ha',1),1):.1f}%",
                    f"{summary.get('agriculture_ha',0):,.0f} ha (Cropland)", "#fc8d59", icon="\U0001f33e")
    with m4:
        metric_card("Scrubland",
                    f"{100*summary.get('scrub_ha',0)/max(summary.get('total_area_ha',1),1):.1f}%",
                    f"{summary.get('scrub_ha',0):,.0f} ha", "#74c476", icon="\U0001f33f")

    # ── Pie chart ─────────────────────────────────────────────────────────────
    try:
        import plotly.express as px

        lc_rows = [(v["label"], v["area_ha"]) for k, v in stats.items()
                   if k != "_summary" and v.get("area_ha", 0) > 0]
        lc_df = pd.DataFrame(lc_rows, columns=["Land Cover", "Area (ha)"])

        color_map = {
            "Tree cover": "#1a9641",
            "Shrubland":  "#78c679",
            "Grassland":  "#c2e699",
            "Cropland":   "#f46d43",
            "Built-up":   "#d7191c",
            "Bare/sparse veg": "#d9d9d9",
            "Water":      "#4393c3",
            "Wetland":    "#abd9e9",
        }

        fig = px.pie(lc_df, names="Land Cover", values="Area (ha)",
                     color="Land Cover",
                     color_discrete_map=color_map,
                     title="Land Cover Composition — Guna Division",
                     hole=0.35)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=500, template="plotly_dark",
                          showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

        # ── Bar chart ──────────────────────────────────────────────────────
        lc_df_sorted = lc_df.sort_values("Area (ha)", ascending=True)
        fig2 = px.bar(lc_df_sorted, x="Area (ha)", y="Land Cover",
                      orientation="h", color="Land Cover",
                      color_discrete_map=color_map,
                      title="Land Cover Area Breakdown (ha)",
                      template="plotly_dark")
        fig2.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig2, use_container_width=True)

    except ImportError:
        st.info("Install plotly: pip install plotly")
        for k, v in stats.items():
            if k != "_summary" and v.get("area_ha", 0) > 0:
                st.write(f"**{v['label']}**: {v['area_ha']:,.0f} ha ({v['pct_of_area']}%)")

    # ── Fire-Land Cover Overlap ────────────────────────────────────────────────
    st.subheader("\U0001f525 Fire Detections by Land Cover Type")
    try:
        import rasterio
        from rasterio.transform import rowcol
        import plotly.express as px

        wc_path = ROOT / "data_lake" / "land_cover" / "worldcover_guna_raw.tif"
        firms_all = load_firms_all()
        if wc_path.exists() and not firms_all.empty:
            with rasterio.open(wc_path) as src:
                wc_data = src.read(1)
                wc_transform = src.transform
                wc_bounds = src.bounds

            # Filter fires within raster bounds
            in_bounds = firms_all[
                (firms_all["latitude"] >= wc_bounds.bottom) &
                (firms_all["latitude"] <= wc_bounds.top) &
                (firms_all["longitude"] >= wc_bounds.left) &
                (firms_all["longitude"] <= wc_bounds.right)
            ]
            if not in_bounds.empty:
                rows, cols = rowcol(wc_transform, in_bounds["longitude"].values, in_bounds["latitude"].values)
                rows = np.clip(rows, 0, wc_data.shape[0] - 1)
                cols = np.clip(cols, 0, wc_data.shape[1] - 1)
                lc_vals = wc_data[rows, cols]

                esa_labels = {
                    10: "Tree cover", 20: "Shrubland", 30: "Grassland",
                    40: "Cropland", 50: "Built-up", 60: "Bare/sparse",
                    80: "Water", 90: "Wetland", 95: "Mangroves",
                }
                lc_names = [esa_labels.get(v, f"Class {v}") for v in lc_vals]
                overlap_df = pd.Series(lc_names).value_counts().reset_index()
                overlap_df.columns = ["Land Cover", "Fire Count"]

                lc_colors = {
                    "Tree cover": "#1a9641", "Shrubland": "#78c679",
                    "Grassland": "#c2e699", "Cropland": "#f46d43",
                    "Built-up": "#d7191c", "Bare/sparse": "#d9d9d9",
                    "Water": "#4393c3", "Wetland": "#abd9e9",
                }
                fig_overlap = px.bar(
                    overlap_df, x="Fire Count", y="Land Cover",
                    orientation="h", color="Land Cover",
                    color_discrete_map=lc_colors,
                    title="Where Do Fires Actually Occur?",
                    template="plotly_dark",
                )
                fig_overlap.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig_overlap, use_container_width=True)

                forest_fires = sum(1 for n in lc_names if n == "Tree cover")
                agri_fires = sum(1 for n in lc_names if n == "Cropland")
                total_fires = len(lc_names)
                st.caption(
                    f"Of **{total_fires:,}** fire detections: "
                    f"**{100*forest_fires/max(total_fires,1):.1f}%** in forest, "
                    f"**{100*agri_fires/max(total_fires,1):.1f}%** in cropland"
                )
            else:
                st.info("No fire detections fall within the WorldCover raster extent.")
        else:
            st.info("WorldCover raster or FIRMS data not available for overlap analysis.")
    except ImportError:
        st.info("Install rasterio for fire-land cover overlap: pip install rasterio")
    except Exception as e:
        st.warning(f"Fire-land cover overlap unavailable: {e}")

    # ── Key insight ───────────────────────────────────────────────────────────
    st.info(
        f"**Key insight for fire alerts:** Guna Division is "
        f"**{100*summary.get('agriculture_ha',0)/max(summary.get('total_area_ha',1),1):.0f}% agricultural** "
        f"and only **{summary.get('forest_pct',0):.1f}% forest**. "
        f"The vast majority of FIRMS fire detections in Guna are **crop residue burns**, "
        f"not forest fires. The forest mask is used in the NRT alert pipeline to "
        f"correctly classify and prioritize only the **{summary.get('forest_ha',0):,.0f} ha** "
        f"of forested land for Van Suraksha alerts."
    )

    # ── Forest mask status ────────────────────────────────────────────────────
    st.subheader("Data Files")
    files = {
        "Forest mask (30m)": ROOT / "data_lake/land_cover/forest_mask_guna_30m.tif",
        "Forest mask (10m)": ROOT / "data_lake/land_cover/forest_mask_guna_10m.tif",
        "WorldCover clip":   ROOT / "data_lake/land_cover/worldcover_guna_raw.tif",
        "District boundary": ROOT / "data_lake/boundaries/guna_district.geojson",
    }
    for name, path in files.items():
        exists = path.exists()
        size   = f"{path.stat().st_size/1024:.0f} KB" if exists else "—"
        st.write(f"{'✅' if exists else '❌'} **{name}** — `{path.name}` ({size})")


# =============================================================================
# TAB: Ignition ABM
# =============================================================================
elif selected_tab == "\U0001f9ea Ignition ABM":
    st.header("\U0001f9ea Human Ignition ABM \u2014 Guna Division")
    st.caption(
        "Agent-Based Model predicting human-caused fire ignition risk. "
        "5 agent types: Tendu collector, Mahua collector, Grazier, Farmer, Traveler. "
        "Beat-calibrated using 2013-2025 FIRMS fire history."
    )

    # Controls
    c1, c2, c3 = st.columns(3)
    with c1:
        abm_date = st.date_input("Simulation date", value=datetime(2025, 3, 15).date())
    with c2:
        abm_fwi = st.slider("FWI override", 0.0, 60.0, 25.0, 0.5)
    with c3:
        abm_runs = st.select_slider("Monte Carlo runs", options=[5, 10, 20, 50], value=10)

    if st.button("Run ABM Simulation", type="primary"):
        with st.spinner(f"Running {abm_runs} Monte Carlo simulations..."):
            try:
                from src.model.ignition_abm import (
                    DayWeather, run_monte_carlo, IgnitionABM,
                    LAT_MIN as ABM_LAT_MIN, LON_MIN as ABM_LON_MIN,
                    CELL_SIZE_DEG as ABM_CELL,
                    GRID_WIDTH as ABM_W, GRID_HEIGHT as ABM_H,
                )

                weather = DayWeather(fwi=abm_fwi, ffmc=min(97, 70 + abm_fwi * 0.6),
                                     temp_c=35.0, rh_pct=max(10, 50 - abm_fwi))
                mc = run_monte_carlo(
                    sim_date=str(abm_date), weather=weather, n_runs=abm_runs,
                )

                # Summary metrics
                m1, m2, m3, m4 = st.columns(4)
                mean_ign = mc["mean_ignitions"]
                risk = ("VERY HIGH" if mean_ign >= 30 else "HIGH" if mean_ign >= 15
                        else "MODERATE" if mean_ign >= 5 else "LOW")
                risk_color = {"VERY HIGH": "#d73027", "HIGH": "#fc8d59",
                              "MODERATE": "#fee08b", "LOW": "#1a9850"}.get(risk, "#999")
                with m1:
                    metric_card("Ignition Risk", risk, f"FWI={abm_fwi:.0f}", risk_color)
                with m2:
                    metric_card("Predicted Fires/Day", f"{mean_ign:.1f}",
                                f"from {abm_runs} runs", "#4393c3")
                with m3:
                    metric_card("Hotspot Cells", f"{len(mc['hotspots'])}",
                                "with p > 0", "#7570b3")
                with m4:
                    metric_card("Simulation Date", str(abm_date),
                                f"DOY {abm_date.timetuple().tm_yday}", "#333")

                # Hotspot map using pydeck
                hotspots = mc.get("hotspots", [])
                if hotspots:
                    import pydeck as pdk
                    hs_df = pd.DataFrame(hotspots)
                    hs_df["radius"] = hs_df["probability"] * 2000 + 300
                    hs_df["color_r"] = (hs_df["probability"] * 255).clip(0, 255).astype(int)
                    hs_df["color_g"] = ((1 - hs_df["probability"]) * 100).astype(int)

                    layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=hs_df,
                        get_position=["longitude", "latitude"],
                        get_radius="radius",
                        get_fill_color=["color_r", "color_g", 30, 180],
                        pickable=True,
                    )
                    view = pdk.ViewState(
                        latitude=(ABM_LAT_MIN + 24.95) / 2,
                        longitude=(ABM_LON_MIN + 77.85) / 2,
                        zoom=8.5,
                        pitch=0,
                    )
                    _deck_abm = pdk.Deck(
                        layers=[layer],
                        initial_view_state=view,
                        tooltip={"text": "Lat: {latitude}\nLon: {longitude}\nP(ignition): {probability}"},
                    )
                    st.pydeck_chart(_deck_abm)
                    fullscreen_map_button(_deck_abm, "ignition_abm")

                    # Hotspot table
                    st.subheader("Top Ignition Hotspots")
                    display_df = hs_df[["latitude", "longitude", "probability"]].copy()
                    display_df.columns = ["Latitude", "Longitude", "P(ignition)"]
                    display_df["P(ignition)"] = display_df["P(ignition)"].apply(lambda x: f"{x:.1%}")
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No ignition hotspots predicted — conditions are too wet or cool.")

            except Exception as e:
                st.error(f"ABM simulation failed: {e}")
    else:
        st.info(
            "Click **Run ABM Simulation** to predict today's human-caused fire ignition risk. "
            "The model simulates 830 agents (tendu/mahua collectors, graziers, farmers, travelers) "
            "moving through the landscape and attempting ignition based on weather, terrain, and proximity."
        )

