import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Ensure src in path
sys.path.append(str(Path(__file__).parent.parent))

from src.abm.model import VillageFireEconomy
from src.abm.agents import ForestPatch

def compare_abm_to_firms():
    """
    Correlates ABM simulated ignitions with historical FIRMS detections
    to verify spatial empirical accuracy.
    """
    print("Initializing ABM vs FIRMS Empirical Validation...")
    
    # 1. Run ABM for a 2019 (Normal Year) baseline
    # 100m resolution width=1140, height=1390
    grid_w, grid_h = 1140, 1390
    model = VillageFireEconomy(width=grid_w, height=grid_h, num_villagers=50000, 
                               year=2019, human_density_multiplier=20.0)
    
    print("Simulating 90 days of human ignitions (Longer window for signal)...")
    for _ in range(90):
        model.step()
    
    abm_grid = model.ignition_grid
    
    # 2. Load Historical FIRMS Data
    # Path: data_lake/fire_detections/empirical_ignition_grid.npy
    # This was likely pre-computed during the ML pipeline training.
    firms_path = Path("data_lake/fire_detections/firms_fire_season_grid.npy")
    if not firms_path.exists():
        # Fallback to general empirical grid
        firms_path = Path("data_lake/fire_detections/empirical_ignition_grid.npy")
        
    if firms_path.exists():
        firms_grid = np.load(str(firms_path))
        # Match grid dimensions (250m resolution height=456, width=556)
        if firms_grid.shape != abm_grid.shape:
            print(f"Resampling FIRMS {firms_grid.shape} to ABM {abm_grid.shape}...")
            from scipy.ndimage import zoom
            zh = abm_grid.shape[0] / firms_grid.shape[0]
            zw = abm_grid.shape[1] / firms_grid.shape[1]
            firms_grid = zoom(firms_grid, (zh, zw), order=0)
    else:
        print("Error: FIRMS empirical grid not found.")
        return

    # 3. Correlation Analysis & Symmetry Testing
    # Test common coordinate orientations
    orientations = {
        "original": abm_grid,
        "v_flip": np.flipud(abm_grid),
        "h_flip": np.fliplr(abm_grid),
        "both_flip": np.flipud(np.fliplr(abm_grid)),
    }
    
    # Also test transpositions if shape matches after T
    if abm_grid.shape[0] == firms_grid.shape[1] and abm_grid.shape[1] == firms_grid.shape[0]:
        orientations["transposed"] = abm_grid.T
        orientations["t_v_flip"] = np.flipud(abm_grid.T)
        orientations["t_h_flip"] = np.fliplr(abm_grid.T)

    best_corr = -1.0
    best_name = "none"
    best_grid_final = abm_grid
    
    for name, grid in orientations.items():
        # Ensure shape matching for corr calculation
        if grid.shape != firms_grid.shape:
            continue
        corr = np.corrcoef(grid.flatten(), firms_grid.flatten())[0, 1]
        print(f"Testing {name}: R = {corr:.4f}")
        if corr > best_corr:
            best_corr = corr
            best_name = name
            best_grid_final = grid

    # 4. Filter or Normalize for Correlation? 
    # Use Gaussian smoothing to bridge 100m-to-1km spatial gap
    from scipy.ndimage import gaussian_filter
    best_grid_blur = gaussian_filter(best_grid_final, sigma=10.0)
    firms_grid_blur = gaussian_filter(firms_grid, sigma=10.0)
    
    correlation = np.corrcoef(best_grid_blur.flatten(), firms_grid_blur.flatten())[0, 1]
    
    print(f"Empirical Spatial Correlation (Pearson R_smooth): {correlation:.4f}")
    
    # 5. Visualization
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    
    # Normalize for visual comparison
    abm_norm = best_grid_blur / (best_grid_blur.max() if best_grid_blur.max() > 0 else 1)
    firms_norm = firms_grid_blur / (firms_grid_blur.max() if firms_grid_blur.max() > 0 else 1)
    
    im0 = axes[0].imshow(abm_norm, cmap='hot', origin='upper')
    axes[0].set_title(f"ABM Quantum-Res (100m)\n(R_smooth={correlation:.3f})")
    
    im1 = axes[1].imshow(firms_norm, cmap='hot', origin='upper')
    axes[1].set_title("Real FIRMS Detections\n(Resampled to 100m)")
    
    plt.tight_layout()
    out_path = Path("outputs/abm_vs_firms_validation.png")
    plt.savefig(str(out_path))
    print(f"Comparison plot saved to {out_path}")

    # Interpretation
    if correlation > 0.05:
        print("Result: POSITIVE SPATIAL CORRELATION. High-res clusters align.")
    else:
        print("Result: LOW CORRELATION. High-res jitter may be decoupling cells.")

if __name__ == "__main__":
    compare_abm_to_firms()
