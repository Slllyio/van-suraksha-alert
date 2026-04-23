import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Ensure src in path
sys.path.append(str(Path(__file__).parent.parent))

from src.abm.model import VillageFireEconomy
from src.abm.agents import ForestPatch, VillageAgent

def validate_spatial_topology():
    print("Generating spatial validation diagnostic...")
    grid_w, grid_h = 114, 139
    mult = 15.0
    
    # Run a high-fidelity simulation for 2019 (Normal Year)
    model = VillageFireEconomy(
        width=grid_w, 
        height=grid_h, 
        num_villagers=500, 
        year=2019, 
        human_density_multiplier=mult
    )
    
    # Simulate 30 days
    for _ in range(30):
        model.step()
        
    ignition_grid = model.ignition_grid
    
    # Plotting
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    # 1. Simulated Ignitions Heatmap
    im0 = axes[0].imshow(ignition_grid, cmap='hot', interpolation='nearest', origin='lower')
    axes[0].set_title(f"Simulated Ignitions (n={int(ignition_grid.sum())})")
    plt.colorbar(im0, ax=axes[0])
    
    # 2. Forest Patch Biomass (The "Where" indicator)
    # Reconstruct biomass layer from agents
    biomass_grid = np.zeros_like(ignition_grid)
    for agent in model.agents:
        if isinstance(agent, ForestPatch):
            x, y = agent.pos
            biomass_grid[y, x] = agent.biomass
            
    im1 = axes[1].imshow(biomass_grid, cmap='YlGn', interpolation='nearest', origin='lower')
    axes[1].set_title("Forest Biomass Distribution")
    plt.colorbar(im1, ax=axes[1])
    
    # 3. Normalized Probability Spatial Topology
    max_val = ignition_grid.max() if ignition_grid.max() > 0 else 1.0
    prob_grid = ignition_grid / max_val
    im2 = axes[2].imshow(prob_grid, cmap='plasma', interpolation='nearest', origin='lower')
    axes[2].set_title("Probability Topology [0, 1]")
    plt.colorbar(im2, ax=axes[2])
    
    save_path = Path("outputs/abm_spatial_validation.png")
    plt.tight_layout()
    plt.savefig(str(save_path))
    print(f"Spatial validation plot saved to {save_path}")

    # Calculate spatial concentration metric
    # High biomass cells should have higher ignition counts
    total_fires = ignition_grid.sum()
    if total_fires > 0:
        high_fuel_mask = biomass_grid > 0.7
        fires_in_fuel = ignition_grid[high_fuel_mask].sum()
        concentration = (fires_in_fuel / total_fires) * 100
        print(f"Spatial Quality: {concentration:.1f}% of ignitions occurred in high-biomass zones.")
    else:
        print("No fires generated for analysis.")

if __name__ == "__main__":
    validate_spatial_topology()
