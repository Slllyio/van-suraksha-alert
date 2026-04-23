"""
THE MOST IMPORTANT TEST: Does the ABM add value beyond naive spatial priors?

Computes:
1. Naive baseline: 1/distance_to_settlement correlation with FIRMS
2. ABM ignition grid correlation with FIRMS
3. Delta: ABM improvement over naive baseline

If the ABM barely beats the naive baseline, it means agent behavior
(movement, foraging, FWI ignition) adds no predictive power —
the model is just a fancy settlement heat map.
"""
import sys, time
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter, zoom
from scipy.ndimage import label as ndimage_label
from scipy.stats import pearsonr, spearmanr

sys.path.append(str(Path(__file__).parent.parent))

def run_naive_baseline_test():
    print("=" * 70)
    print("  THE FUNDAMENTAL QUESTION: Does the ABM Add Value?")
    print("  Naive Baseline (1/settlement_distance) vs ABM vs FIRMS")
    print("=" * 70)

    grid_w, grid_h = 1140, 1390

    # ── 1. Build Naive Baseline: 1/distance_to_settlement ──
    print("\n[1] Building Naive Baseline (1/distance_to_settlement)...")
    
    # Method A: Use settlement distance raster if available
    import json
    set_path = Path("data/aoi/guna_settlements.json")
    if set_path.exists():
        with open(set_path, 'r') as f:
            settlements = json.load(f)
        
        # Build a settlement proximity grid at 100m
        naive_grid = np.zeros((grid_h, grid_w), dtype=np.float32)
        
        for s in settlements:
            pop = s.get('population_est', 500)
            sx = int(s.get('grid_x', 0) * grid_w / 114)  # Scale from 114-col to 1140-col
            sy = int(s.get('grid_y', 0) * grid_h / 139)  # Scale from 139-row to 1390-row
            sx = min(max(sx, 0), grid_w - 1)
            sy = min(max(sy, 0), grid_h - 1)
            
            # Gaussian spread: population-weighted, sigma proportional to sqrt(pop)
            # This mimics: "fire probability = f(distance to village, village size)"
            sigma = max(5, np.sqrt(pop) / 2)  # 5-50 cells depending on pop
            point = np.zeros((grid_h, grid_w), dtype=np.float32)
            point[sy, sx] = float(pop)
            naive_grid += gaussian_filter(point, sigma=sigma)
        
        # Normalize to [0, 1]
        if naive_grid.max() > 0:
            naive_grid = naive_grid / naive_grid.max()
        
        print(f"    Settlements loaded: {len(settlements)}")
        print(f"    Naive grid shape: {naive_grid.shape}")
        print(f"    Non-zero cells: {np.count_nonzero(naive_grid)} ({100*np.count_nonzero(naive_grid)/naive_grid.size:.1f}%)")
        print(f"    Mean/Max: {naive_grid.mean():.4f} / {naive_grid.max():.4f}")
    else:
        print("    ERROR: No settlement data found!")
        return

    # ── 2. Run ABM ──
    print("\n[2] Running ABM (50k agents, 90 days)...")
    from src.abm.model import VillageFireEconomy
    t0 = time.time()
    model = VillageFireEconomy(width=grid_w, height=grid_h, num_villagers=50000,
                               year=2019, human_density_multiplier=20.0)
    for day in range(90):
        model.step()
    sim_time = time.time() - t0
    abm_grid = model.ignition_grid.astype(np.float64)
    print(f"    Sim time: {sim_time:.1f}s")
    print(f"    ABM ignitions: {int(abm_grid.sum())}")

    # ── 3. Load FIRMS Ground Truth ──
    print("\n[3] Loading FIRMS ground truth...")
    firms_path = Path("data_lake/fire_detections/firms_fire_season_grid.npy")
    if not firms_path.exists():
        firms_path = Path("data_lake/fire_detections/empirical_ignition_grid.npy")
    firms_raw = np.load(str(firms_path))
    zh = grid_h / firms_raw.shape[0]
    zw = grid_w / firms_raw.shape[1]
    firms_grid = zoom(firms_raw, (zh, zw), order=0).astype(np.float64)
    print(f"    FIRMS shape: {firms_grid.shape}, detections: {int(firms_raw.sum())}")

    # ── 4. Test All Orientations for Both ──
    print("\n[4] Testing orientations...")
    
    def best_orientation(grid, firms, name):
        orientations = {
            "original": grid,
            "v_flip": np.flipud(grid),
            "h_flip": np.fliplr(grid),
            "both_flip": np.flipud(np.fliplr(grid)),
        }
        best_r, best_name, best_g = -1, "none", grid
        for oname, g in orientations.items():
            r, p = pearsonr(g.flatten(), firms.flatten())
            if r > best_r:
                best_r, best_name, best_g = r, oname, g
        print(f"    {name} best orientation: {best_name} (R={best_r:.6f})")
        return best_g, best_r, best_name
    
    naive_aligned, naive_raw_r, naive_orient = best_orientation(naive_grid, firms_grid, "NAIVE")
    abm_aligned, abm_raw_r, abm_orient = best_orientation(abm_grid, firms_grid, "ABM")

    # ── 5. Smoothed Correlation Comparison ──
    print("\n[5] Smoothed Correlation (Naive vs ABM vs FIRMS):")
    print(f"    {'Sigma':>8} | {'Naive R':>10} | {'ABM R':>10} | {'Delta':>10} | {'ABM adds value?':>16}")
    print(f"    {'-'*8}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*16}")
    
    results = []
    for sigma in [0, 1, 2, 5, 10, 20, 30, 50]:
        if sigma == 0:
            naive_s = naive_aligned
            abm_s = abm_aligned
            firms_s = firms_grid
        else:
            naive_s = gaussian_filter(naive_aligned, sigma=sigma)
            abm_s = gaussian_filter(abm_aligned, sigma=sigma)
            firms_s = gaussian_filter(firms_grid, sigma=sigma)
        
        r_naive, _ = pearsonr(naive_s.flatten(), firms_s.flatten())
        r_abm, _ = pearsonr(abm_s.flatten(), firms_s.flatten())
        delta = r_abm - r_naive
        pct = (delta / max(abs(r_naive), 0.001)) * 100
        verdict = "YES ✓" if delta > 0.01 else ("MARGINAL" if delta > 0 else "NO ✗")
        
        results.append((sigma, r_naive, r_abm, delta, pct))
        lbl = f"Raw" if sigma == 0 else f"σ={sigma}"
        print(f"    {lbl:>8} | {r_naive:>10.6f} | {r_abm:>10.6f} | {delta:>+10.6f} | {verdict:>16}")

    # ── 6. Hotspot IoU Comparison ──
    print("\n[6] Hotspot IoU (Top-5%):")
    for name, grid in [("NAIVE", naive_aligned), ("ABM", abm_aligned)]:
        gs = gaussian_filter(grid, sigma=10)
        fs = gaussian_filter(firms_grid, sigma=10)
        g_hot = gs >= np.percentile(gs, 95)
        f_hot = fs >= np.percentile(fs, 95)
        overlap = np.logical_and(g_hot, f_hot).sum()
        union = np.logical_or(g_hot, f_hot).sum()
        iou = overlap / union if union > 0 else 0
        print(f"    {name}: IoU={iou:.4f}, Overlap={overlap}, Union={union}")

    # ── 7. Cluster Count Comparison ──
    print("\n[7] Cluster Count:")
    for name, grid in [("NAIVE", naive_aligned), ("ABM", abm_aligned), ("FIRMS", firms_grid)]:
        gs = gaussian_filter(grid, sigma=10)
        hot = gs >= np.percentile(gs, 95)
        _, n = ndimage_label(hot)
        print(f"    {name}: {n} clusters")

    # ── 8. FINAL VERDICT ──
    print(f"\n{'='*70}")
    print(f"  VERDICT: DOES THE ABM ADD VALUE?")
    print(f"{'='*70}")
    
    # Key comparison at σ=10 (1km, FIRMS native resolution)
    sigma10 = [r for r in results if r[0] == 10][0]
    _, r_naive_10, r_abm_10, delta_10, pct_10 = sigma10
    
    print(f"  Naive Baseline R@σ=10:  {r_naive_10:.6f}")
    print(f"  ABM R@σ=10:             {r_abm_10:.6f}")
    print(f"  Delta:                  {delta_10:+.6f} ({pct_10:+.1f}%)")
    print()
    
    if delta_10 > 0.05:
        print(f"  ✓ ABM ADDS MEANINGFUL VALUE over naive settlement proximity.")
        print(f"    Agent behavior (movement, FWI ignition, foraging) contributes")
        print(f"    {pct_10:.0f}% improvement in spatial prediction.")
    elif delta_10 > 0.01:
        print(f"  ⚠️  ABM adds MARGINAL value over naive baseline.")
        print(f"    The {pct_10:.1f}% improvement suggests agent behavior contributes")
        print(f"    weakly. Most signal comes from settlement placement.")
    else:
        print(f"  ✗ ABM ADDS NO VALUE over naive settlement distance.")
        print(f"    The model is just a fancy settlement heat map.")
        print(f"    Agent movement, FWI modulation, and foraging behavior")
        print(f"    do not improve spatial prediction.")

if __name__ == "__main__":
    run_naive_baseline_test()
