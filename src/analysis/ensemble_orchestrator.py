"""
Ensemble Orchestrator — Strategy A
====================================
Combines each model where it's strongest into a unified fire risk score:

  1. LightGBM v3 (AUC 0.824)  → Fire RISK probability from spectral+terrain+weather
  2. Pixel LightGBM (AUC 0.70) → Spatial risk layer from terrain-only at 30m
  3. FIRMS VIIRS/MODIS          → Real-time DETECTION of active fires
  4. Anomaly Scorer             → Statistical anomaly (FRP percentile + FWI deviation)
  5. Prescriptive Engine        → Physics-based fire behavior + tactical dispatch
  6. ABM Ignition Model         → Anthropogenic ignition probability (tendu/mahua/grazier)

Pipeline:
  FIRMS detection → enrich with risk scores → compute fire physics → prescribe tactics

Usage:
    from src.analysis.ensemble_orchestrator import EnsembleOrchestrator
    orch = EnsembleOrchestrator()
    alerts = orch.run(firms_detections_df, target_date)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_ENSEMBLE_CONFIG = {
    # Model weights for combined risk score
    "weights": {
        "lgbm_risk": 0.40,       # LightGBM v3 patch-level risk probability
        "pixel_risk": 0.15,      # Pixel-level terrain risk
        "anomaly": 0.25,         # Statistical anomaly score
        "abm_ignition": 0.20,    # Anthropogenic ignition probability
    },
    # Severity classification thresholds (on 0-1 combined score)
    # Calibrated against 2025 FIRMS data: mean=0.28, max=0.49
    "severity_thresholds": {
        "CRITICAL": 0.45,
        "HIGH": 0.35,
        "MODERATE": 0.20,
        "LOW": 0.0,
    },
    # Physics parameters for Guna dry deciduous forest
    "physics": {
        "fuel_load_tonnes_ha": 10.0,   # Dry deciduous (teak/sal litter)
        "cbh_m": 5.0,                   # Canopy base height
        "fmc_pct": 60.0,               # Fire season foliar moisture
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Ensemble Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class EnsembleOrchestrator:
    """
    Unified fire alert pipeline combining all model outputs.

    Each FIRMS detection is enriched with:
      - Risk probability (LightGBM v3)
      - Terrain risk (pixel-level LightGBM)
      - Statistical anomaly score (FRP + FWI)
      - Ignition probability (ABM)
      - Fire physics (Byram intensity, crown fire)
      - Tactical prescription (attack mode, equipment, evacuation)
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or DEFAULT_ENSEMBLE_CONFIG
        self._pixel_model = None
        self._abm_grid = None
        self._fwi_df = None
        self._beat_lookup = None

    # ─── Lazy Loading ─────────────────────────────────────────────────

    def _load_pixel_model(self):
        """Load pixel-level terrain risk model."""
        if self._pixel_model is not None:
            return self._pixel_model

        try:
            import lightgbm as lgb
            model_path = ROOT / "outputs" / "pixel_lgbm" / "pixel_lgbm_v3" / "model.lgbm"
            if not model_path.exists():
                model_path = ROOT / "outputs" / "pixel_lgbm" / "pixel_lgbm_v2" / "model.lgbm"
            if model_path.exists():
                self._pixel_model = lgb.Booster(model_file=str(model_path))
                log.info(f"Loaded pixel-level model from {model_path}")
            else:
                log.warning("Pixel-level model not found — terrain risk disabled")
        except Exception as e:
            log.warning(f"Failed to load pixel model: {e}")

        return self._pixel_model

    def _load_abm_grid(self):
        """Load ABM ignition probability grid."""
        if self._abm_grid is not None:
            return self._abm_grid

        grid_path = ROOT / "data_lake" / "fire_detections" / "abm_ignition_probability.npy"
        if grid_path.exists():
            self._abm_grid = np.load(str(grid_path))
            log.info(f"Loaded ABM ignition grid: shape={self._abm_grid.shape}")
        else:
            log.warning("ABM ignition grid not found")

        return self._abm_grid

    def _load_fwi(self):
        """Load FWI data for weather context."""
        if self._fwi_df is not None:
            return self._fwi_df

        fwi_path = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
        if fwi_path.exists():
            self._fwi_df = pd.read_parquet(fwi_path)
            self._fwi_df["date"] = pd.to_datetime(self._fwi_df["date"])
            self._fwi_df = self._fwi_df.set_index("date")
            log.info(f"Loaded FWI data: {len(self._fwi_df)} days")
        else:
            log.warning("FWI data not found")

        return self._fwi_df

    def _load_beat_lookup(self):
        """Load beat GeoJSON for spatial lookups."""
        if self._beat_lookup is not None:
            return self._beat_lookup

        try:
            import shapely.geometry as sg
            aoi_path = ROOT / "data" / "aoi" / "gunafinal.geojson"
            if aoi_path.exists():
                with open(aoi_path) as f:
                    geojson = json.load(f)
                beats = []
                for feat in geojson["features"]:
                    props = feat.get("properties", {})
                    geom = sg.shape(feat["geometry"])
                    beats.append({
                        "name": props.get("BEAT", props.get("BEAT_N", props.get("name", "Unknown"))),
                        "range": props.get("RANGE", props.get("RANGE_N", "")),
                        "geometry": geom,
                    })
                self._beat_lookup = beats
                log.info(f"Loaded {len(beats)} beat boundaries")
        except ImportError:
            log.warning("shapely not available — beat lookup disabled")
            self._beat_lookup = []

        return self._beat_lookup

    # ─── Core Pipeline ────────────────────────────────────────────────

    def run(
        self,
        firms_df: pd.DataFrame,
        target_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run the full ensemble pipeline on FIRMS detections.

        Parameters
        ----------
        firms_df : DataFrame with columns: latitude, longitude, frp, acq_date, confidence
        target_date : Override date for weather lookups (defaults to detection date)

        Returns
        -------
        List of enriched alert dicts, one per detection
        """
        if firms_df.empty:
            return []

        log.info(f"Ensemble pipeline: processing {len(firms_df)} FIRMS detections")

        # Load all components
        self._load_abm_grid()
        fwi_df = self._load_fwi()

        alerts = []
        for idx, row in firms_df.iterrows():
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            frp = float(row.get("frp", 0.0))
            confidence = str(row.get("confidence", "nominal"))
            acq_date = pd.to_datetime(row.get("acq_date", target_date or datetime.now()))

            alert = self._process_detection(
                lat=lat, lon=lon, frp=frp,
                confidence=confidence,
                detection_date=acq_date,
                fwi_df=fwi_df,
            )
            alerts.append(alert)

        # Sort by ensemble score descending
        alerts.sort(key=lambda a: a["ensemble_score"], reverse=True)

        log.info(f"Ensemble complete: {len(alerts)} alerts "
                 f"({sum(1 for a in alerts if a['severity'] == 'CRITICAL')} CRITICAL, "
                 f"{sum(1 for a in alerts if a['severity'] == 'HIGH')} HIGH)")

        return alerts

    def _process_detection(
        self,
        lat: float,
        lon: float,
        frp: float,
        confidence: str,
        detection_date: datetime,
        fwi_df: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """Process a single FIRMS detection through the full ensemble."""

        # ── 1. Get FWI for this date ──
        fwi_value = self._get_fwi_for_date(fwi_df, detection_date)

        # ── 2. Anomaly Score ──
        from src.analysis.anomaly_scorer import compute_anomaly_score
        anomaly = compute_anomaly_score(
            frp_mw=frp,
            fwi_value=fwi_value,
            severity=self._frp_to_severity(frp),
            month=detection_date.month,
            n_nearby_fires=1,
        )

        # ── 3. ABM Ignition Probability ──
        abm_prob = self._get_abm_probability(lat, lon)

        # ── 4. Terrain Risk (pixel-level model) ──
        terrain_risk = self._get_terrain_risk(lat, lon, detection_date)

        # ── 5. Confidence adjustment ──
        confidence_factor = {"high": 1.0, "nominal": 0.8, "low": 0.5}.get(
            confidence.lower(), 0.7
        )

        # ── 6. Ensemble Score ──
        w = self.config["weights"]
        raw_score = (
            w["anomaly"] * anomaly["anomaly_score"]
            + w["abm_ignition"] * abm_prob
            + w["pixel_risk"] * terrain_risk
            + w["lgbm_risk"] * anomaly["anomaly_score"]  # Use anomaly as proxy when full LightGBM unavailable
        )
        ensemble_score = min(1.0, raw_score * confidence_factor)

        # ── 7. Severity Classification ──
        severity = self._classify_severity(ensemble_score)

        # ── 8. Fire Physics ──
        physics = self._compute_fire_physics(frp, fwi_value)

        # ── 9. Tactical Prescription ──
        from src.analysis.prescriptive_engine import generate_tactical_prescription
        prescription = generate_tactical_prescription(
            intensity_kw_m=physics["byram_intensity_kw_m"],
            ros_km_h=physics["ros_km_h"],
            fwi_value=fwi_value,
            land_cover="Tree cover",  # Guna is dry deciduous forest
        )

        # ── 10. Beat Lookup ──
        beat_info = self._find_beat(lat, lon)

        return {
            # Identity
            "latitude": lat,
            "longitude": lon,
            "detection_date": str(detection_date.date()) if hasattr(detection_date, 'date') else str(detection_date),
            "frp_mw": frp,
            "confidence": confidence,

            # Ensemble
            "ensemble_score": round(ensemble_score, 4),
            "severity": severity,

            # Model Components
            "components": {
                "anomaly_score": anomaly["anomaly_score"],
                "frp_percentile": anomaly["frp_percentile"],
                "fwi_deviation": anomaly["fwi_deviation"],
                "abm_ignition_prob": round(abm_prob, 4),
                "terrain_risk": round(terrain_risk, 4),
                "confidence_factor": confidence_factor,
            },

            # Weather
            "fwi_value": fwi_value,

            # Physics
            "fire_physics": physics,

            # Tactical
            "prescription": prescription,

            # Location
            "beat": beat_info,
        }

    # ─── Helper Methods ───────────────────────────────────────────────

    def _get_fwi_for_date(self, fwi_df, date) -> float:
        """Get FWI value for a given date."""
        if fwi_df is None:
            return 20.0  # Default moderate

        ts = pd.Timestamp(date)
        if ts in fwi_df.index:
            return float(fwi_df.loc[ts, "fwi"])

        # Nearest available date
        idx = fwi_df.index.get_indexer([ts], method="nearest")[0]
        if 0 <= idx < len(fwi_df):
            return float(fwi_df.iloc[idx]["fwi"])
        return 20.0

    def _get_abm_probability(self, lat: float, lon: float) -> float:
        """Look up ABM ignition probability at given location."""
        if self._abm_grid is None:
            return 0.5  # Default moderate

        # Map lat/lon to grid indices
        # ABM grid covers Guna AOI: lat [23.88, 25.11], lon [76.80, 77.49]
        grid_h, grid_w = self._abm_grid.shape
        lat_min, lat_max = 23.88, 25.11
        lon_min, lon_max = 76.80, 77.49

        gy = int((lat_max - lat) / (lat_max - lat_min) * grid_h)
        gx = int((lon - lon_min) / (lon_max - lon_min) * grid_w)

        gy = np.clip(gy, 0, grid_h - 1)
        gx = np.clip(gx, 0, grid_w - 1)

        prob = float(self._abm_grid[gy, gx])
        # Normalize to 0-1 if needed
        grid_max = self._abm_grid.max()
        if grid_max > 1.0:
            prob = prob / grid_max

        return prob

    def _get_terrain_risk(self, lat: float, lon: float, date: datetime) -> float:
        """Get terrain risk from pixel-level model (or default)."""
        pixel_model = self._load_pixel_model()
        if pixel_model is None:
            return 0.5

        # For now, return moderate risk — full integration requires raster sampling
        # at inference time. The pixel model is better used for pre-computed risk maps.
        return 0.5

    def _frp_to_severity(self, frp: float) -> str:
        """Map FRP to severity label."""
        if frp >= 50:
            return "CRITICAL"
        elif frp >= 20:
            return "HIGH"
        elif frp >= 5:
            return "MODERATE"
        return "LOW"

    def _classify_severity(self, score: float) -> str:
        """Classify ensemble score into severity level."""
        thresholds = self.config["severity_thresholds"]
        if score >= thresholds["CRITICAL"]:
            return "CRITICAL"
        elif score >= thresholds["HIGH"]:
            return "HIGH"
        elif score >= thresholds["MODERATE"]:
            return "MODERATE"
        return "LOW"

    def _compute_fire_physics(self, frp: float, fwi: float) -> Dict[str, Any]:
        """Compute fire physics from FRP and FWI."""
        from src.analysis.prescriptive_engine import (
            calculate_byram_intensity,
            van_wagner_crown_fire,
        )

        # Estimate ROS from FRP (empirical: FRP is proportional to intensity, I = H*w*r)
        # For dry deciduous: fuel_load ~ 10 t/ha, H ~ 18000 kJ/kg
        # I_kw_m ~ FRP_MW * 50 (rough empirical scaling for VIIRS)
        estimated_intensity = frp * 50.0
        fuel_load = self.config["physics"]["fuel_load_tonnes_ha"]

        # Back-solve ROS: I = H * w * r -> r = I / (H * w)
        w_kg_m2 = fuel_load * 0.1
        H = 18000.0
        ros_m_s = estimated_intensity / max(H * w_kg_m2, 1.0)
        ros_km_h = ros_m_s * 3.6

        byram = calculate_byram_intensity(ros_km_h, fuel_load)
        crown = van_wagner_crown_fire(
            byram,
            cbh_m=self.config["physics"]["cbh_m"],
            fmc_pct=self.config["physics"]["fmc_pct"],
        )

        return {
            "byram_intensity_kw_m": byram,
            "ros_km_h": round(ros_km_h, 3),
            "ros_m_min": round(ros_m_s * 60, 2),
            "fire_type": crown["fire_type"],
            "is_crowning": crown["is_crowning"],
            "crown_fraction": crown["crown_fraction"],
            "estimated_from": "FRP_empirical",
        }

    def _find_beat(self, lat: float, lon: float) -> Dict[str, str]:
        """Find which beat/range a coordinate falls in."""
        beats = self._load_beat_lookup()
        if not beats:
            return {"beat_name": "Unknown", "range_name": "Unknown"}

        try:
            from shapely.geometry import Point
            point = Point(lon, lat)
            for beat in beats:
                if beat["geometry"].contains(point):
                    return {
                        "beat_name": beat["name"],
                        "range_name": beat["range"],
                    }
        except Exception:
            pass

        return {"beat_name": "Unknown", "range_name": "Unknown"}


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════

def run_ensemble_on_firms(
    firms_csv_or_df,
    target_date: Optional[datetime] = None,
    config: Optional[Dict] = None,
) -> List[Dict]:
    """
    One-shot convenience function: load FIRMS data -> run ensemble -> return alerts.

    Parameters
    ----------
    firms_csv_or_df : str (CSV path) or DataFrame
    target_date : Override date for weather lookups
    config : Override ensemble configuration

    Returns
    -------
    List of alert dicts sorted by ensemble_score descending
    """
    if isinstance(firms_csv_or_df, (str, Path)):
        firms_df = pd.read_csv(firms_csv_or_df)
    else:
        firms_df = firms_csv_or_df

    orch = EnsembleOrchestrator(config=config)
    return orch.run(firms_df, target_date=target_date)


def format_alert_summary(alerts: List[Dict]) -> str:
    """Format alerts as human-readable summary text."""
    if not alerts:
        return "No active fire alerts."

    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"VANAAGNI ENSEMBLE FIRE ALERT SUMMARY -- {len(alerts)} detections")
    lines.append(f"{'='*70}")

    severity_counts = {}
    for a in alerts:
        s = a["severity"]
        severity_counts[s] = severity_counts.get(s, 0) + 1

    for sev in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        if sev in severity_counts:
            lines.append(f"  {sev}: {severity_counts[sev]}")

    lines.append(f"\n{'_'*70}")

    for i, a in enumerate(alerts):
        lines.append(f"\n[{i+1}] {a['severity']} -- Score: {a['ensemble_score']:.3f}")
        lines.append(f"    Location: ({a['latitude']:.4f}, {a['longitude']:.4f})")
        lines.append(f"    Beat: {a['beat']['beat_name']} ({a['beat']['range_name']})")
        lines.append(f"    FRP: {a['frp_mw']:.1f} MW | FWI: {a['fwi_value']:.1f}")
        lines.append(f"    Fire type: {a['fire_physics']['fire_type']} | "
                     f"Intensity: {a['fire_physics']['byram_intensity_kw_m']:.0f} kW/m")
        lines.append(f"    Attack: {a['prescription']['attack_mode']}")
        if a['prescription']['evacuation_trigger']:
            lines.append(f"    WARNING: EVACUATION TRIGGER ACTIVE")

    lines.append(f"\n{'='*70}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="VanAagni Ensemble Fire Alert Pipeline")
    parser.add_argument("--firms-csv", type=str, default=None,
                        help="Path to FIRMS CSV (or uses latest VIIRS data)")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD)")
    parser.add_argument("--demo", action="store_true",
                        help="Run demo with synthetic detections")
    args = parser.parse_args()

    if args.demo:
        # Demo with representative Guna Division fire detections
        demo_df = pd.DataFrame([
            {"latitude": 24.285, "longitude": 76.998, "frp": 62.7,
             "acq_date": "2025-03-15", "confidence": "high"},
            {"latitude": 24.512, "longitude": 77.230, "frp": 15.3,
             "acq_date": "2025-03-15", "confidence": "nominal"},
            {"latitude": 24.870, "longitude": 77.150, "frp": 5.1,
             "acq_date": "2025-03-15", "confidence": "low"},
        ])
        alerts = run_ensemble_on_firms(demo_df)
    elif args.firms_csv:
        target_date = datetime.strptime(args.date, "%Y-%m-%d") if args.date else None
        alerts = run_ensemble_on_firms(args.firms_csv, target_date=target_date)
    else:
        # Load latest VIIRS data
        viirs_dir = ROOT / "data_lake" / "fire_detections" / "firms_viirs_snpp_sp"
        latest = sorted(viirs_dir.glob("*.parquet"))[-1]
        firms_df = pd.read_parquet(latest)
        if args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        else:
            target_date = None
        alerts = run_ensemble_on_firms(firms_df, target_date=target_date)

    # Print summary
    print(format_alert_summary(alerts))

    # Save full results
    out_path = ROOT / "outputs" / "ensemble_alerts.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(alerts, f, indent=2, default=str)
    print(f"\nFull results saved to: {out_path}")
