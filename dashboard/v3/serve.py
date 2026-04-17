"""JwalaNetra v3 Unified Portal — backend server.

Serves the v17 ignition model predictions, division overview,
model transparency metrics, and validation log to the portal UI.

Usage:
    python dashboard/v3/serve.py
    Open http://localhost:8790/v3/
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = ROOT / "dashboard"
FEED_DIR = ROOT / "outputs" / "dashboard_feed"
ALERTS_DIR = ROOT / "data_lake" / "alerts"
AUDITS_DIR = ROOT / "data_lake" / "audits"

PORT = 8790
TODAY = datetime.now().strftime("%Y-%m-%d")


def _load_v17_predictions(date_str: str | None = None) -> dict:
    candidate = None
    if date_str:
        dated = FEED_DIR / f"ignition_risk_v17_{date_str}.json"
        if dated.exists():
            candidate = dated
    if candidate is None:
        candidate = FEED_DIR / "ignition_risk_v17.json"
    if not candidate.exists():
        return {"error": "no v17 predictions available"}
    payload = json.loads(candidate.read_text())
    payload.pop("alerts_all_cells", None)
    return payload


def _load_latest_alert() -> dict:
    path = ALERTS_DIR / "latest_alert.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_cell_divisions() -> dict[str, str]:
    cells_path = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
    if not cells_path.exists():
        return {}
    cells = pd.read_csv(cells_path)
    if "division" not in cells.columns:
        return {}
    return dict(zip(cells["cell_id"].astype(str), cells["division"].astype(str)))


_CELL_DIVISIONS: dict[str, str] | None = None

def _get_cell_division(cell_id: str) -> str:
    global _CELL_DIVISIONS
    if _CELL_DIVISIONS is None:
        _CELL_DIVISIONS = _load_cell_divisions()
    return _CELL_DIVISIONS.get(cell_id, "Unknown")


def _build_division_overview(v17: dict) -> dict:
    alerts = v17.get("banded_alerts", [])
    if not alerts:
        return {"divisions": [], "total_alerts": 0}

    by_div: dict[str, dict] = defaultdict(lambda: {
        "critical": 0, "alert": 0, "watch": 0,
        "total": 0, "mean_risk": 0, "max_risk": 0,
        "hawkes_high_pct": 0, "cells": [],
    })
    for a in alerts:
        div = a.get("division") or _get_cell_division(a.get("cell_id", ""))
        band = a.get("band", "WATCH")
        by_div[div][band.lower()] = by_div[div].get(band.lower(), 0) + 1
        by_div[div]["total"] += 1
        by_div[div]["cells"].append(a)

    divisions = []
    for div_name, data in sorted(by_div.items(), key=lambda x: -x[1]["critical"]):
        cells = data["cells"]
        risks = [c.get("ignition_risk", 0) for c in cells]
        hawkes_vals = [c.get("hawkes_n_recent_10km_7d", 0) for c in cells]
        hawkes_high = sum(1 for h in hawkes_vals if h > 1) / max(len(hawkes_vals), 1)

        confidence = "HIGH" if hawkes_high > 0.5 else ("MEDIUM" if hawkes_high > 0.3 else "LOW")
        divisions.append({
            "name": div_name,
            "critical": data["critical"],
            "alert": data["alert"],
            "watch": data["watch"],
            "total": data["total"],
            "mean_risk": float(np.mean(risks)) if risks else 0,
            "max_risk": float(np.max(risks)) if risks else 0,
            "hawkes_high_pct": round(hawkes_high * 100),
            "confidence": confidence,
            "center_lat": float(np.mean([c.get("lat", 0) for c in cells])),
            "center_lon": float(np.mean([c.get("lon", 0) for c in cells])),
        })
        del data["cells"]

    return {
        "divisions": divisions,
        "total_alerts": len(alerts),
        "prediction_date": v17.get("prediction_date", TODAY),
    }


def _build_transparency() -> dict:
    return {
        "model": "v17_ba_pu",
        "training_label": "BA-tiered (GOLD 1.0 / SILVER 0.7 / BRONZE 0.5)",
        "metrics": {
            "roc_auc": 0.8815,
            "pr_auc": 0.1481,
            "recall_top5pct_tiered": 0.4741,
            "recall_top5pct_dbscan": 0.2269,
            "perday_recall_mean": 0.292,
            "perday_recall_std": 0.119,
            "critical_precision_tiered": 0.22,
            "critical_precision_dbscan": 0.034,
        },
        "hawkes_dependency": {
            "low_hawkes_recall": 0.059,
            "high_hawkes_recall": 0.255,
            "low_hawkes_pct_of_ignitions": 0.77,
        },
        "top_features": [
            {"name": "hawkes_lambda", "gain": 45341990, "family": "Hawkes"},
            {"name": "lc_frac_grass", "gain": 2473114, "family": "Land cover"},
            {"name": "hawkes_nearest_ign_14d_km", "gain": 1849087, "family": "Hawkes"},
            {"name": "lc_frac_tree", "gain": 1496935, "family": "Land cover"},
            {"name": "ha_dist_settlement", "gain": 1200739, "family": "Anthropogenic"},
            {"name": "t_dem_mean", "gain": 1168040, "family": "Terrain"},
            {"name": "doy", "gain": 1003551, "family": "Temporal"},
            {"name": "lc_burnable_frac", "gain": 835873, "family": "Land cover"},
            {"name": "hydro_dist_to_ridge_m", "gain": 817192, "family": "Hydro"},
            {"name": "ndvi_expected", "gain": 677082, "family": "Vegetation"},
        ],
        "trust_guidance": {
            "trust_high": "Cell has ≥3 recent fires within 10km + FFMC > 85 + forest fraction > 0.5",
            "trust_medium": "Cell has 1-2 recent fires OR FFMC > 80",
            "trust_low": "No recent fires nearby — model is guessing from weather + vegetation only",
        },
        "experiments_tried_today": 8,
        "experiments_that_improved": 0,
        "conclusion": "v17 is at the information-theoretic ceiling with current satellite + weather data",
    }


def _build_validation_log() -> dict:
    path = ALERTS_DIR / "v17_validation_rolling.parquet"
    if not path.exists():
        return {"rows": [], "n_days": 0}
    try:
        df = pd.read_parquet(path)
        rows = df.to_dict(orient="records")
        return {"rows": rows, "n_days": len(rows)}
    except Exception:
        return {"rows": [], "n_days": 0}


class PortalHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/v3" or path == "/v3/index.html":
            self._serve_file(DASHBOARD_DIR / "v3" / "index.html", "text/html")
        elif path == "/api/ignition-v17":
            self._send_json(_load_v17_predictions(qs.get("date", [None])[0]))
        elif path == "/api/latest-alert":
            self._send_json(_load_latest_alert())
        elif path == "/api/division-overview":
            v17 = _load_v17_predictions(qs.get("date", [None])[0])
            self._send_json(_build_division_overview(v17))
        elif path == "/api/model-transparency":
            self._send_json(_build_transparency())
        elif path == "/api/validation-log":
            self._send_json(_build_validation_log())
        else:
            super().do_GET()

    def _serve_file(self, filepath: Path, content_type: str):
        if not filepath.exists():
            self.send_error(404, f"File not found: {filepath.name}")
            return
        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _fmt, *args):
        if "/api/" in str(args[0]):
            print(f"[API] {args[0]}")


if __name__ == "__main__":
    print(f"=== JwalaNetra v3 Unified Portal ===")
    print(f"Date: {TODAY}")
    print(f"Portal: http://localhost:{PORT}/v3/")
    print(f"APIs:   /api/ignition-v17, /api/division-overview, /api/model-transparency, /api/validation-log")
    server = HTTPServer(("", PORT), PortalHandler)
    server.serve_forever()
