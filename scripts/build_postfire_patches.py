#!/usr/bin/env python3
"""
scripts/build_postfire_patches.py
==================================
Build POST-fire training patches for burn scar fine-tuning (Strategy B).

Each patch contains:
  hls     float32  (6, 224, 224)   Single-frame post-fire HLS reflectance
  label   int32    (224, 224)      Binary mask: 1=burned, 0=unburned, -1=ignore
  meta    JSON string              Patch metadata

Uses EXISTING data:
  - Post-fire HLS scenes from data_lake/satellite_imagery/hls_s30/
  - RBR ground truth labels from data_lake/training_patches_v5/ .npz files
  - Fire events from training_patches_v5/manifest.csv

Output: data_lake/burnscar_finetune/ with train/val/test splits

Usage:
    python scripts/build_postfire_patches.py
    python scripts/build_postfire_patches.py --max-events 5   # smoke test
"""

import json
import logging
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

os.environ["GTIFF_SRS_SOURCE"] = "GEOKEYS"
os.environ.pop("GDAL_DATA", None)
try:
    import pyproj as _pp
    _proj_data = str(Path(_pp.datadir.get_data_dir()))
    os.environ["PROJ_DATA"] = _proj_data
    os.environ["PROJ_LIB"] = _proj_data
except Exception:
    pass

import numpy as np
import pandas as pd
import rasterio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_LAKE = ROOT / "data_lake"
HLS_DIR = DATA_LAKE / "satellite_imagery" / "hls_s30"
MANIFEST = DATA_LAKE / "training_patches_v5" / "manifest.csv"
OUT_DIR = DATA_LAKE / "burnscar_finetune"

HLS_BANDS = ["B02", "B03", "B04", "B8A", "B11", "B12"]
PATCH_SIZE = 224
POST_FIRE_MIN_GAP = 5    # days after fire
POST_FIRE_MAX_GAP = 45   # days after fire


def find_postfire_scene(tile: str, fire_date: datetime,
                        min_gap: int = POST_FIRE_MIN_GAP,
                        max_gap: int = POST_FIRE_MAX_GAP) -> Optional[Path]:
    """Find the closest post-fire HLS scene directory."""
    for delta in range(min_gap, max_gap + 1):
        dt = fire_date + timedelta(days=delta)
        scene_dir = HLS_DIR / tile / str(dt.year) / f"{dt.month:02d}" / f"{dt.day:02d}"
        if scene_dir.exists() and list(scene_dir.glob("*.B02.tif")):
            return scene_dir
    return None


def load_hls_single_frame(scene_dir: Path,
                          crop_hw: Optional[Tuple[int, int]] = None
                          ) -> Tuple[Optional[np.ndarray], Optional[dict]]:
    """Load 6-band HLS as (6, H, W) float32 reflectance [0, 1]."""
    arrays, profile = [], None
    for band in HLS_BANDS:
        matches = sorted(scene_dir.glob(f"*.{band}.tif"))
        if not matches:
            return None, None
        with rasterio.open(matches[0]) as src:
            if crop_hw is not None:
                from rasterio.windows import Window
                win = Window(0, 0, crop_hw[1], crop_hw[0])
                raw = src.read(1, window=win).astype(np.float32)
            else:
                raw = src.read(1).astype(np.float32)
            if profile is None:
                profile = src.profile.copy()
                if crop_hw is not None:
                    profile.update(height=crop_hw[0], width=crop_hw[1])
        nodata = (raw <= -9990) | (raw == 0)
        reflectance = np.clip(raw * 1e-4, 0.0, 1.0)
        reflectance[nodata] = 0.0  # fill nodata with 0 for training stability
        arrays.append(reflectance)
    return np.stack(arrays, axis=0), profile


def load_label_from_npz(npz_path: Path) -> Tuple[Optional[np.ndarray], dict]:
    """Load binary burn label from existing training patch .npz.
    NOTE: Loading our own trusted local .npz training patches (not external data).
    """
    data = np.load(str(npz_path), allow_pickle=True)
    meta = json.loads(str(data["meta"]))
    raw_label = data["label"].astype(np.float32)

    # Binary: burned where RBR > 0, ignore NaN
    label = np.zeros(raw_label.shape, dtype=np.int32)
    label[raw_label > 0.0] = 1
    label[np.isnan(raw_label)] = -1
    return label, meta


def extract_patches(hls: np.ndarray, label: np.ndarray,
                    stride: int = 112, bg_per_fire: int = 2) -> list:
    """Extract 224x224 patches from full tile with given stride.

    Returns list of (hls_patch, label_patch, row, col, is_fire, fire_px).
    Keeps ALL fire patches + bg_per_fire background patches per fire patch.
    """
    _, H, W = hls.shape
    fire_patches = []
    bg_candidates = []

    for r0 in range(0, max(1, H - PATCH_SIZE + 1), stride):
        for c0 in range(0, max(1, W - PATCH_SIZE + 1), stride):
            lbl_p = label[r0:r0 + PATCH_SIZE, c0:c0 + PATCH_SIZE]
            hls_p = hls[:, r0:r0 + PATCH_SIZE, c0:c0 + PATCH_SIZE]

            if lbl_p.shape != (PATCH_SIZE, PATCH_SIZE):
                continue

            valid = lbl_p >= 0
            fire_px = int((lbl_p == 1).sum())
            is_fire = fire_px >= 10

            if is_fire:
                fire_patches.append((hls_p, lbl_p, r0, c0, True, fire_px))
            elif valid.sum() > PATCH_SIZE * PATCH_SIZE * 0.5:
                bg_candidates.append((hls_p, lbl_p, r0, c0, False, fire_px))

    # Subsample background to bg_per_fire × n_fire
    n_bg = min(len(bg_candidates), len(fire_patches) * bg_per_fire)
    if n_bg > 0 and len(bg_candidates) > n_bg:
        indices = np.random.choice(len(bg_candidates), n_bg, replace=False)
        bg_patches = [bg_candidates[i] for i in indices]
    else:
        bg_patches = bg_candidates[:n_bg]

    return fire_patches + bg_patches


def save_patch(out_path: Path, hls: np.ndarray, label: np.ndarray,
               meta: dict) -> None:
    """Save a single training patch as compressed .npz."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        hls=hls,        # (6, 224, 224)
        label=label,    # (224, 224) int32
        meta=json.dumps(meta),
    )


def build_dataset(max_events: Optional[int] = None):
    manifest = pd.read_csv(MANIFEST)
    fire_df = manifest[
        (manifest["is_fire"] == 1)
        & (manifest["has_spectral"] == 1)
    ].copy()

    # Deduplicate by tile + fire_date, keep highest tier
    tier_rank = {"GOLD": 4, "SILVER": 3, "BRONZE": 2, "VIIRS_ONLY": 1}
    fire_df["_rank"] = fire_df["tier"].map(tier_rank).fillna(0)
    events = fire_df.sort_values("_rank", ascending=False).drop_duplicates(
        subset=["tile", "fire_date"], keep="first"
    ).reset_index(drop=True)

    if max_events:
        events = events.head(max_events)

    log.info(f"Processing {len(events)} unique fire events")
    log.info(f"Output: {OUT_DIR}")

    manifest_rows = []
    stats = {"fire": 0, "bg": 0, "no_scene": 0, "no_hls": 0}

    # Collect all existing patch paths per (tile, fire_date) for label loading
    patch_lookup = {}
    for _, row in fire_df.iterrows():
        key = (row["tile"], row["fire_date"][:10])
        path = ROOT / row["path"]
        if path.exists():
            patch_lookup.setdefault(key, []).append(path)

    for evt_idx, (_, row) in enumerate(events.iterrows()):
        tile = str(row["tile"])
        fire_date_str = str(row["fire_date"])[:10]
        fire_date = datetime.strptime(fire_date_str, "%Y-%m-%d")
        split = row["split"]
        tier = row["tier"]

        log.info(f"[{evt_idx+1}/{len(events)}] {tile} fire={fire_date_str} tier={tier} split={split}")

        # Find post-fire HLS scene
        scene_dir = find_postfire_scene(tile, fire_date)
        if scene_dir is None:
            log.warning(f"  No post-fire HLS scene found — skip")
            stats["no_scene"] += 1
            continue

        # Calculate gap from scene dir path
        scene_date = datetime(
            int(scene_dir.parent.parent.name),
            int(scene_dir.parent.name),
            int(scene_dir.name)
        )
        gap_days = (scene_date - fire_date).days
        log.info(f"  Post-fire scene: {scene_date.date()} (gap={gap_days}d)")

        # Load full-tile HLS
        hls, profile = load_hls_single_frame(scene_dir)
        if hls is None:
            log.warning(f"  Failed to load HLS bands — skip")
            stats["no_hls"] += 1
            continue

        full_H, full_W = hls.shape[1], hls.shape[2]
        log.info(f"  HLS shape: {hls.shape}")

        # Build full-tile label from existing patches
        label_full = np.full((full_H, full_W), -1, dtype=np.int32)
        key = (tile, fire_date_str)
        npz_paths = patch_lookup.get(key, [])

        if not npz_paths:
            log.warning(f"  No existing patches for label — skip")
            continue

        for npz_path in npz_paths:
            lbl, meta = load_label_from_npz(npz_path)
            window = meta["window"]  # [row, col, h, w]
            r0, c0, h, w = window

            if r0 + h <= full_H and c0 + w <= full_W and lbl.shape == (h, w):
                label_full[r0:r0 + h, c0:c0 + w] = lbl

        fire_coverage = int((label_full == 1).sum())
        log.info(f"  Label coverage: {fire_coverage} fire pixels from {len(npz_paths)} patches")

        if fire_coverage == 0:
            log.warning(f"  No fire pixels in label — skip")
            continue

        # Fill unlabeled pixels as "not burned" (label=0) — outside the labeled
        # windows, the tile is unburned forest/land that provides negative samples.
        # Only keep -1 (ignore) for pixels that were explicitly NaN in the labels.
        unlabeled = label_full == -1
        label_full[unlabeled] = 0

        # Extract patches
        patches = extract_patches(hls, label_full)
        n_fire = sum(1 for p in patches if p[4])
        n_bg = len(patches) - n_fire
        log.info(f"  Patches: {n_fire} fire + {n_bg} background")

        for p_idx, (hls_p, lbl_p, r0, c0, is_fire, fire_px) in enumerate(patches):
            tag = "f" if is_fire else "bg"
            pid = f"{tile}_{fire_date.strftime('%Y%m%d')}_post_{tag}{p_idx:04d}"
            out_path = OUT_DIR / split / f"patch_{pid}.npz"

            patch_meta = {
                "patch_id": pid,
                "tile": tile,
                "fire_date": fire_date.isoformat(),
                "scene_date": scene_date.isoformat(),
                "gap_days": gap_days,
                "split": split,
                "tier": tier if is_fire else "NEGATIVE",
                "fire_pixels": fire_px,
                "window": [r0, c0, PATCH_SIZE, PATCH_SIZE],
                "mode": "postfire",
            }

            save_patch(out_path, hls_p, lbl_p, patch_meta)
            manifest_rows.append({
                "path": str(out_path.relative_to(ROOT)),
                "patch_id": pid,
                "tile": tile,
                "fire_date": fire_date_str,
                "scene_date": scene_date.date().isoformat(),
                "gap_days": gap_days,
                "split": split,
                "tier": tier if is_fire else "NEGATIVE",
                "fire_pixels": fire_px,
                "is_fire": 1 if is_fire else 0,
            })

            if is_fire:
                stats["fire"] += 1
            else:
                stats["bg"] += 1

    # Save manifest
    out_manifest = OUT_DIR / "manifest.csv"
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(manifest_rows)
    df.to_csv(out_manifest, index=False)

    print("\n" + "=" * 65)
    print("POST-FIRE DATASET BUILD COMPLETE")
    print("=" * 65)
    print(f"\nPatches -> {OUT_DIR}")
    print(f"Manifest -> {out_manifest}")
    print(f"\nStats:")
    print(f"  Fire patches:     {stats['fire']}")
    print(f"  Background:       {stats['bg']}")
    print(f"  No post-fire HLS: {stats['no_scene']}")
    print(f"  HLS load fail:    {stats['no_hls']}")

    if len(df) > 0:
        print(f"\nSplit summary:")
        for split, grp in df.groupby("split"):
            nf = int(grp["is_fire"].sum())
            nn = len(grp) - nf
            print(f"  {split:6s}: {len(grp):5d} total ({nf} fire + {nn} bg)")

        print(f"\nGap distribution:")
        fire_df_out = df[df["is_fire"] == 1]
        if len(fire_df_out) > 0:
            print(f"  Mean gap:   {fire_df_out['gap_days'].mean():.1f} days")
            print(f"  Median gap: {fire_df_out['gap_days'].median():.1f} days")
            print(f"  Min/Max:    {fire_df_out['gap_days'].min()}-{fire_df_out['gap_days'].max()} days")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build post-fire burn scar patches")
    parser.add_argument("--max-events", type=int, default=None,
                        help="Limit number of events (for smoke testing)")
    args = parser.parse_args()
    build_dataset(max_events=args.max_events)
