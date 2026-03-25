FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies for GDAL/geo
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin libgdal-dev libgeos-dev libproj-dev gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies (all packages the dashboard needs)
RUN pip install --no-cache-dir \
    numpy pandas pyarrow requests scipy joblib \
    lightgbm scikit-learn \
    geopandas shapely pyproj rasterio fiona \
    pyyaml plotly matplotlib folium seaborn \
    streamlit pydeck Pillow \
    xarray netcdf4 mesa

# Application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY dashboard/ ./dashboard/
COPY config.yaml ./

# Data — ALL directories the dashboard tabs need
COPY models/ignition/ ./models/ignition/
COPY data/aoi/ ./data/aoi/
COPY data_lake/fire_detections/ ./data_lake/fire_detections/
COPY data_lake/fire_weather/ ./data_lake/fire_weather/
COPY data_lake/alerts/ ./data_lake/alerts/
COPY data_lake/land_cover/ ./data_lake/land_cover/
COPY data_lake/burn_scars/ ./data_lake/burn_scars/
COPY data_lake/terrain/ ./data_lake/terrain/
COPY data_lake/boundaries/ ./data_lake/boundaries/

RUN mkdir -p outputs/dashboard_feed logs data_lake/weather_forecasts/gfs

EXPOSE 7860

# Streamlit on HF Spaces port
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port", "7860", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]
