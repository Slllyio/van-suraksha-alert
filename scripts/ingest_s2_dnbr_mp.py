"""Stage 7 — Ingest Sentinel-2 seasonal dNBR burn masks for MP at 30m.

Third BA source (alongside MCD64 500m + FireCCI 250m). At 30m resolution, S2
catches fires as small as ~0.1 ha, vastly finer than either predecessor.

Method (Parks 2014 RBR-style thresholding):
  - Pre-fire composite: median S2 L2A Oct 1 - Jan 31 (peak greenness, pre-season)
  - Post-fire composite: median S2 L2A Jun 1 - Aug 31 (post-season)
  - NBR = (B8 - B12) / (B8 + B12)   [NIR-narrow minus SWIR2]
  - dNBR = NBR_pre - NBR_post       [positive = burned]
  - Threshold dNBR >= 0.15          [Parks 2014 "low severity" floor]
  - Mask non-forest using Dynamic World forest probability >= 0.30
  - Clip clouds via S2 SCL mask on both composites

Output: data_lake/burnt_area/s2_dnbr_mp_{year}.tif (30m, uint8 0/1 binary burn mask)

Burn-date field: unlike MCD64/FireCCI, S2 dNBR does NOT give a per-pixel burn
date. We assign `burn_doy = 120` (April 30, mid-fire-season) as a placeholder
for Andela flood-fill. Andela clustering still works — clusters represent
spatially-contiguous burned patches; temporal tolerance doesn't apply for the
annual binary product.

Usage:
  python scripts/ingest_s2_dnbr_mp.py --queue                # all 2019-2026
  python scripts/ingest_s2_dnbr_mp.py --queue --year 2024
  python scripts/ingest_s2_dnbr_mp.py --status
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import ee

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ee.Initialize(project="van-suraksha-alert")

ROOT = Path(__file__).resolve().parents[1]
DRIVE_FOLDER = "burnt_area_s2_dnbr"

MP_GEOM = (
    ee.FeatureCollection("FAO/GAUL/2015/level1")
    .filter(ee.Filter.eq("ADM1_NAME", "Madhya Pradesh"))
    .geometry()
)

YEARS = list(range(2019, 2027))  # Sentinel-2 L2A fully available from 2019
DNBR_THRESHOLD = 0.15             # Parks 2014 low-severity floor
FOREST_PROB_MIN = 0.30            # DW forest probability
S2_CLOUD_PROB_MAX = 35            # SCL-based cloud threshold


def mask_clouds_s2_sr(img: ee.Image) -> ee.Image:
    """Mask clouds using Sentinel-2 SCL band (L2A product)."""
    scl = img.select("SCL")
    # Keep: 4=vegetation, 5=not-vegetated, 6=water, 7=unclassified
    # Mask: 3=cloud-shadow, 8=cloud-medium, 9=cloud-high, 10=thin-cirrus, 11=snow
    mask = scl.gte(4).And(scl.lte(7))
    return img.updateMask(mask).divide(10000)  # scale to reflectance


def compute_nbr(img: ee.Image) -> ee.Image:
    """NBR = (B8 - B12) / (B8 + B12)."""
    return img.expression("(NIR - SWIR2) / (NIR + SWIR2)", {
        "NIR": img.select("B8"),
        "SWIR2": img.select("B12"),
    }).rename("nbr")


def build_yearly_s2_dnbr(year: int) -> ee.Image:
    """Build annual S2 dNBR burn mask for a year."""
    # Pre-season: previous year Oct 1 - current year Jan 31
    pre_start = f"{year - 1}-10-01"
    pre_end = f"{year}-01-31"
    # Post-season: current year Jun 1 - Aug 31
    post_start = f"{year}-06-01"
    post_end = f"{year}-08-31"

    s2_col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(MP_GEOM)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 60))
    )

    pre = s2_col.filterDate(pre_start, pre_end).map(mask_clouds_s2_sr)
    post = s2_col.filterDate(post_start, post_end).map(mask_clouds_s2_sr)

    pre_nbr = pre.map(compute_nbr).median().rename("nbr_pre")
    post_nbr = post.map(compute_nbr).median().rename("nbr_post")
    dnbr = pre_nbr.subtract(post_nbr).rename("dnbr")

    # Forest mask from Dynamic World (same year's dry season)
    dw_year = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterBounds(MP_GEOM)
        .filterDate(pre_start, pre_end)
        .select("trees")
        .mean()
        .rename("forest_prob")
    )
    forest_mask = dw_year.gte(FOREST_PROB_MIN)

    burn_mask = dnbr.gte(DNBR_THRESHOLD).And(forest_mask).rename("burn")
    # Assign burn_doy=120 (April 30) as placeholder — Andela doesn't use sub-annual for binary products
    burn_doy = burn_mask.multiply(120).rename("burn_doy")

    # Cast all to float32 for uniform export dtype (GEE requires compatible bands)
    return burn_doy.addBands(dnbr).addBands(burn_mask).toFloat().set("year", year)


def queue_exports(years: list[int]) -> int:
    log.info("Queueing %d S2 dNBR exports at 30m over MP...", len(years))
    for year in years:
        img = build_yearly_s2_dnbr(year).clip(MP_GEOM)
        task = ee.batch.Export.image.toDrive(
            image=img,
            description=f"s2_dnbr_mp_{year}",
            folder=DRIVE_FOLDER,
            fileNamePrefix=f"s2_dnbr_mp_{year}",
            region=MP_GEOM,
            scale=30,
            crs="EPSG:4326",
            maxPixels=int(5e9),
        )
        task.start()
        log.info("  %d queued (id=%s)", year, task.id[:12])
    log.info("\nStatus: python scripts/ingest_s2_dnbr_mp.py --status")
    log.info("Download later: python scripts/download_burnt_area_exports.py (needs --product s2 support)")
    return 0


def check_status() -> int:
    tasks = ee.batch.Task.list()[:60]
    by_state: dict[str, list[str]] = {}
    for t in tasks:
        s = t.status()
        if "s2_dnbr_mp" in s.get("description", ""):
            by_state.setdefault(s["state"], []).append(s["description"])
    for state, descs in sorted(by_state.items()):
        log.info("[%s] %d tasks", state, len(descs))
        for d in sorted(descs)[:15]:
            log.info("  - %s", d)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--queue", action="store_true")
    grp.add_argument("--status", action="store_true")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()

    if args.queue:
        years = [args.year] if args.year else YEARS
        return queue_exports(years)
    return check_status()


if __name__ == "__main__":
    raise SystemExit(main())
