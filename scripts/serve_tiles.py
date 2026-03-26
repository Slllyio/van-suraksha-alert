"""
TiTiler COG Tile Server
=======================
Serves Cloud-Optimized GeoTIFFs as dynamic XYZ map tiles for the dashboard.

Endpoints:
  GET /cog/tiles/{z}/{x}/{y}.png?url=<path_to_tif>   — map tile
  GET /cog/info?url=<path_to_tif>                     — raster metadata
  GET /cog/statistics?url=<path_to_tif>               — band statistics
  GET /cog/preview.png?url=<path_to_tif>              — quick preview
  GET /health                                         — health check

Usage::

    python scripts/serve_tiles.py                     # localhost:8000
    python scripts/serve_tiles.py --port 8082         # custom port

    # In MapLibre / Leaflet:
    # http://localhost:8000/cog/tiles/{z}/{x}/{y}.png?url=file:///E:/FIRE/data/rasters/dem_30m.tif
"""

from __future__ import annotations

import argparse
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from titiler.core.factory import TilerFactory

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="FIRE COG Tile Server",
        description="Dynamic tile serving for Guna Division rasters (DEM, slope, burn scars, labels)",
    )

    # CORS for dashboard access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # COG tiler — handles /cog/tiles, /cog/info, /cog/statistics, /cog/preview
    cog = TilerFactory(router_prefix="/cog")
    app.include_router(cog.router, prefix="/cog", tags=["COG Tiles"])

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "fire-tile-server"}

    @app.get("/")
    def index():
        return {
            "endpoints": [
                "/cog/tiles/{z}/{x}/{y}.png?url=<tif_path>",
                "/cog/info?url=<tif_path>",
                "/cog/statistics?url=<tif_path>",
                "/cog/preview.png?url=<tif_path>",
                "/health",
                "/docs",
            ],
            "example_rasters": [
                "file:///E:/FIRE/data/rasters/dem_30m.tif",
                "file:///E:/FIRE/data/rasters/slope_30m.tif",
                "file:///E:/FIRE/data/labels/loss_2024.tif",
            ],
        }

    return app


app = create_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FIRE COG Tile Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    log.info("Starting tile server on %s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)
