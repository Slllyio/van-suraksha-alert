"""Stage 0 — Ellipse-fit pilot for v17 Tier H T0 rectification.

Goal: validate whether MP burn polygons are defensibly elliptical before
committing to physics-informed back-projection. If most burns fit well as
ellipses, the major axis + wind direction gives us ignition point; major axis
length / Rothermel ROS gives us time since ignition.

For each GOLD/SILVER burn mask (connected component ≥100 px):
  - Extract pixel coordinates of burn
  - PCA → eigenvectors, eigenvalues
  - Ellipse semi-axes = sqrt(eigenvalue × n_pixels) — area preserved
  - Compute aspect ratio = major/minor
  - Compute residual = |burn pixels outside ellipse| / |total burn pixels|
  - Compute compactness = burn_area / ellipse_area (should be ~0.785 = π/4 for perfect ellipse)

Pass criterion: ≥70% of fires with aspect ratio 1.3-5 AND residual < 30%
→ proceed with Tier H physics-informed back-projection
→ else: fall back to centroid + downslope-adjusted wind-gradient method

Output: docs/debug/ellipse_pilot.pdf with plots + JSON summary.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.backends.backend_pdf import PdfPages
from scipy.ndimage import label as cc_label

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
LABELS_DIR = ROOT / "data_lake" / "fire_labels_v2"
OUT_PDF = ROOT / "docs" / "debug" / "ellipse_pilot.pdf"
OUT_JSON = ROOT / "docs" / "debug" / "ellipse_pilot_summary.json"

MIN_COMPONENT_PX = 100  # drop noise specks


def load_gold_silver_masks(limit: int = 30) -> list[dict]:
    """Return metadata for GOLD/SILVER masks, sorted by area desc."""
    metas = list(LABELS_DIR.rglob("meta_*.json"))
    rows = []
    for m in metas:
        try:
            d = json.loads(m.read_text())
        except Exception:
            continue
        if d.get("tier") not in ("GOLD", "SILVER"):
            continue
        # Corresponding binary TIF
        date_str = d["fire_date"].replace("-", "")
        tile = d["tile"]
        binary = m.parent / f"binary_{date_str}_{tile}.tif"
        if not binary.exists():
            continue
        rows.append({
            "tier": d["tier"],
            "fire_date": d["fire_date"],
            "tile": tile,
            "binary_path": binary,
            "meta": d,
            "fire_px": d.get("fire_px_total", d.get("fire_px", 0)),
        })
    rows.sort(key=lambda r: -r["fire_px"])
    return rows[:limit]


def fit_pca_ellipse(rows: np.ndarray, cols: np.ndarray) -> dict:
    """Fit PCA ellipse to pixel coordinates.

    Returns dict with centroid, axes, orientation, eigenvalues, aspect_ratio.
    """
    coords = np.column_stack([cols, rows]).astype(np.float64)  # x=col, y=row
    centroid = coords.mean(axis=0)
    centered = coords - centroid
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # eigenvectors sorted ascending by eigval → reverse for major first
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    # Semi-axes (2σ covers ~95% of a normal; use 2*sqrt(eigval) = 2σ)
    semi_major = 2.0 * np.sqrt(max(eigvals[0], 1e-9))
    semi_minor = 2.0 * np.sqrt(max(eigvals[1], 1e-9))

    orientation_rad = np.arctan2(eigvecs[1, 0], eigvecs[0, 0])  # angle of major axis from +x

    return {
        "centroid_x": float(centroid[0]),
        "centroid_y": float(centroid[1]),
        "semi_major": float(semi_major),
        "semi_minor": float(semi_minor),
        "orientation_deg": float(np.degrees(orientation_rad)),
        "aspect_ratio": float(semi_major / max(semi_minor, 1e-9)),
    }


def compute_ellipse_residual(rows: np.ndarray, cols: np.ndarray, ell: dict) -> float:
    """Fraction of burn pixels OUTSIDE the fitted ellipse (0=perfect fit)."""
    cx, cy = ell["centroid_x"], ell["centroid_y"]
    a, b = ell["semi_major"], ell["semi_minor"]
    theta = np.radians(ell["orientation_deg"])
    # Transform to ellipse frame
    dx = cols - cx
    dy = rows - cy
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    xp = dx * cos_t + dy * sin_t
    yp = -dx * sin_t + dy * cos_t
    inside = (xp / a) ** 2 + (yp / b) ** 2 <= 1.0
    return float(1.0 - inside.mean())


def process_one_mask(row: dict) -> list[dict]:
    """Process one fire's binary mask, return per-component stats."""
    with rasterio.open(row["binary_path"]) as src:
        mask = src.read(1)
    # Binary masks store {0=bg, 1=burn, 255=nodata/other} — threshold for burn
    burn = (mask == 1)
    if burn.sum() < MIN_COMPONENT_PX:
        return []

    labeled, n_components = cc_label(burn)
    components = []
    for i in range(1, n_components + 1):
        comp_mask = labeled == i
        n_px = int(comp_mask.sum())
        if n_px < MIN_COMPONENT_PX:
            continue
        rr, cc = np.where(comp_mask)
        ell = fit_pca_ellipse(rr, cc)
        residual = compute_ellipse_residual(rr, cc, ell)
        # Compactness: burn_area / ellipse_area
        ellipse_area = np.pi * ell["semi_major"] * ell["semi_minor"]
        compactness = n_px / max(ellipse_area, 1.0)
        components.append({
            "tier": row["tier"],
            "fire_date": row["fire_date"],
            "tile": row["tile"],
            "n_px": n_px,
            "component_id": i,
            "aspect_ratio": ell["aspect_ratio"],
            "residual_fraction": residual,
            "compactness": float(compactness),
            "orientation_deg": ell["orientation_deg"],
            "semi_major": ell["semi_major"],
            "semi_minor": ell["semi_minor"],
            "ellipse": ell,
            "rows": rr,
            "cols": cc,
        })
    return components


def plot_component(ax, comp: dict) -> None:
    rr, cc = comp["rows"], comp["cols"]
    ax.scatter(cc, rr, s=0.3, c="darkred", alpha=0.6, label=f"burn (n={comp['n_px']})")
    ell = comp["ellipse"]
    ellipse_patch = mpatches.Ellipse(
        (ell["centroid_x"], ell["centroid_y"]),
        2 * ell["semi_major"], 2 * ell["semi_minor"],
        angle=ell["orientation_deg"], fill=False, edgecolor="blue", linewidth=2,
    )
    ax.add_patch(ellipse_patch)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_title(
        f"{comp['tier']} {comp['fire_date']} {comp['tile']}\n"
        f"aspect={comp['aspect_ratio']:.2f} resid={comp['residual_fraction']:.2%} compact={comp['compactness']:.2f}",
        fontsize=8,
    )
    ax.legend(fontsize=6, loc="upper right")


def main() -> int:
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading GOLD/SILVER burn masks (top 30 by size)...")
    rows = load_gold_silver_masks(limit=30)
    log.info("  %d masks loaded", len(rows))

    all_components: list[dict] = []
    log.info("Processing masks → connected components + ellipse fits...")
    for r in rows:
        comps = process_one_mask(r)
        log.info("  %s %s %s: %d components", r["tier"], r["fire_date"], r["tile"], len(comps))
        all_components.extend(comps)

    log.info("\nTotal components (≥%d px): %d", MIN_COMPONENT_PX, len(all_components))

    # Sort by n_px desc for plot (biggest = most informative)
    all_components.sort(key=lambda c: -c["n_px"])
    plot_components = all_components[:30]

    log.info("Plotting to %s...", OUT_PDF.relative_to(ROOT))
    with PdfPages(OUT_PDF) as pdf:
        for i in range(0, len(plot_components), 6):
            fig, axes = plt.subplots(2, 3, figsize=(15, 10))
            for j, ax in enumerate(axes.flat):
                if i + j >= len(plot_components):
                    ax.axis("off")
                    continue
                plot_component(ax, plot_components[i + j])
            plt.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

    # Summary stats
    aspects = np.array([c["aspect_ratio"] for c in all_components])
    residuals = np.array([c["residual_fraction"] for c in all_components])
    compactness = np.array([c["compactness"] for c in all_components])
    px = np.array([c["n_px"] for c in all_components])

    defensible_mask = (aspects >= 1.3) & (aspects <= 8.0) & (residuals <= 0.30)
    defensible_frac = float(defensible_mask.mean())

    summary = {
        "n_components": int(len(all_components)),
        "n_components_plotted": int(len(plot_components)),
        "aspect_ratio": {
            "median": float(np.median(aspects)), "p10": float(np.percentile(aspects, 10)),
            "p90": float(np.percentile(aspects, 90)), "max": float(aspects.max()),
        },
        "residual_fraction": {
            "median": float(np.median(residuals)), "p10": float(np.percentile(residuals, 10)),
            "p90": float(np.percentile(residuals, 90)),
        },
        "compactness_vs_pi_over_4": {
            "median": float(np.median(compactness)), "p10": float(np.percentile(compactness, 10)),
            "p90": float(np.percentile(compactness, 90)),
            "pi_over_4_reference": float(np.pi / 4),
        },
        "n_px": {
            "median": int(np.median(px)), "max": int(px.max()), "min": int(px.min()),
        },
        "defensibly_elliptical_fraction": defensible_frac,
        "defensibility_rule": "aspect_ratio in [1.3, 8.0] AND residual_fraction <= 0.30",
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))
    log.info("\n=== SUMMARY ===")
    for k, v in summary.items():
        log.info("  %s: %s", k, v)

    log.info("\n=== VERDICT ===")
    if defensible_frac >= 0.70:
        log.info("  PASS — %.1f%% of burn components fit defensibly as ellipses", defensible_frac * 100)
        log.info("  → Proceed with Tier H physics-informed back-projection")
    else:
        log.info("  FAIL — only %.1f%% of burn components fit defensibly", defensible_frac * 100)
        log.info("  → Fall back to centroid + downslope-adjusted wind-gradient method")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
