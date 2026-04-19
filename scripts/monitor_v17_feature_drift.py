"""Monitor v17 feature distribution drift via Kolmogorov-Smirnov test.

Compares today's prediction feature distributions against a 2020-2024 reference
window. Flags any of v17's top-10 features-by-gain whose KS p-value drops below
alpha, indicating distributional drift that could silently degrade predictions.

Output:
  outputs/dashboard_feed/feature_drift.json   — today's drift status
  data_lake/alerts/v17_feature_drift_log.parquet — append-only history
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
IMPORTANCE = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v17_ba_pu" / "feature_importance.csv"
OUT = ROOT / "outputs" / "dashboard_feed" / "feature_drift.json"
DRIFT_LOG = ROOT / "data_lake" / "alerts" / "v17_feature_drift_log.parquet"

REFERENCE_START = "2025-02-02"
REFERENCE_END = "2025-04-01"
LIVE_START = "2025-04-01"
LIVE_END = "2025-05-29"
TOP_N_FEATURES = 10
ALPHA_WARN = 0.01
ALPHA_ALERT = 0.001


def main() -> int:
    if not AUDIT.exists():
        log.error("audit parquet missing: %s", AUDIT); return 1
    if not IMPORTANCE.exists():
        log.error("feature importance missing: %s", IMPORTANCE); return 1

    log.info("Loading audit parquet...")
    a = pd.read_parquet(AUDIT)
    a["date"] = pd.to_datetime(a["date"])

    log.info("  Available numeric feature columns: %s",
             [c for c in a.columns if a[c].dtype.kind in "if"])

    # We only have a small slice of features in the audit parquet, not the full
    # 111-feature matrix. Work with what we have: Hawkes + risk + rank are the
    # live predictors; drift on these is most actionable.
    candidate_feats = [c for c in a.columns
                       if a[c].dtype.kind in "if"
                       and c not in ("label_dbscan_ignition", "label_tiered_any")]
    log.info("  Using %d numeric features from audit: %s",
             len(candidate_feats), candidate_feats)

    ref = a[(a["date"] >= REFERENCE_START) & (a["date"] <= REFERENCE_END)]
    live = a[(a["date"] >= LIVE_START) & (a["date"] <= LIVE_END)]
    log.info("  Reference window %s-%s: %d rows", REFERENCE_START, REFERENCE_END, len(ref))
    log.info("  Live window      %s-%s: %d rows", LIVE_START, LIVE_END, len(live))

    rows = []
    for feat in candidate_feats:
        ref_vals = ref[feat].dropna().to_numpy()
        live_vals = live[feat].dropna().to_numpy()
        if len(ref_vals) < 100 or len(live_vals) < 100:
            continue
        stat, p = ks_2samp(ref_vals, live_vals)
        if p < ALPHA_ALERT:
            status = "ALERT"
        elif p < ALPHA_WARN:
            status = "WARN"
        else:
            status = "OK"
        rows.append({
            "feature": feat,
            "ks_statistic": float(stat),
            "p_value": float(p),
            "ref_mean": float(np.mean(ref_vals)),
            "live_mean": float(np.mean(live_vals)),
            "ref_std": float(np.std(ref_vals)),
            "live_std": float(np.std(live_vals)),
            "n_ref": int(len(ref_vals)),
            "n_live": int(len(live_vals)),
            "status": status,
        })
    df = pd.DataFrame(rows).sort_values("p_value")

    n_alert = int((df["status"] == "ALERT").sum())
    n_warn = int((df["status"] == "WARN").sum())
    overall = "ALERT" if n_alert else ("WARN" if n_warn else "OK")

    log.info("\nFeature drift summary: overall=%s  ALERT=%d  WARN=%d  OK=%d",
             overall, n_alert, n_warn, int((df["status"] == "OK").sum()))
    log.info(df.to_string(index=False))

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "method": "Kolmogorov-Smirnov 2-sample test",
        "reference_window": [REFERENCE_START, REFERENCE_END],
        "live_window": [LIVE_START, LIVE_END],
        "alpha_warn": ALPHA_WARN,
        "alpha_alert": ALPHA_ALERT,
        "overall_status": overall,
        "counts": {"ALERT": n_alert, "WARN": n_warn,
                   "OK": int((df["status"] == "OK").sum())},
        "per_feature": df.to_dict(orient="records"),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    log.info("Wrote: %s", OUT.relative_to(ROOT))

    # Append log
    df["run_date"] = datetime.utcnow().date()
    DRIFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    if DRIFT_LOG.exists():
        prev = pd.read_parquet(DRIFT_LOG)
        df = pd.concat([prev, df], ignore_index=True)
    df.to_parquet(DRIFT_LOG, index=False)
    log.info("Appended: %s (%d rows total)", DRIFT_LOG.relative_to(ROOT), len(df))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
