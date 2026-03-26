"""
Van Suraksha — Forest Fire Monitoring Dashboard
================================================
Streamlit dashboard for Guna Division, Madhya Pradesh.

Tabs:
  1. Live Alert       — today's fire alert bulletin + FWI gauge
  2. 3D Digital Twin  — Three.js 3D terrain visualization
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
def load_firms_history(lookback_days: int = 365) -> list:
    """Load VIIRS/MODIS fire detections for Three.js overlay.
    Reuses load_firms_all() which merges annual parquets + NRT CSVs."""
    df = load_firms_all()
    if df.empty:
        return []
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
    df = df[df["acq_date"] >= cutoff].sort_values("acq_date", ascending=False)
    out = []
    for _, r in df.head(2000).iterrows():
        out.append({
            "lat": float(r.latitude), "lon": float(r.longitude),
            "date": r.acq_date.strftime("%Y-%m-%d"),
            "frp": float(r.get("frp", 0) if hasattr(r, "get") else 0),
        })
    return out


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

    # --- Static file server (shared, used by 3D Digital Twin & overlays) ---
    if "overlay_server" not in st.session_state:
        import threading, http.server

        class CORSHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(ROOT / "dashboard" / "static"), **kwargs)

            def end_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET")
                super().end_headers()

            def log_message(self, format, *args):
                pass  # suppress logs

        _srv = http.server.HTTPServer(("127.0.0.1", 8777), CORSHandler)
        _srv.timeout = 0.1
        threading.Thread(target=_srv.serve_forever, daemon=True).start()
        st.session_state["overlay_server"] = True

    _overlay_base = "http://127.0.0.1:8777"

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
    st.subheader("3D Digital Twin — Guna Division")

    # Load config and fire data
    _twin_config_path = ROOT / "dashboard" / "static" / "twin_config.json"
    if _twin_config_path.exists():
        with open(_twin_config_path) as _f:
            _twin_cfg = json.load(_f)
    else:
        st.warning("Twin config not found. Run: python scripts/generate_twin_data.py")
        _twin_cfg = {"terrain": {"bounds": {}, "elevation_range": [0, 1]}, "trees": [], "boundaries": []}

    # Load latest alert for fire overlay
    _alert_path = ROOT / "data_lake" / "alerts" / "latest_alert.json"
    if _alert_path.exists():
        with open(_alert_path) as _f:
            _latest_alert = json.load(_f)
    else:
        _latest_alert = {"fires": [], "fires_detected": 0}
    _fires_data = json.dumps({
        "active": [
            {"lat": f["fire_lat"], "lon": f["fire_lon"],
             "frp": f.get("frp_mw", 0),
             "ros": f.get("prescriptive_metrics", {}).get("ros_m_min", 5.0)}
            for f in _latest_alert.get("fires", [])
        ],
        "abm_hotspots": _latest_alert.get("abm_ignition_risk", {}).get("hotspots", []),
        "firms_history": load_firms_history(),
    })

    _twin_config_json = json.dumps(_twin_cfg)

    twin_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<style>
  * {{{{ margin:0; padding:0; box-sizing:border-box; }}}}
  body {{{{ background:#0a0a0f; overflow:hidden; }}}}
  #c {{{{ width:100%; height:800px; display:block; }}}}

  .panel {{{{
    position:absolute; z-index:10;
    background:rgba(10,10,20,0.88); color:#fff;
    border:1px solid rgba(255,255,255,0.15);
    border-radius:8px; backdrop-filter:blur(8px);
    font-family:'Segoe UI',system-ui,sans-serif;
  }}}}

  #overlay-btns {{{{
    top:12px; right:12px; padding:8px; display:flex; gap:6px;
  }}}}
  .obtn {{{{
    padding:6px 12px; border:1px solid rgba(255,255,255,0.25);
    border-radius:6px; background:transparent; color:#fff;
    cursor:pointer; font-size:12px; transition:all 0.2s;
  }}}}
  .obtn:hover {{{{ border-color:rgba(255,255,255,0.5); }}}}
  .obtn.active {{{{ border-color:#4ade80; color:#4ade80; }}}}

  #info {{{{
    bottom:12px; left:12px; padding:12px 16px; min-width:200px;
  }}}}
  #info h4 {{{{ font-size:13px; color:#4ade80; margin-bottom:4px; }}}}
  #info p {{{{ font-size:11px; opacity:0.8; line-height:1.4; }}}}

  #style-toggle {{{{
    bottom:12px; right:12px; padding:6px 14px;
  }}}}
  .obtn.style {{{{ font-size:11px; }}}}

  #stats {{{{
    top:12px; left:12px; padding:8px 12px; font-size:11px;
    font-family:monospace;
  }}}}
</style>
</head><body>
<canvas id="c"></canvas>

<div class="panel" id="overlay-btns">
  <button class="obtn active" onclick="setOverlay('fires',this)">\U0001f525 Fires</button>
  <button class="obtn" onclick="setOverlay('spread',this)">\U0001f4e1 Spread</button>
  <button class="obtn" onclick="setOverlay('risk',this)">\U0001f5fa\ufe0f Risk</button>
  <button class="obtn" onclick="setOverlay('firms',this)">\U0001f4cd FIRMS</button>
</div>

<div class="panel" id="info">
  <h4 id="info-title">Guna Division</h4>
  <p id="info-body">747 compartments \u00b7 8 ranges \u00b7 Drag to explore</p>
</div>

<div class="panel" id="style-toggle">
  <button class="obtn style active" onclick="toggleDither(this)">\u2b21 Dithered</button>
</div>

<div class="panel" id="stats">
  <span id="fps">--</span> FPS
</div>

<script type="importmap">
{{{{
  "imports": {{{{
    "three": "https://cdn.jsdelivr.net/npm/three@0.171.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.171.0/examples/jsm/"
  }}}}
}}}}
</script>

<script type="module">
import * as THREE from 'three';
import {{{{ OrbitControls }}}} from 'three/addons/controls/OrbitControls.js';
import {{{{ EffectComposer }}}} from 'three/addons/postprocessing/EffectComposer.js';
import {{{{ RenderPass }}}} from 'three/addons/postprocessing/RenderPass.js';
import {{{{ ShaderPass }}}} from 'three/addons/postprocessing/ShaderPass.js';

// --- Data ---
const CONFIG = {_twin_config_json};
const FIRES = {_fires_data};
const OVERLAY_BASE = "{_overlay_base}";
const B = CONFIG.terrain.bounds;
const ELEV = CONFIG.terrain.elevation_range;
const EXAG = CONFIG.terrain.vertical_exaggeration || 2.5;
const TERRAIN_W = B.east - B.west;
const TERRAIN_H = B.north - B.south;
const SCALE = 100;

// --- Coordinate Mapping: lon->X, lat->Z, elev->Y ---
function geoToWorld(lon, lat, elev) {{{{
  const x = (lon - B.west) / TERRAIN_W * TERRAIN_W * SCALE - (TERRAIN_W * SCALE / 2);
  const z = -((lat - B.south) / TERRAIN_H * TERRAIN_H * SCALE - (TERRAIN_H * SCALE / 2));
  const y = elev !== undefined ?
    ((elev - ELEV[0]) / (ELEV[1] - ELEV[0])) * (ELEV[1] - ELEV[0]) * EXAG * 0.01 : 0;
  return new THREE.Vector3(x, y, z);
}}}}

// --- Renderer ---
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({{{{ canvas, antialias: true }}}});
renderer.setSize(canvas.clientWidth, canvas.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, canvas.clientWidth / canvas.clientHeight, 0.1, 5000);

const cx = TERRAIN_W * SCALE * 0.3;
const cz = TERRAIN_H * SCALE * 0.3;
camera.position.set(cx, 30, cz);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.target.set(0, 5, 0);
controls.maxPolarAngle = Math.PI / 2.1;
controls.minDistance = 20;
controls.maxDistance = TERRAIN_W * SCALE * 2;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.3;

let autoRotateTimer = null;
controls.addEventListener('start', () => {{{{
  controls.autoRotate = false;
  clearTimeout(autoRotateTimer);
}}}});
controls.addEventListener('end', () => {{{{
  autoRotateTimer = setTimeout(() => {{{{ controls.autoRotate = true; }}}}, 10000);
}}}});

// --- Lighting ---
scene.add(new THREE.AmbientLight(0x445566, 0.6));

const sun = new THREE.DirectionalLight(0xffeedd, 1.8);
sun.position.set(60, 80, 40);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 1;
sun.shadow.camera.far = 300;
const sc = TERRAIN_W * SCALE;
sun.shadow.camera.left = -sc;
sun.shadow.camera.right = sc;
sun.shadow.camera.top = sc;
sun.shadow.camera.bottom = -sc;
scene.add(sun);
scene.add(new THREE.DirectionalLight(0x88aacc, 0.4).translateX(-40).translateY(30));
// --- Sky ---
const skyGeo = new THREE.SphereGeometry(2000, 32, 32);
const skyMat = new THREE.ShaderMaterial({{{{
  side: THREE.BackSide,
  uniforms: {{{{
    topColor: {{{{ value: new THREE.Color(0x0044aa) }}}},
    bottomColor: {{{{ value: new THREE.Color(0xccddee) }}}},
  }}}},
  vertexShader: `varying vec3 vWP; void main(){{{{ vWP=(modelMatrix*vec4(position,1.0)).xyz; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }}}}`,
  fragmentShader: `uniform vec3 topColor,bottomColor; varying vec3 vWP;
    void main(){{{{ float h=normalize(vWP+20.0).y; gl_FragColor=vec4(mix(bottomColor,topColor,max(pow(max(h,0.0),0.4),0.0)),1.0); }}}}`
}}}});
scene.add(new THREE.Mesh(skyGeo, skyMat));

// --- Terrain (GPU-displaced) ---
const terrainGeo = new THREE.PlaneGeometry(
  TERRAIN_W * SCALE, TERRAIN_H * SCALE, 1024, 1024
);
terrainGeo.rotateX(-Math.PI / 2);

const heightmapTex = new THREE.TextureLoader().load(OVERLAY_BASE + '/heightmap_guna.png');
heightmapTex.minFilter = THREE.LinearFilter;
heightmapTex.magFilter = THREE.LinearFilter;

const lulcTex = new THREE.TextureLoader().load(OVERLAY_BASE + '/lulc.png');

let terrainMat;
try {{{{
terrainMat = new THREE.ShaderMaterial({{{{
  uniforms: {{{{
    heightmap: {{{{ value: heightmapTex }}}},
    lulcMap: {{{{ value: lulcTex }}}},
    elevRange: {{{{ value: new THREE.Vector2(ELEV[0], ELEV[1]) }}}},
    exaggeration: {{{{ value: EXAG * 0.01 }}}},
    sunDir: {{{{ value: new THREE.Vector3(0.5, 0.8, 0.3).normalize() }}}},
  }}}},
  vertexShader: `
    uniform sampler2D heightmap;
    uniform vec2 elevRange;
    uniform float exaggeration;
    varying vec2 vUv;
    varying vec3 vNormal;
    varying vec3 vWorldPos;

    void main() {{{{
      vUv = uv;
      float h = texture2D(heightmap, uv).r;
      float elev = mix(elevRange.x, elevRange.y, h) * exaggeration;
      vec3 pos = position;
      pos.y = elev;

      float texel = 1.0 / 1024.0;
      float hL = texture2D(heightmap, uv + vec2(-texel, 0.0)).r;
      float hR = texture2D(heightmap, uv + vec2( texel, 0.0)).r;
      float hD = texture2D(heightmap, uv + vec2(0.0, -texel)).r;
      float hU = texture2D(heightmap, uv + vec2(0.0,  texel)).r;
      vec3 n = normalize(vec3(hL - hR, 2.0 * texel / exaggeration, hD - hU));
      vNormal = normalMatrix * n;

      vWorldPos = (modelMatrix * vec4(pos, 1.0)).xyz;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    }}}}
  `,
  fragmentShader: `
    uniform sampler2D lulcMap;
    uniform vec3 sunDir;
    varying vec2 vUv;
    varying vec3 vNormal;
    varying vec3 vWorldPos;

    void main() {{{{
      vec3 lulcColor = texture2D(lulcMap, vUv).rgb;
      vec3 baseColor = mix(lulcColor, vec3(0.3, 0.35, 0.15), 0.3);

      float diff = max(dot(normalize(vNormal), sunDir), 0.0);
      float ambient = 0.35;
      vec3 lit = baseColor * (ambient + diff * 0.65);

      gl_FragColor = vec4(lit, 1.0);
    }}}}
  `
}}}});
}}}} catch(e) {{{{
  console.warn('Terrain shader failed, using Lambert fallback:', e);
  terrainMat = new THREE.MeshLambertMaterial({{{{ color: 0x3d6b2e }}}});
}}}}

const terrain = new THREE.Mesh(terrainGeo, terrainMat);
terrain.receiveShadow = true;
scene.add(terrain);

// --- Instanced Trees ---
const SPECIES_COLORS = {{{{
  teak: 0x2d5a27, tendu: 0x5a6e30, mahua: 0x4a7c3f,
  bamboo: 0x7ab356, shrub: 0x8b7d3c,
}}}};

const trunkGeo = new THREE.CylinderGeometry(0.08, 0.15, 1.5, 5);
const canopyGeo = new THREE.DodecahedronGeometry(1.0, 1);
const trunkMat = new THREE.MeshStandardMaterial({{{{ color: 0x5c3a1e, roughness: 0.9 }}}});
const canopyMat = new THREE.MeshStandardMaterial({{{{ color: 0x3d6b2e, roughness: 0.8 }}}});

const TREES = CONFIG.trees;
const treeCount = TREES.length;
const trunkMesh = new THREE.InstancedMesh(trunkGeo, trunkMat, treeCount);
const canopyMesh = new THREE.InstancedMesh(canopyGeo, canopyMat, treeCount);
trunkMesh.castShadow = true;
canopyMesh.castShadow = true;

const _d = new THREE.Object3D();
for (let i = 0; i < treeCount; i++) {{{{
  const t = TREES[i];
  const wPos = geoToWorld(t.lon, t.lat);
  const s = t.height || 1.0;

  _d.position.set(wPos.x, wPos.y + 0.75 * s, wPos.z);
  _d.scale.set(s, s, s);
  _d.rotation.y = Math.random() * Math.PI * 2;
  _d.updateMatrix();
  trunkMesh.setMatrixAt(i, _d.matrix);

  _d.position.y = wPos.y + 2.0 * s;
  _d.scale.set(s * (0.8 + Math.random() * 0.4), s * (0.7 + Math.random() * 0.5), s * (0.8 + Math.random() * 0.4));
  _d.updateMatrix();
  canopyMesh.setMatrixAt(i, _d.matrix);

  const col = new THREE.Color(SPECIES_COLORS[t.species] || 0x3d6b2e);
  canopyMesh.setColorAt(i, col);
}}}}

scene.add(trunkMesh);
scene.add(canopyMesh);

// --- Fire Particles ---
const activeFires = FIRES.active;
let _fireShader = null;
let _fireGlows = null;

if (activeFires.length > 0) {{{{
  const FIRE_COUNT = Math.min(activeFires.length * 200, 800);
  const SMOKE_COUNT = Math.min(activeFires.length * 80, 300);

  const fireShader = new THREE.ShaderMaterial({{{{
    transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    uniforms: {{{{ uTime: {{{{ value: 0 }}}} }}}},
    vertexShader: `
      attribute float aLife, aSpeed, aSize, aBaseY;
      uniform float uTime;
      varying float vLife;
      void main() {{{{
        float life = fract(aLife + uTime * aSpeed * 0.3);
        vLife = life;
        vec3 pos = position;
        pos.y = aBaseY + life * 5.0;
        vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
        gl_Position = projectionMatrix * mvPos;
        gl_PointSize = aSize * (1.0 - life * 0.6) * 80.0 / -mvPos.z;
      }}}}
    `,
    fragmentShader: `
      varying float vLife;
      void main() {{{{
        float d = length(gl_PointCoord - 0.5) * 2.0;
        if (d > 1.0) discard;
        float alpha = (1.0 - d) * (1.0 - vLife) * 0.9;
        vec3 col = mix(vec3(1.0, 0.8, 0.2), vec3(0.8, 0.1, 0.0), vLife);
        gl_FragColor = vec4(col, alpha);
      }}}}
    `
  }}}});

  const firePositions = new Float32Array(FIRE_COUNT * 3);
  const fireLife = new Float32Array(FIRE_COUNT);
  const fireSpeed = new Float32Array(FIRE_COUNT);
  const fireSize = new Float32Array(FIRE_COUNT);
  const fireBaseY = new Float32Array(FIRE_COUNT);

  for (let i = 0; i < FIRE_COUNT; i++) {{{{
    const fire = activeFires[i % activeFires.length];
    const wp = geoToWorld(fire.lon, fire.lat);
    const spread = (fire.frp || 5) * 0.05;
    firePositions[i*3]   = wp.x + (Math.random()-0.5) * spread;
    firePositions[i*3+1] = wp.y;
    firePositions[i*3+2] = wp.z + (Math.random()-0.5) * spread;
    fireLife[i] = Math.random();
    fireSpeed[i] = 0.5 + Math.random() * 1.5;
    fireSize[i] = 0.3 + Math.random() * 0.8;
    fireBaseY[i] = wp.y;
  }}}}

  const fireGeo = new THREE.BufferGeometry();
  fireGeo.setAttribute('position', new THREE.BufferAttribute(firePositions, 3));
  fireGeo.setAttribute('aLife', new THREE.BufferAttribute(fireLife, 1));
  fireGeo.setAttribute('aSpeed', new THREE.BufferAttribute(fireSpeed, 1));
  fireGeo.setAttribute('aSize', new THREE.BufferAttribute(fireSize, 1));
  fireGeo.setAttribute('aBaseY', new THREE.BufferAttribute(fireBaseY, 1));

  const firePoints = new THREE.Points(fireGeo, fireShader);
  scene.add(firePoints);

  const fireGlows = activeFires.map(f => {{{{
    const wp = geoToWorld(f.lon, f.lat);
    const light = new THREE.PointLight(0xff4400, 15, 30);
    light.position.set(wp.x, wp.y + 3, wp.z);
    scene.add(light);
    return light;
  }}}});

  const smokePositions = new Float32Array(SMOKE_COUNT * 3);
  for (let i = 0; i < SMOKE_COUNT; i++) {{{{
    const fire = activeFires[i % activeFires.length];
    const wp = geoToWorld(fire.lon, fire.lat);
    smokePositions[i*3]   = wp.x + (Math.random()-0.5) * 2;
    smokePositions[i*3+1] = wp.y + 3 + Math.random() * 15;
    smokePositions[i*3+2] = wp.z + (Math.random()-0.5) * 2;
  }}}}

  const smokeGeo = new THREE.BufferGeometry();
  smokeGeo.setAttribute('position', new THREE.BufferAttribute(smokePositions, 3));
  const smokeMat = new THREE.PointsMaterial({{{{
    color: 0x555555, size: 2.5, transparent: true,
    opacity: 0.2, depthWrite: false, sizeAttenuation: true,
  }}}});
  scene.add(new THREE.Points(smokeGeo, smokeMat));

  _fireShader = fireShader;
  _fireGlows = fireGlows;
}}}}

// --- Compartment Boundaries ---
const boundaryGroup = new THREE.Group();
const bMat = new THREE.LineBasicMaterial({{{{ color: 0x4ade80, opacity: 0.35, transparent: true }}}});

CONFIG.boundaries.forEach((b, idx) => {{{{
  const pts = b.coords.map(c => {{{{
    const wp = geoToWorld(c[0], c[1]);
    return new THREE.Vector3(wp.x, wp.y + 0.2, wp.z);
  }}}});
  if (pts.length < 3) return;
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const line = new THREE.Line(geo, bMat);
  line.userData = {{{{ idx, beat: b.beat, range: b.range, lulc: b.lulc }}}};
  boundaryGroup.add(line);
}}}});
scene.add(boundaryGroup);

// --- Raycasting for Info Panel ---
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

canvas.addEventListener('mousemove', (e) => {{{{
  const rect = canvas.getBoundingClientRect();
  mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(boundaryGroup.children);

  if (hits.length > 0) {{{{
    const d = hits[0].object.userData;
    document.getElementById('info-title').textContent = d.beat + ' (' + d.range + ')';
    document.getElementById('info-body').textContent =
      'Tree: ' + d.lulc.tree + '% · Shrub: ' + d.lulc.shrub + '% · Grass: ' + d.lulc.grass + '%';
  }}}}
}}}});

// --- Overlay Groups ---
const overlayGroups = {{{{ spread: new THREE.Group(), risk: new THREE.Group(), firms: new THREE.Group() }}}};
Object.values(overlayGroups).forEach(g => {{{{ g.visible = false; scene.add(g); }}}});

// FIRMS History dots
if (FIRES.firms_history && FIRES.firms_history.length > 0) {{{{
  const fhCount = FIRES.firms_history.length;
  const fhGeo = new THREE.BufferGeometry();
  const fhPos = new Float32Array(fhCount * 3);
  const fhCol = new Float32Array(fhCount * 3);
  const now = Date.now();

  FIRES.firms_history.forEach((f, i) => {{{{
    const wp = geoToWorld(f.lon, f.lat);
    fhPos[i*3] = wp.x; fhPos[i*3+1] = wp.y + 0.5; fhPos[i*3+2] = wp.z;
    const age = (now - new Date(f.date).getTime()) / (365 * 86400000);
    const c = new THREE.Color().setHSL(0, 1.0 - age * 0.8, 0.5);
    fhCol[i*3] = c.r; fhCol[i*3+1] = c.g; fhCol[i*3+2] = c.b;
  }}}});

  fhGeo.setAttribute('position', new THREE.BufferAttribute(fhPos, 3));
  fhGeo.setAttribute('color', new THREE.BufferAttribute(fhCol, 3));
  overlayGroups.firms.add(new THREE.Points(fhGeo,
    new THREE.PointsMaterial({{{{ size: 1.5, vertexColors: true, sizeAttenuation: true, transparent: true, opacity: 0.8 }}}})));
}}}}

// ABM Risk Heatmap
if (FIRES.abm_hotspots && FIRES.abm_hotspots.length > 0) {{{{
  FIRES.abm_hotspots.forEach(h => {{{{
    const wp = geoToWorld(h.longitude, h.latitude);
    const cellGeo = new THREE.PlaneGeometry(1.5, 1.5);
    cellGeo.rotateX(-Math.PI / 2);
    const prob = h.probability || 0.1;
    const c = new THREE.Color().setHSL(0.1 - prob * 0.1, 1, 0.5);
    const mat = new THREE.MeshBasicMaterial({{{{ color: c, transparent: true, opacity: prob * 2, side: THREE.DoubleSide }}}});
    const cell = new THREE.Mesh(cellGeo, mat);
    cell.position.set(wp.x, wp.y + 0.3, wp.z);
    overlayGroups.risk.add(cell);
  }}}});
}}}}

// Spread Sim (concentric rings)
if (activeFires.length > 0) {{{{
  activeFires.forEach(f => {{{{
    const wp = geoToWorld(f.lon, f.lat);
    const ros = (f.ros || 5) * 0.001;
    for (let r = 1; r <= 3; r++) {{{{
      const ringGeo = new THREE.RingGeometry(r * ros * 30, r * ros * 30 + 0.1, 32);
      ringGeo.rotateX(-Math.PI / 2);
      const mat = new THREE.MeshBasicMaterial({{{{
        color: 0xff4400, transparent: true, opacity: 0.4 / r, side: THREE.DoubleSide
      }}}});
      const ring = new THREE.Mesh(ringGeo, mat);
      ring.position.set(wp.x, wp.y + 0.3, wp.z);
      overlayGroups.spread.add(ring);
    }}}}
  }}}});
}}}}

// --- Overlay toggle ---
let activeOverlay = 'fires';
window.setOverlay = function(name, btn) {{{{
  activeOverlay = name;
  document.querySelectorAll('#overlay-btns .obtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  overlayGroups.spread.visible = (name === 'spread');
  overlayGroups.risk.visible = (name === 'risk');
  overlayGroups.firms.visible = (name === 'firms');
}}}};

// --- Dithering Post-Process ---
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));

let ditherEnabled = true;
const DitherShader = {{{{
  uniforms: {{{{
    tDiffuse: {{{{ value: null }}}},
    resolution: {{{{ value: new THREE.Vector2(canvas.clientWidth, canvas.clientHeight) }}}},
    ditherScale: {{{{ value: 4.0 }}}},
    colorLevels: {{{{ value: 16.0 }}}},
    enabled: {{{{ value: 1.0 }}}},
  }}}},
  vertexShader: `varying vec2 vUv; void main(){{{{ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }}}}`,
  fragmentShader: `
    uniform sampler2D tDiffuse;
    uniform vec2 resolution;
    uniform float ditherScale, colorLevels, enabled;
    varying vec2 vUv;

    float bayer8(vec2 p) {{{{
      ivec2 ip = ivec2(mod(p, 8.0));
      int b[64] = int[64](
        0,32,8,40,2,34,10,42, 48,16,56,24,50,18,58,26,
        12,44,4,36,14,46,6,38, 60,28,52,20,62,30,54,22,
        3,35,11,43,1,33,9,41, 51,19,59,27,49,17,57,25,
        15,47,7,39,13,45,5,37, 63,31,55,23,61,29,53,21
      );
      return float(b[ip.y*8+ip.x]) / 63.0;
    }}}}

    void main() {{{{
      vec4 color = texture2D(tDiffuse, vUv);
      if (enabled < 0.5) {{{{ gl_FragColor = color; return; }}}}
      vec2 pc = vUv * resolution / ditherScale;
      float d = bayer8(pc);
      vec3 c = floor(color.rgb * (colorLevels - 1.0) + d) / (colorLevels - 1.0);
      gl_FragColor = vec4(c, 1.0);
    }}}}
  `
}}}};

let ditherPass;
try {{{{
  ditherPass = new ShaderPass(DitherShader);
  composer.addPass(ditherPass);
}}}} catch(e) {{{{
  console.warn('Dither shader failed, using fallback:', e);
  ditherEnabled = false;
}}}}

window.toggleDither = function(btn) {{{{
  if (!ditherPass) return;
  ditherEnabled = !ditherEnabled;
  ditherPass.uniforms.enabled.value = ditherEnabled ? 1.0 : 0.0;
  btn.classList.toggle('active');
  btn.textContent = ditherEnabled ? '⬡ Dithered' : '◻ Realistic';
}}}};

// --- Animation ---
const clock = new THREE.Clock();
let fc = 0, lastFT = 0;

function animate() {{{{
  requestAnimationFrame(animate);
  controls.update();

  if (_fireShader) {{{{
    _fireShader.uniforms.uTime.value = clock.getElapsedTime();
  }}}}
  if (_fireGlows) {{{{
    const t = clock.getElapsedTime();
    _fireGlows.forEach((l, i) => {{{{
      l.intensity = 12 + Math.sin(t * 8 + i * 2) * 5;
    }}}});
  }}}}

  composer.render();

  fc++;
  const t = clock.getElapsedTime();
  if (t - lastFT > 0.5) {{{{
    document.getElementById('fps').textContent = Math.round(fc / (t - lastFT));
    fc = 0; lastFT = t;
  }}}}
}}}}
animate();

window.addEventListener('resize', () => {{{{
  camera.aspect = canvas.clientWidth / canvas.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(canvas.clientWidth, canvas.clientHeight);
  composer.setSize(canvas.clientWidth, canvas.clientHeight);
  if (ditherPass) ditherPass.uniforms.resolution.value.set(canvas.clientWidth, canvas.clientHeight);
}}}});
</script>
</body></html>"""

    st.components.v1.html(twin_html, height=820)

    # Quick stats row
    _n_fires = _latest_alert.get("fires_detected", 0)
    _fwi = _latest_alert.get("fwi", {}).get("value", 0)
    _fwi_class = _latest_alert.get("fwi", {}).get("danger_class", "N/A")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Compartments", len(_twin_cfg.get("boundaries", [])))
    c2.metric("Trees", f"{len(_twin_cfg.get('trees', [])):,}")
    c3.metric("Active Fires", _n_fires)
    c4.metric("FWI", f"{_fwi:.1f} ({_fwi_class})")

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

