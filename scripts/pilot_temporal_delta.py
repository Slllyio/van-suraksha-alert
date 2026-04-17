"""Stage VLM.2 — Pilot: temporal-delta scalar features for fire-precursor signal.

Hypothesis (revised after VLM.1 FAIL):
    A single Sentinel-2 chip captures only the END state of a cell. The DELTA
    between a chip at T-30 (D-37..D-31) and a chip at T0 (D-14..D-1) captures
    what CHANGED in the ~23-day window before ignition. Scalar pixel-level
    indices (NDVI, NDWI, bare-soil ratio, RGB norm) and their deltas can act as
    tabular features for LightGBM, sidestepping the VLM template-anchoring
    failure of Stage VLM.1.

Pipeline:
    1. Read 200 (cell, date, class) rows from data_lake/audits/vlm_pilot_scores.parquet.
    2. For each cell, fetch TWO multi-band S2 chips via GEE getDownloadURL (NPY
       format, raw uint16 reflectance, 64x64, bands B2/B3/B4/B8).
    3. Cache as .npz (resume-safe).
    4. Compute 11 scalar features per pair (NDVI/NDWI/BSI t0/t30 + deltas + flags).
    5. Train LightGBM 5-fold stratified CV. Report ROC mean +/- std + top-3
       importances by gain.
    6. PASS = mean CV ROC >= 0.60 AND >= 1 delta feature in top 3.
    7. Write docs/audits/temporal_delta_finding.md.

Usage:
    python scripts/pilot_temporal_delta.py                         # full 200-cell run
    python scripts/pilot_temporal_delta.py --n-cells 5             # smoke test
    python scripts/pilot_temporal_delta.py --no-resume             # ignore cached chips
    python scripts/pilot_temporal_delta.py --cloud-max 80          # looser cloud filter
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import ee
import lightgbm as lgb
import numpy as np
import pandas as pd
import requests
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pilot_temporal_delta")

ROOT = Path(__file__).resolve().parents[1]
PAIRS_PATH = ROOT / "data_lake" / "audits" / "vlm_pilot_scores.parquet"
OUT_DIR = ROOT / "data_lake" / "audits"
CHIP_DIR = OUT_DIR / "temporal_chips"
FEAT_PATH = OUT_DIR / "temporal_delta_features.parquet"
FINDING_MD = ROOT / "docs" / "audits" / "temporal_delta_finding.md"

CHIP_PIXELS_DEFAULT = 64
CHIP_SIZE_M = 6700  # 6.7 km footprint, same as VLM.1
T0_LOOKBACK = (14, 1)   # (start_offset, end_offset) days before D
T30_LOOKBACK = (37, 31)
S2_CLOUD_MAX_DEFAULT = 60  # looser than VLM.1's 40 to maximize T-30 hit rate
BANDS = ["B2", "B3", "B4", "B8"]  # Blue, Green, Red, NIR
S2_REFL_SCALE = 10000.0  # S2_SR uint16 -> reflectance [0,1]

DELTA_FEATURE_NAMES = {
    "rgb_mean_delta",
    "ndvi_delta",
    "ndwi_delta",
    "bsi_delta",
    "frac_pix_ndvi_drop_gt_0p1",
}


# ---------------------------------------------------------------------------
# GEE fetch
# ---------------------------------------------------------------------------

def fetch_s2_multiband(
    lat: float,
    lon: float,
    start: str,
    end: str,
    chip_pixels: int,
    cloud_max: int,
) -> Optional[np.ndarray]:
    """Fetch a least-cloudy S2 multi-band chip as (H,W,4) float32 reflectance."""
    half = (CHIP_SIZE_M / 2) / 110000.0  # degrees
    region = ee.Geometry.Rectangle([lon - half, lat - half, lon + half, lat + half])
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
    )
    try:
        n = col.size().getInfo()
    except ee.EEException as e:
        log.warning("  EE size error lat=%.3f lon=%.3f: %s", lat, lon, e)
        return None
    if n == 0:
        return None

    img = col.sort("CLOUDY_PIXEL_PERCENTAGE").first().select(BANDS)
    try:
        url = img.getDownloadURL(
            {
                "region": region,
                "dimensions": chip_pixels,
                "format": "NPY",
                "bands": BANDS,
            }
        )
    except ee.EEException as e:
        log.warning("  EE getDownloadURL error lat=%.3f lon=%.3f: %s", lat, lon, e)
        return None

    for attempt in range(4):
        try:
            resp = requests.get(url, timeout=120)
        except requests.RequestException as e:
            wait = 2 ** attempt
            log.warning("  HTTP error %s (attempt %d), wait %ds", e, attempt + 1, wait)
            time.sleep(wait)
            continue
        if resp.status_code == 429:
            wait = 2 ** (attempt + 2)
            log.warning("  HTTP 429 (attempt %d), wait %ds", attempt + 1, wait)
            time.sleep(wait)
            continue
        if resp.status_code >= 400:
            log.warning(
                "  HTTP %d lat=%.3f lon=%.3f: %s",
                resp.status_code, lat, lon, resp.text[:120],
            )
            return None
        break
    else:
        return None

    # GEE NPY response is a structured array (H,W) with one field per band.
    try:
        arr_struct = np.load(io.BytesIO(resp.content))
    except Exception as e:
        log.warning("  npy parse error lat=%.3f lon=%.3f: %s", lat, lon, e)
        return None

    if arr_struct.dtype.names is None:
        # Fallback: assume (H,W,B) plain array
        arr = np.asarray(arr_struct, dtype=np.float32) / S2_REFL_SCALE
        return arr

    # Stack per-band fields into (H,W,4) float32 reflectance
    h, w = arr_struct.shape
    out = np.zeros((h, w, len(BANDS)), dtype=np.float32)
    for i, b in enumerate(BANDS):
        if b in arr_struct.dtype.names:
            out[..., i] = arr_struct[b].astype(np.float32) / S2_REFL_SCALE
        else:
            log.warning("  missing band %s in npy", b)
            return None
    return out


def _load_or_fetch(
    cache_path: Path,
    lat: float,
    lon: float,
    target_date: pd.Timestamp,
    lookback: tuple[int, int],
    chip_pixels: int,
    cloud_max: int,
    resume: bool,
) -> Optional[np.ndarray]:
    """Load chip from npz cache or fetch from GEE. Returns (H,W,4) or None."""
    if resume and cache_path.exists():
        try:
            with np.load(cache_path) as npz:
                arr = npz["arr"].astype(np.float32)
            return arr
        except Exception as e:
            log.warning("  cache read error %s: %s -- refetching", cache_path.name, e)

    start_off, end_off = lookback
    start = (target_date - pd.Timedelta(days=start_off)).strftime("%Y-%m-%d")
    end = (target_date - pd.Timedelta(days=end_off)).strftime("%Y-%m-%d")
    arr = fetch_s2_multiband(lat, lon, start, end, chip_pixels, cloud_max)
    if arr is None:
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        np.savez_compressed(
            cache_path,
            arr=arr.astype(np.float32),
            bands=np.asarray(BANDS),
        )
    except Exception as e:
        log.warning("  cache write error %s: %s", cache_path.name, e)
    return arr


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _ndvi(a: np.ndarray) -> np.ndarray:
    """NDVI = (NIR - R) / (NIR + R). a is (H,W,4) Blue/Green/Red/NIR."""
    nir, r = a[..., 3], a[..., 2]
    return (nir - r) / (nir + r + 1e-6)


def _ndwi(a: np.ndarray) -> np.ndarray:
    """NDWI (McFeeters) = (G - NIR) / (G + NIR). Moisture / water proxy."""
    g, nir = a[..., 1], a[..., 3]
    return (g - nir) / (g + nir + 1e-6)


def _bare_soil(a: np.ndarray) -> np.ndarray:
    """R / (R + G + B). Stand-in for SWIR-based BSI (we don't fetch SWIR here)."""
    r, g, b = a[..., 2], a[..., 1], a[..., 0]
    return r / (r + g + b + 1e-6)


def compute_delta_features(t0: np.ndarray, t30: np.ndarray) -> dict:
    """All 11 scalar delta features. Inputs (H,W,4) float32 reflectance."""
    rgb_t0 = t0[..., :3].mean(axis=(0, 1))
    rgb_t30 = t30[..., :3].mean(axis=(0, 1))
    rgb_mean_delta = float(np.linalg.norm(rgb_t0 - rgb_t30))

    ndvi_t0 = _ndvi(t0)
    ndvi_t30 = _ndvi(t30)
    ndwi_t0 = _ndwi(t0)
    ndwi_t30 = _ndwi(t30)
    bsi_t0 = _bare_soil(t0)
    bsi_t30 = _bare_soil(t30)

    ndvi_t0_mean = float(ndvi_t0.mean())
    ndvi_t30_mean = float(ndvi_t30.mean())
    ndwi_t0_mean = float(ndwi_t0.mean())
    ndwi_t30_mean = float(ndwi_t30.mean())
    bsi_t0_mean = float(bsi_t0.mean())
    bsi_t30_mean = float(bsi_t30.mean())

    return {
        "rgb_mean_delta": rgb_mean_delta,
        "ndvi_t0_mean": ndvi_t0_mean,
        "ndvi_t30_mean": ndvi_t30_mean,
        "ndvi_delta": ndvi_t0_mean - ndvi_t30_mean,
        "ndwi_t0_mean": ndwi_t0_mean,
        "ndwi_t30_mean": ndwi_t30_mean,
        "ndwi_delta": ndwi_t0_mean - ndwi_t30_mean,
        "bsi_t0_mean": bsi_t0_mean,
        "bsi_t30_mean": bsi_t30_mean,
        "bsi_delta": bsi_t0_mean - bsi_t30_mean,
        "frac_pix_ndvi_drop_gt_0p1": float(((ndvi_t30 - ndvi_t0) > 0.1).mean()),
    }


# ---------------------------------------------------------------------------
# Modelling
# ---------------------------------------------------------------------------

def train_lightgbm_cv(
    df: pd.DataFrame,
) -> tuple[Optional[float], Optional[float], list[tuple[str, float]], int, list[float]]:
    """5-fold stratified CV LightGBM. Returns (mean_auc, std_auc, top_importances, n_avail, fold_aucs)."""
    avail = df[df["chip_t0_available"] & df["chip_t30_available"]].copy()
    n_avail = len(avail)
    if n_avail < 50:
        return None, None, [], n_avail, []

    feature_cols = [
        c for c in df.columns
        if c not in {"cell_id", "date", "class",
                     "chip_t0_available", "chip_t30_available"}
    ]
    X = avail[feature_cols].fillna(0.0).to_numpy()
    y = (avail["class"] == "ignited").astype(int).to_numpy()

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    fold_aucs: list[float] = []
    gains_total = np.zeros(len(feature_cols), dtype=np.float64)
    for tr, va in skf.split(X, y):
        clf = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=15,
            min_data_in_leaf=5,
            is_unbalance=True,
            random_state=42,
            verbose=-1,
        )
        clf.fit(X[tr], y[tr])
        p = clf.predict_proba(X[va])[:, 1]
        fold_aucs.append(float(roc_auc_score(y[va], p)))
        gains_total += clf.booster_.feature_importance(importance_type="gain")

    importances = sorted(
        zip(feature_cols, gains_total.tolist()),
        key=lambda x: -x[1],
    )
    return float(np.mean(fold_aucs)), float(np.std(fold_aucs)), importances, n_avail, fold_aucs


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_finding_md(
    verdict: str,
    mean_auc: Optional[float],
    std_auc: Optional[float],
    importances: list[tuple[str, float]],
    n_avail: int,
    n_total: int,
    fold_aucs: list[float],
    cloud_max: int,
    chip_pixels: int,
) -> None:
    FINDING_MD.parent.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    if mean_auc is None:
        body = [
            "# Stage VLM.2 Pilot -- VERDICT: INSUFFICIENT DATA",
            "",
            f"**Date:** {today}",
            f"**Pairs requested:** {n_total} | **Pairs with both chips:** {n_avail}",
            "",
            "## Hypothesis",
            "",
            "Tabular pixel-level deltas (NDVI/NDWI/BSI) between Sentinel-2 chips at "
            "T-30 (D-37..D-31) and T0 (D-14..D-1) carry pre-fire precursor signal "
            "where a single chip does not.",
            "",
            "## Result",
            "",
            f"Only **{n_avail}/{n_total}** cells had BOTH a T-30 and a T0 chip "
            f"available with cloud cover <= {cloud_max}%. Below the 50-pair "
            "minimum required for stable 5-fold CV -- the modelling step was "
            "skipped to avoid reporting a bogus AUC.",
            "",
            "## What it would take to revisit",
            "",
            "1. Loosen `--cloud-max` further (try 80%) and accept noisier chips.",
            "2. Widen the T-30 window from 7 days to 14 days "
            "(`T30_LOOKBACK = (44, 31)`).",
            "3. Backfill historical S2 with `COPERNICUS/S2_HARMONIZED` (TOA, "
            "wider archive coverage pre-2017).",
            "",
            "## Files",
            "",
            "- `scripts/pilot_temporal_delta.py`",
            f"- `data_lake/audits/temporal_delta_features.parquet` ({n_total} rows)",
            "- `data_lake/audits/temporal_chips/` (npz cache, partial)",
        ]
        FINDING_MD.write_text("\n".join(body) + "\n", encoding="utf-8")
        return

    top3 = importances[:3]
    has_delta_in_top3 = any(name in DELTA_FEATURE_NAMES for name, _ in top3)
    pass_roc = mean_auc >= 0.60

    fold_table = "\n".join(
        f"| fold {i+1} | {a:.4f} |" for i, a in enumerate(fold_aucs)
    )
    importances_table = "\n".join(
        f"| {name} | {gain:.1f} |" for name, gain in importances
    )

    body = [
        f"# Stage VLM.2 Pilot -- VERDICT: {verdict} "
        f"(5-fold ROC = {mean_auc:.3f} +/- {std_auc:.3f})",
        "",
        f"**Date:** {today}",
        f"**Source pairs:** `data_lake/audits/vlm_pilot_scores.parquet` "
        "(100 ignited / 100 control low-Hawkes 2025 hold-out)",
        f"**Modelling subset:** {n_avail}/{n_total} cells with both T-30 and T0 chips",
        f"**Chip pixels:** {chip_pixels}x{chip_pixels} | **Cloud max:** {cloud_max}%",
        "",
        "## Hypothesis",
        "",
        "Stage VLM.1 showed a single Sentinel-2 RGB chip has no LLaVA-discriminable "
        "pre-fire signal (mean delta -0.29, p=0.74, rho=-0.045). VLM.2 tests a "
        "different cut on the same imagery: instead of asking a VLM to score one "
        "chip, we compute scalar pixel-level indices (NDVI, NDWI, bare-soil ratio, "
        "RGB norm) on TWO chips (T0 = D-14..D-1, T-30 = D-37..D-31), take their "
        "deltas, and feed the resulting tabular features to LightGBM.",
        "",
        "## Pilot design",
        "",
        "- **Source:** 200 (cell, date, class) rows reused from VLM.1 pilot.",
        "- **Imagery:** Sentinel-2 SR Harmonized via `getDownloadURL` (NPY format, "
        "raw uint16 reflectance scaled to [0,1]). Bands: B2 (Blue), B3 (Green), "
        "B4 (Red), B8 (NIR).",
        f"- **Windows:** T0 = [D-14, D-1], T-30 = [D-37, D-31]. Least-cloudy scene "
        f"per window with `CLOUDY_PIXEL_PERCENTAGE <= {cloud_max}`.",
        f"- **Chip size:** {chip_pixels}x{chip_pixels} over a 6.7 km x 6.7 km "
        "footprint (~104 m/px). Downsampled vs VLM.1's 224x224 to keep 400 GEE "
        "fetches tractable; for scalar mean/fraction features the loss is small.",
        "- **Indices:** NDVI = (NIR-R)/(NIR+R); NDWI = (G-NIR)/(G+NIR); "
        "bare-soil ratio = R/(R+G+B) (proxy for SWIR-based BSI, since SWIR not "
        "fetched in this pilot).",
        "- **Model:** LightGBM binary, `is_unbalance=True`, n=300, num_leaves=15, "
        "min_data_in_leaf=5, lr=0.05. 5-fold StratifiedKFold(random_state=42).",
        "",
        "## Result -- per-fold ROC AUC",
        "",
        "| Fold | ROC AUC |",
        "|------|--------:|",
        f"{fold_table}",
        f"| **mean +/- std** | **{mean_auc:.4f} +/- {std_auc:.4f}** |",
        "",
        "## Feature importance (gain, summed across folds)",
        "",
        "| Feature | Gain |",
        "|---------|-----:|",
        f"{importances_table}",
        "",
        "## Verdict",
        "",
        f"- **Mean CV ROC >= 0.60:** {mean_auc:.3f} -> **{'PASS' if pass_roc else 'FAIL'}**",
        f"- **>= 1 delta feature in top 3:** "
        f"top3 = {[n for n,_ in top3]} -> **{'PASS' if has_delta_in_top3 else 'FAIL'}**",
        "",
        f"**Overall verdict: {verdict}**",
        "",
        "## What it would take to revisit (if FAIL)",
        "",
        "1. **Full 224x224 chips** (matches VLM.1 footprint, captures more spatial heterogeneity).",
        "2. **Add B11/B12 SWIR bands** for true BSI = ((SWIR1+R) - (NIR+B)) / ((SWIR1+R) + (NIR+B)) and NBR = (NIR-SWIR2)/(NIR+SWIR2).",
        "3. **Cell-block spatial CV** (matched ignited/control may be geographically close, inflating CV ROC).",
        "4. **Per-pixel CNN on the delta tensor** instead of scalar mean features -- preserves spatial information our 11 scalars discard.",
        "",
        "## Files",
        "",
        "- `scripts/pilot_temporal_delta.py`",
        f"- `data_lake/audits/temporal_delta_features.parquet` ({n_total} rows)",
        f"- `data_lake/audits/temporal_chips/` (npz cache, ~{n_avail*2} files)",
        "",
        "## Reproducibility",
        "",
        "```",
        f"python scripts/pilot_temporal_delta.py --cloud-max {cloud_max} --chip-pixels {chip_pixels}",
        "```",
    ]
    FINDING_MD.write_text("\n".join(body) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-cells", type=int, default=0,
                   help="Subset to first N rows (0 = all).")
    p.add_argument("--no-resume", action="store_true",
                   help="Ignore cached npz files and refetch.")
    p.add_argument("--cloud-max", type=int, default=S2_CLOUD_MAX_DEFAULT,
                   help=f"S2 CLOUDY_PIXEL_PERCENTAGE upper bound (default {S2_CLOUD_MAX_DEFAULT}).")
    p.add_argument("--chip-pixels", type=int, default=CHIP_PIXELS_DEFAULT,
                   help=f"Chip resolution in pixels (default {CHIP_PIXELS_DEFAULT}).")
    p.add_argument("--gee-project", type=str, default="van-suraksha-alert",
                   help="Earth Engine project ID.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    CHIP_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading pairs from %s", PAIRS_PATH)
    if not PAIRS_PATH.exists():
        log.error("missing pairs parquet: %s", PAIRS_PATH)
        return 2
    pairs = pd.read_parquet(PAIRS_PATH)[
        ["cell_id", "date", "class", "centroid_lat", "centroid_lon"]
    ].copy()
    pairs["date"] = pd.to_datetime(pairs["date"])
    if args.n_cells > 0:
        pairs = pairs.head(args.n_cells).reset_index(drop=True)
    log.info("Pairs to process: %d  (classes: %s)",
             len(pairs), pairs["class"].value_counts().to_dict())

    log.info("Initializing GEE (project=%s)", args.gee_project)
    ee.Initialize(project=args.gee_project)

    rows: list[dict] = []
    n_t0_ok = n_t30_ok = n_both = 0
    t_start = time.time()
    for i, r in pairs.iterrows():
        d = pd.Timestamp(r["date"])
        cls = r["class"]
        cell_id = r["cell_id"]
        t0_path = CHIP_DIR / f"{cls}_{cell_id}_{d:%Y%m%d}_t0.npz"
        t30_path = CHIP_DIR / f"{cls}_{cell_id}_{d:%Y%m%d}_t30.npz"

        t0_arr = _load_or_fetch(
            t0_path, float(r["centroid_lat"]), float(r["centroid_lon"]), d,
            T0_LOOKBACK, args.chip_pixels, args.cloud_max, not args.no_resume,
        )
        t30_arr = _load_or_fetch(
            t30_path, float(r["centroid_lat"]), float(r["centroid_lon"]), d,
            T30_LOOKBACK, args.chip_pixels, args.cloud_max, not args.no_resume,
        )

        feats: dict = {
            "cell_id": cell_id,
            "date": d,
            "class": cls,
            "chip_t0_available": t0_arr is not None,
            "chip_t30_available": t30_arr is not None,
        }
        if t0_arr is not None:
            n_t0_ok += 1
        if t30_arr is not None:
            n_t30_ok += 1
        if t0_arr is not None and t30_arr is not None:
            n_both += 1
            try:
                feats.update(compute_delta_features(t0_arr, t30_arr))
            except Exception as e:
                log.warning("  feature compute error %s: %s", cell_id, e)

        rows.append(feats)
        if (i + 1) % 10 == 0 or (i + 1) == len(pairs):
            elapsed = time.time() - t_start
            log.info(
                "[%3d/%3d] t0=%d t30=%d both=%d  (%.1fs elapsed, %.1fs/pair)",
                i + 1, len(pairs), n_t0_ok, n_t30_ok, n_both,
                elapsed, elapsed / (i + 1),
            )

    df = pd.DataFrame(rows)
    df.to_parquet(FEAT_PATH, index=False)
    log.info("Wrote features: %s (%d rows)", FEAT_PATH, len(df))

    log.info("Training LightGBM 5-fold CV...")
    mean_auc, std_auc, importances, n_avail, fold_aucs = train_lightgbm_cv(df)

    if mean_auc is None:
        log.warning("INSUFFICIENT DATA: only %d/%d cells had both chips (need >=50)",
                    n_avail, len(df))
        write_finding_md(
            "INSUFFICIENT DATA", None, None, [], n_avail, len(df), [],
            args.cloud_max, args.chip_pixels,
        )
        print(f"VERDICT: INSUFFICIENT_DATA | n_avail={n_avail}/{len(df)}")
        return 0

    top3 = importances[:3]
    has_delta_in_top3 = any(name in DELTA_FEATURE_NAMES for name, _ in top3)
    verdict = "PASS" if (mean_auc >= 0.60 and has_delta_in_top3) else "FAIL"

    log.info("5-fold ROC = %.4f +/- %.4f (n=%d)", mean_auc, std_auc, n_avail)
    log.info("Top-3 by gain:")
    for name, g in top3:
        log.info("  %s : %.1f", name, g)
    log.info("Verdict: %s", verdict)

    write_finding_md(
        verdict, mean_auc, std_auc, importances, n_avail, len(df),
        fold_aucs, args.cloud_max, args.chip_pixels,
    )
    print(f"VERDICT: {verdict} | ROC={mean_auc:.3f}+/-{std_auc:.3f} | n={n_avail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
