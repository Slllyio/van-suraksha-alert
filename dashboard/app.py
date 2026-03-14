"""
Van Suraksha — Forest Fire Monitoring Dashboard
================================================
Streamlit dashboard for Guna Division, Madhya Pradesh.

Tabs:
  1. Live Alert       — today's fire alert bulletin + FWI gauge
  2. Fire History     — FIRMS fire detections on interactive map
  3. Burn Scars       — Prithvi burn scar catalog + causal fire links
  4. FWI Trends       — Canadian FWI time series, annual peaks, seasonality
  5. Weather & Terrain— GFS NWP forecasts + terrain analysis
  6. Land Cover       — ESA WorldCover forest/agriculture breakdown

Run:
  streamlit run dashboard/app.py
"""

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.io as pio
import streamlit as st

# ── Plotly dark theme override ────────────────────────────────────────────────
_dark = pio.templates["plotly_dark"]
_dark.layout.paper_bgcolor = "rgba(0,0,0,0)"
_dark.layout.plot_bgcolor = "#141a25"
_dark.layout.font = dict(family="Inter, sans-serif", color="#8b949e")
_dark.layout.xaxis = dict(gridcolor="rgba(255,255,255,0.04)")
_dark.layout.yaxis = dict(gridcolor="rgba(255,255,255,0.04)")
pio.templates.default = "plotly_dark"

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Van Suraksha — Guna Fire Monitor",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parent.parent
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

/* ── Dark base ── */
[data-testid="stAppViewContainer"] > section > div,
[data-testid="stMain"] > div { background: var(--bg-primary) !important; }
[data-testid="stAppViewBlockContainer"] { background: var(--bg-primary) !important; }
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
    border-left: 3px solid var(--accent, var(--blue));
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


def metric_card(label: str, value, sub: str = "", color: str = "#3b82f6"):
    st.markdown(
        f"""<div class="metric-card" style="--accent:{color}">
            <div class="label">{label}</div>
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
            text-transform:uppercase">Command Horizon &bull; Guna Division</p>
        </div>""",
        unsafe_allow_html=True,
    )
    st.divider()

    tab_names = [
        "Live Alert",
        "3D Digital Twin",
        "Fire History",
        "Burn Scars",
        "FWI Trends",
        "Weather & Terrain",
        "Land Cover",
    ]
    selected_tab = st.radio("Navigation", tab_names, label_visibility="collapsed")
    st.divider()
    st.caption("FIRMS VIIRS SNPP | NASA POWER | ESA WorldCover 2021 | IBM-NASA Prithvi-EO-2.0")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: 3D Digital Twin
# ─────────────────────────────────────────────────────────────────────────────

if selected_tab == "3D Digital Twin":
    st.header("🛰️ 3D Digital Twin Command Room")
    st.markdown("""
    This interactive 3D environment uses **CesiumJS** and the **Muhurta-2D Level-Set Engine** 
    to simulate fire behavior over Guna's 30m terrain in real-time.
    """)

    # Check if the WebSocket server is likely running
    st.sidebar.info("🔗 Physics Engine: Port 8001")
    
    # Define the Cesium HTML component
    cesium_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <script src="https://cesium.com/downloads/cesiumjs/releases/1.110/Build/Cesium/Cesium.js"></script>
        <link href="https://cesium.com/downloads/cesiumjs/releases/1.110/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
        <style>
            body {{ margin: 0; padding: 0; overflow: hidden; background: #0d1117; font-family: sans-serif; }}
            #cesiumContainer {{ width: 100%; height: 700px; border-radius: 12px; }}
            #hud {{
                position: absolute; top: 20px; left: 20px; background: rgba(20, 20, 20, 0.85);
                border: 1px solid #444; border-radius: 8px; padding: 15px; color: white;
                width: 260px; z-index: 1000; pointer-events: auto;
            }}
            .btn-group {{ display: flex; gap: 5px; margin-top: 10px; }}
            button {{
                flex: 1; background: #444; color: white; border: 1px solid #666; padding: 8px;
                border-radius: 4px; cursor: pointer; font-size: 0.7rem; font-weight: bold;
            }}
            button.active {{ background: #ef4444; border-color: #ef4444; }}
            #status-indicator {{
                position: absolute; bottom: 20px; right: 20px; color: #a6d96a;
                background: rgba(0,0,0,0.5); padding: 5px 10px; font-size: 0.7rem;
            }}
        </style>
    </head>
    <body>
        <div id="cesiumContainer"></div>
        <div id="hud">
            <div style="font-size: 0.9rem; font-weight:bold; margin-bottom:10px; color:#f97316">🔥 MUHURTA-2D CONTROL</div>
            <div style="font-size: 0.7rem; margin-bottom: 8px;">
                Sim Time: <span id="sim-time" style="color:#3b82f6;">00:00</span><br>
                Status: <span id="twin-status" style="color:#22c55e;">Ready</span>
            </div>
            <div class="btn-group">
                <button id="toggleSimBtn" onclick="toggleSimulation()">START SIM</button>
                <button id="lineBtn" onclick="setMode('FIRELINE')">LINE</button>
                <button id="igniteBtn" onclick="setMode('BACKFIRE')">IGNITE</button>
            </div>
            <button style="margin-top:5px; width:100%; background:#2c3e50" onclick="clearAll()">CLEAR</button>
        </div>
        <div id="status-indicator">PDE Engine Ready</div>

        <script>
            const viewer = new Cesium.Viewer('cesiumContainer', {{
                terrainProvider: Cesium.createWorldTerrain(),
                baseLayerPicker: false, infoBox: false, animation: false, timeline: false
            }});
            viewer.scene.globe.depthTestAgainstTerrain = true;

            const centerLon = 77.320;
            const centerLat = 24.640;
            viewer.camera.flyTo({{
                destination: Cesium.Cartesian3.fromDegrees(centerLon, centerLat - 0.05, 5000),
                orientation: {{ pitch: Cesium.Math.toRadians(-35) }}
            }});

            let fireCoords = [];
            let isSimulating = false;
            let socket = null;
            let mode = null;
            let interventions = [];

            const fireEntity = viewer.entities.add({{
                name: 'Surface Fire',
                polygon: {{
                    hierarchy: new Cesium.CallbackProperty(() => {{
                        return fireCoords.length > 2 ? new Cesium.PolygonHierarchy(
                            fireCoords.map(c => Cesium.Cartesian3.fromDegrees(c.lon, c.lat))
                        ) : null;
                    }}, false),
                    material: Cesium.Color.ORANGERED.withAlpha(0.6),
                    outline: true, outlineColor: Cesium.Color.YELLOW,
                    heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
                }}
            }});

            function setMode(m) {{
                mode = m;
                document.getElementById('lineBtn').classList.toggle('active', m === 'FIRELINE');
                document.getElementById('igniteBtn').classList.toggle('active', m === 'BACKFIRE');
            }}

            function clearAll() {{
                interventions = []; fireCoords = [];
                viewer.entities.values.filter(e => e.name === 'Intervention').forEach(e => viewer.entities.remove(e));
                mode = null;
            }}

            const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
            handler.setInputAction((click) => {{
                if (!mode) return;
                const pos = viewer.scene.pickPosition(click.position);
                if (Cesium.defined(pos)) {{
                    const cart = Cesium.Cartographic.fromCartesian(pos);
                    const lon = Cesium.Math.toDegrees(cart.longitude);
                    const lat = Cesium.Math.toDegrees(cart.latitude);
                    interventions.push({{ type: mode, geometry: {{ type: "Point", coordinates: [lon, lat] }} }});
                    viewer.entities.add({{
                        name: 'Intervention', position: pos,
                        point: {{ pixelSize: 8, color: mode === 'FIRELINE' ? Cesium.Color.YELLOW : Cesium.Color.RED, heightReference: Cesium.HeightReference.CLAMP_TO_GROUND }}
                    }});
                }}
            }}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

            function toggleSimulation() {{
                if (isSimulating) {{
                    isSimulating = false; if (socket) socket.close();
                    document.getElementById('toggleSimBtn').innerText = "START SIM";
                    document.getElementById('twin-status').innerText = "Stopped";
                    return;
                }}
                
                // Use 127.0.0.1 for local stability
                const wsHost = "127.0.0.1";
                socket = new WebSocket("ws://" + wsHost + ":8001/ws/simulate");
                isSimulating = true;
                document.getElementById('toggleSimBtn').innerText = "STOP SIM";
                document.getElementById('twin-status').innerText = "Connecting...";

                socket.onopen = () => {{
                    document.getElementById('twin-status').innerText = "Connected";
                    socket.send(JSON.stringify({{ lat: centerLat, lon: centerLon, wind_u: 8.0, wind_v: 3.0, interventions: interventions }}));
                }};
                socket.onmessage = (e) => {{
                    const data = JSON.parse(e.data);
                    if (data.polygons && data.polygons.length > 0) {{
                        fireCoords = data.polygons[0].map(c => ({{ lon: c[0], lat: c[1] }}));
                    }}
                    document.getElementById('sim-time').innerText = "+" + data.time_elapsed + " mins";
                    document.getElementById('twin-status').innerText = "Streaming Physics";
                }};
                socket.onerror = (err) => {{ 
                    console.error("WS Error:", err);
                    document.getElementById('twin-status').innerText = "Conn Failed (Port 8001)"; 
                    isSimulating = false; 
                    document.getElementById('toggleSimBtn').innerText = "START SIM";
                }};
                socket.onclose = () => {{
                    document.getElementById('twin-status').innerText = "Disconnected";
                    isSimulating = false;
                }};
            }}
        </script>
    </body>
    </html>
    """
    
    st.components.v1.html(cesium_html, height=800)
    
    with st.expander("📖 Digital Twin Instructions"):
        st.markdown("""
        1. **View:** Rotate/Zoom the 3D terrain using your mouse.
        2. **Defend:** Click **FIRELINE**, then click on the map to place defense points.
        3. **Attack:** Click **IGNITE**, then click on the map to start controlled backfires.
        4. **Simulate:** Click **START SIM** to run the Level-Set PDE spread model.
        """)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: Live Alert
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "Live Alert":
    st.header("Live Fire Alert Bulletin")

    # Date picker
    col_date, col_run = st.columns([2, 1])
    with col_date:
        alert_date = st.date_input(
            "Alert date",
            value=date.today(),
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
                    fwi_color(fwi_val))
    with c2:
        metric_card("Active Fires", alert.get("fires_detected", 0),
                    "in Guna bbox", "#e34a33")
    with c3:
        metric_card("Forest Fires",
                    alert.get("n_forest_fires", "—"),
                    "in/near forest", "#d73027")
    with c4:
        metric_card("Agri Fires",
                    alert.get("n_agri_fires", "—"),
                    "cropland burns", "#f46d43")
    with c5:
        metric_card("Peak FRP",
                    f"{alert.get('peak_frp_mw', 0):.1f} MW",
                    "fire radiative power", "#fc8d59")

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
            metric_card("Temperature", f"{fwi_data['temp_c']}°C", color="#fd8d3c")
        with cc2:
            metric_card("Rel. Humidity", f"{fwi_data['rh_pct']}%", color="#6baed6")
        with cc3:
            metric_card("Wind Speed", f"{fwi_data['wind_kmh']} km/h", color="#74c476")
        with cc4:
            metric_card("Danger Class", fwi_data.get("danger_class",""), color=fwi_color(fwi_val))

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

        # ── Map ────────────────────────────────────────────────────────────
        st.subheader("Fire Locations")
        import pydeck as pdk
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
        boundary = load_boundary_geojson()
        if boundary:
            layers.insert(0, pdk.Layer(
                "GeoJsonLayer", data=boundary,
                get_line_color=[249,115,22,100], get_fill_color=[0,0,0,0],
                line_width_min_pixels=1, pickable=True,
            ))
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(latitude=24.4,longitude=77.15,zoom=9,pitch=0),
            map_style="dark",
            tooltip={"text": "{severity} — FRP: {frp_mw} MW"},
        ))
    else:
        if sev == "WATCH":
            st.info(f"No active fires detected. FWI={fwi_val:.1f} ({fwi_data.get('danger_class','')}). "
                    f"Fire weather conditions are DANGEROUS — heightened patrol advised.")
        else:
            st.success("No fires detected. Conditions are safe.")

    # ── Live NRT Hotspot Feed (Clipped to Guna) ─────────────────────────────
    st.divider()
    st.subheader("📡 Live NRT Hotspot Feed (Last 48 Hours)")
    with st.spinner("Fetching latest satellite hotspots..."):
        all_firms = load_firms_all()
        if not all_firms.empty:
            # Filter for last 48 hours
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=2)
            recent_fires = all_firms[all_firms["acq_date"] >= cutoff].copy()
            
            if not recent_fires.empty:
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
                    
                    try:
                        import sys
                        sys.path.insert(0, str(ROOT))
                        from src.analysis.ai_dispatcher import AISignalCorps
                        corps = AISignalCorps()
                        hindi_order = corps.translate_to_hindi(order_text)
                    except Exception:
                        hindi_order = order_text

                    st.code(hindi_order, language="text")
                    st.caption("Auto-generated by AISignalCorps Agent")

        st.subheader("Alert Messages")
        for f in fires:
            col_sev, col_msg = st.columns([1, 5])
            with col_sev:
                sev = f.get("severity", "UNKNOWN")
                st.markdown(sev_badge(sev), unsafe_allow_html=True)
            with col_msg:
                st.write(f.get("message", f"Fire at {f.get('fire_lat','?')}, {f.get('fire_lon','?')}"))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: Fire History
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "Fire History":
    st.header("FIRMS VIIRS Fire Detection History (2013–2025)")

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
        sel_years = st.multiselect("Year", years, default=years[-3:])
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

    st.caption(f"Showing {len(filt):,} of {len(firms):,} detections")

    # ── Map ───────────────────────────────────────────────────────────────────
    st.subheader("Detection Map")
    if not filt.empty:
        import pydeck as pdk
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
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=view,
            map_style="dark",
            tooltip={"text": "FRP: {frp} MW"},
        ))

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
        st.dataframe(filt[["acq_date","latitude","longitude","frp","confidence","daynight"]]
                     .sort_values("acq_date", ascending=False).head(200),
                     use_container_width=True)

    # ── Stats table ───────────────────────────────────────────────────────────
    with st.expander("Summary Statistics"):
        st.write(f"Total detections in filter: **{len(filt):,}**")
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("**By confidence:**")
            st.dataframe(filt["confidence"].value_counts().rename("count"),
                         use_container_width=True)
        with col_b:
            st.write("**By day/night:**")
            st.dataframe(filt["daynight"].value_counts().rename("count"),
                         use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Burn Scars
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "Burn Scars":
    st.header("Prithvi-EO-2.0 Burn Scar Analysis")

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
        metric_card("Burn Scar Scenes", total, "processed by Prithvi", "#e34a33")
    with m2:
        metric_card("FIRMS Matched", len(matched),
                    f"{100*len(matched)/max(total,1):.0f}% match rate", "#fc8d59")
    with m3:
        metric_card("Spatial Hits", len(spatial),
                    f"{100*len(spatial)/max(total,1):.0f}% (fire ON burned pixel)", "#fd8d3c")
    with m4:
        peak = matched["fire_frp_mw"].dropna().max() if not matched.empty else 0
        metric_card("Peak FRP", f"{peak:.1f} MW", "highest confirmed fire", "#d73027")

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
# TAB 4: FWI Trends
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "FWI Trends":
    st.header("Fire Weather Index — Guna Division (2013–2025)")

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
                    "#d73027")
    with s2:
        metric_card("Fire Season Mean", f"{fire_szn['fwi'].mean():.1f}",
                    "Mar-Jun average", "#f46d43")
    with s3:
        metric_card("Extreme days", int(extreme),
                    f"{100*extreme/len(fwi_df):.1f}% of all days", "#d73027")
    with s4:
        metric_card("Very High+ days", int(vh_plus),
                    f"{100*vh_plus/len(fwi_df):.1f}% of all days", "#f46d43")

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


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: Land Cover
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: Weather & Terrain
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "Weather & Terrain":
    st.header("Weather Forecasts & Terrain Analysis — Guna Division")

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
                if "temp_c"    in row: metric_card("Temperature", f"{row['temp_c']:.1f}°C",   color="#fd8d3c")
                if "rh_pct"    in row: metric_card("Rel. Humidity", f"{row['rh_pct']:.1f}%",  color="#6baed6")
                if "wind_kmh"  in row: metric_card("Wind", f"{row['wind_kmh']:.1f} km/h",     color="#74c476")
                if "precip_mm" in row: metric_card("Precip.", f"{row['precip_mm']:.2f} mm",   color="#4393c3")

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
            metric_card("Min Elevation",  f"{e.get('min',0):.0f} m",  color="#4393c3")
        with tm2:
            metric_card("Max Elevation",  f"{e.get('max',0):.0f} m",  color="#4393c3")
        with tm3:
            metric_card("Mean Elevation", f"{e.get('mean',0):.0f} m", color="#4393c3")
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


# ─────────────────────────────────────────────────────────────────────────────
# TAB 6: Land Cover
# ─────────────────────────────────────────────────────────────────────────────

elif selected_tab == "Land Cover":
    st.header("Land Cover — Guna Division (ESA WorldCover 2021)")

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
                    f"{summary.get('total_area_ha',0)/100:,.0f} km²",
                    f"{summary.get('total_area_ha',0):,.0f} ha", "#4393c3")
    with m2:
        metric_card("Forest Cover",
                    f"{summary.get('forest_pct',0):.1f}%",
                    f"{summary.get('forest_ha',0):,.0f} ha (Tree cover)", "#1a9641")
    with m3:
        metric_card("Agriculture",
                    f"{100*summary.get('agriculture_ha',0)/max(summary.get('total_area_ha',1),1):.1f}%",
                    f"{summary.get('agriculture_ha',0):,.0f} ha (Cropland)", "#fc8d59")
    with m4:
        metric_card("Scrubland",
                    f"{100*summary.get('scrub_ha',0)/max(summary.get('total_area_ha',1),1):.1f}%",
                    f"{summary.get('scrub_ha',0):,.0f} ha", "#74c476")

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

