"""
ABM Ensemble Averaging (10 Runs)

Runs 10 stochastic simulations of the ABM for the same year (2019)
and averages their ignition grids to produce a smoother probability density map.
This reduces noise from individual stochastic agents and stabilizes the
spatial correlation (R) against FIRMS/VIIRS ground truth.

Output: data_lake/fire_detections/abm_ensemble_density_100m.npy
"""
import sys, time, json
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter, zoom
from scipy.stats import pearsonr

sys.path.append(str(Path(__file__).parent.parent))
from src.abm.model import VillageFireEconomy

GRID_W, GRID_H = 1140, 1390
NUM_RUNS = 10
YEAR = 2019

def main():
    print("=" * 70)
    print(f"  ABM ENSEMBLE AVERAGING ({NUM_RUNS} RUNS)")
    print(f"  Target Year: {YEAR}")
    print("=" * 70)
    
    ensemble_grid = np.zeros((GRID_H, GRID_W), dtype=np.float64)
    run_stats = []
    
    t_start = time.time()
    
    for i in range(NUM_RUNS):
        print(f"\n  [Run {i+1}/{NUM_RUNS}] Running 90-day simulation...")
        t0 = time.time()
        
        # New model instance for each run (new random state)
        model = VillageFireEconomy(
            width=GRID_W, height=GRID_H, num_villagers=50000,
            year=YEAR, human_density_multiplier=20.0
        )
        
        for d in range(90):
            model.step()
            
        run_grid = model.ignition_grid.astype(np.float64)
        ensemble_grid += run_grid
        
        elapsed = time.time() - t0
        ignitions = int(run_grid.sum())
        run_stats.append(ignitions)
        print(f"    Completed in {elapsed:.1f}s | Ignitions: {ignitions:,}")
        
    # Compute Average
    avg_grid = ensemble_grid / NUM_RUNS
    
    # Save Ensemble Grid
    out_path = Path("data_lake/fire_detections/abm_ensemble_density_100m.npy")
    np.save(out_path, avg_grid)
    
    total_elapsed = time.time() - t_start
    print(f"\n{'='*70}")
    print(f"  ENSEMBLE COMPLETE")
    print(f"{'='*70}")
    print(f"  Total Time: {total_elapsed/60:.1f} minutes")
    print(f"  Mean Ignitions: {np.mean(run_stats):.1f} (+/- {np.std(run_stats):.1f})")
    print(f"  Total Ignitions Sum: {int(ensemble_grid.sum()):,}")
    print(f"  Ensemble saved to: {out_path}")
    
    # ── VALIDATION ──
    print(f"\n  VALIDATING ENSEMBLE VS GROUND TRUTH:")
    
    # 1. Load Ground Truth
    # MODIS
    mod_raw = np.load('data_lake/fire_detections/firms_fire_season_grid.npy')
    zh, zw = GRID_H/mod_raw.shape[0], GRID_W/mod_raw.shape[1]
    modis = zoom(mod_raw, (zh, zw), order=0).astype(np.float64)
    # VIIRS 2019
    viirs = np.load('data_lake/fire_detections/viirs_fire_density_100m_2019.npy').astype(np.float64)
    
    print(f"\n  {'Sigma':>8} | {'MODIS R':>12} | {'VIIRS R':>12}")
    print(f"  {'-'*8}-+-{'-'*12}-+-{'-'*12}")
    
    for sigma in [0, 5, 10, 20, 50]:
        if sigma == 0:
            a, m, v = avg_grid, modis, viirs
        else:
            a = gaussian_filter(avg_grid, sigma=sigma)
            m = gaussian_filter(modis, sigma=sigma)
            v = gaussian_filter(viirs, sigma=sigma)
            
        rm, _ = pearsonr(a.flatten(), m.flatten())
        rv, _ = pearsonr(a.flatten(), v.flatten())
        print(f"  {sigma:8d} | {rm:>12.6f} | {rv:>12.6f}")

if __name__ == "__main__":
    main()
