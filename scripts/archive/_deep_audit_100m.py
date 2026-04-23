"""
Deep Empirical Audit: MiroFish ABM 100m Resolution
Quantitative spatial and temporal analysis vs FIRMS ground truth.
"""
import sys, time
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter, zoom, label
from scipy.stats import pearsonr, spearmanr

sys.path.append(str(Path(__file__).parent.parent))
from src.abm.model import VillageFireEconomy

def run_deep_audit():
    print("="*70)
    print("  DEEP EMPIRICAL AUDIT: MiroFish 100m ABM vs FIRMS Ground Truth")
    print("="*70)
    
    # -- 1. Run ABM Simulation --
    grid_w, grid_h = 1140, 1390
    print(f"\n[1] Initializing ABM: {grid_w}x{grid_h} grid, 50k agents...")
    t0 = time.time()
    model = VillageFireEconomy(width=grid_w, height=grid_h, num_villagers=50000,
                               year=2019, human_density_multiplier=20.0)
    init_time = time.time() - t0
    print(f"    Init time: {init_time:.2f}s")
    
    # Track daily ignitions for temporal analysis
    daily_ignitions = []
    t0 = time.time()
    for day in range(90):
        model.step()
        daily_ignitions.append(model.human_ignitions_today)
    sim_time = time.time() - t0
    
    # ABM output is in raster-native space (row0=North) -- no flip needed
    abm_grid = model.ignition_grid
    total_abm_ignitions = int(abm_grid.sum())
    abm_nonzero = int(np.count_nonzero(abm_grid))
    
    print(f"    Sim time (90 steps): {sim_time:.2f}s ({sim_time/90:.3f}s/step)")
    print(f"    Total ABM ignitions: {total_abm_ignitions}")
    print(f"    Cells with ignitions: {abm_nonzero} / {grid_w*grid_h} ({100*abm_nonzero/(grid_w*grid_h):.4f}%)")
    print(f"    Daily ignitions min/max/mean: {min(daily_ignitions)}/{max(daily_ignitions)}/{np.mean(daily_ignitions):.1f}")
    
    # -- 2. Load FIRMS Ground Truth --
    print(f"\n[2] Loading FIRMS ground truth...")
    firms_path = Path("data_lake/fire_detections/firms_fire_season_grid.npy")
    if not firms_path.exists():
        firms_path = Path("data_lake/fire_detections/empirical_ignition_grid.npy")
    
    firms_raw = np.load(str(firms_path))
    print(f"    FIRMS raw shape: {firms_raw.shape}")
    print(f"    FIRMS total detections: {int(firms_raw.sum())}")
    print(f"    FIRMS non-zero cells: {np.count_nonzero(firms_raw)}")
    
    # Resample to ABM grid
    zh = abm_grid.shape[0] / firms_raw.shape[0]
    zw = abm_grid.shape[1] / firms_raw.shape[1]
    firms_grid = zoom(firms_raw, (zh, zw), order=0)
    print(f"    FIRMS resampled shape: {firms_grid.shape}")
    firms_nonzero = int(np.count_nonzero(firms_grid))
    print(f"    FIRMS resampled non-zero: {firms_nonzero} ({100*firms_nonzero/(grid_w*grid_h):.4f}%)")
    
    # -- 3. RAW Spatial Correlation (No Smoothing) --
    print(f"\n[3] RAW Spatial Correlation (cell-by-cell, NO smoothing):")
    # Test all orientations
    orientations = {
        "original": abm_grid,
        "v_flip": np.flipud(abm_grid),
        "h_flip": np.fliplr(abm_grid),
        "both_flip": np.flipud(np.fliplr(abm_grid)),
    }
    
    best_raw_r = -1
    best_raw_name = "none"
    best_grid = abm_grid
    for name, grid in orientations.items():
        if grid.shape != firms_grid.shape:
            continue
        r, p = pearsonr(grid.flatten(), firms_grid.flatten())
        rho, _ = spearmanr(grid.flatten(), firms_grid.flatten())
        print(f"    {name:12s}: Pearson R={r:.6f} (p={p:.2e}), Spearman rho={rho:.6f}")
        if r > best_raw_r:
            best_raw_r = r
            best_raw_name = name
            best_grid = grid
    
    print(f"    >>> Best raw orientation: {best_raw_name} (R={best_raw_r:.6f})")
    
    # -- 4. Smoothed Correlation at Multiple Sigma Values --
    print(f"\n[4] Smoothed Correlation (Gaussian) at varying sigma:")
    for sigma in [1, 2, 5, 10, 20, 30, 50]:
        abm_s = gaussian_filter(best_grid.astype(np.float64), sigma=sigma)
        firms_s = gaussian_filter(firms_grid.astype(np.float64), sigma=sigma)
        r, p = pearsonr(abm_s.flatten(), firms_s.flatten())
        print(f"    Sigma={sigma:3d}: Pearson R={r:.6f} (p={p:.2e})")
    
    # -- 5. Hotspot Overlap Analysis --
    print(f"\n[5] Hotspot Overlap Analysis (Top-5% cells):")
    abm_s = gaussian_filter(best_grid.astype(np.float64), sigma=10)
    firms_s = gaussian_filter(firms_grid.astype(np.float64), sigma=10)
    
    abm_thresh = np.percentile(abm_s, 95)
    firms_thresh = np.percentile(firms_s, 95)
    
    abm_hot = abm_s >= abm_thresh
    firms_hot = firms_s >= firms_thresh
    
    overlap = np.logical_and(abm_hot, firms_hot).sum()
    union = np.logical_or(abm_hot, firms_hot).sum()
    iou = overlap / union if union > 0 else 0
    
    print(f"    ABM hotspot cells (top 5%): {abm_hot.sum()}")
    print(f"    FIRMS hotspot cells (top 5%): {firms_hot.sum()}")
    print(f"    Overlap (Intersection): {overlap}")
    print(f"    Union: {union}")
    print(f"    IoU (Jaccard): {iou:.4f}")
    print(f"    Dice Coefficient: {2*overlap/(abm_hot.sum()+firms_hot.sum()):.4f}")
    
    # -- 6. Connected Component Analysis --
    print(f"\n[6] Connected Component (Cluster) Analysis:")
    abm_labels, abm_n = label(abm_hot)
    firms_labels, firms_n = label(firms_hot)
    print(f"    ABM clusters: {abm_n}")
    print(f"    FIRMS clusters: {firms_n}")
    
    # -- 7. Agent Movement Check --
    print(f"\n[7] Agent Movement & Code Integrity Check:")
    # Check if agents actually moved during simulation
    agent_positions = []
    for agent in model.agents:
        if hasattr(agent, 'economic_need'):  # VillageAgent
            agent_positions.append(agent.pos)
    
    if agent_positions:
        xs = [p[0] for p in agent_positions]
        ys = [p[1] for p in agent_positions]
        print(f"    Agent X range: [{min(xs)}, {max(xs)}] (grid width: {grid_w})")
        print(f"    Agent Y range: [{min(ys)}, {max(ys)}] (grid height: {grid_h})")
        print(f"    Unique agent positions: {len(set(agent_positions))} / {len(agent_positions)}")
        
        # Check spatial spread
        x_std = np.std(xs)
        y_std = np.std(ys)
        print(f"    Agent position StdDev: X={x_std:.1f}, Y={y_std:.1f}")
        if x_std < 50 or y_std < 50:
            print(f"    WARNING:  WARNING: Agents are CLUSTERED, not spread across landscape!")
        else:
            print(f"    [OK]  Agents have good spatial spread")
    
    # -- 8. Biomass Grid Reality Check --
    print(f"\n[8] Biomass Grid Reality Check:")
    bio = model.biomass_grid
    print(f"    Shape: {bio.shape}")
    print(f"    Min/Max/Mean: {bio.min():.4f} / {bio.max():.4f} / {bio.mean():.4f}")
    print(f"    Non-zero cells: {np.count_nonzero(bio)} ({100*np.count_nonzero(bio)/bio.size:.2f}%)")
    print(f"    Cells > 0.5 (forested): {(bio > 0.5).sum()} ({100*(bio > 0.5).sum()/bio.size:.2f}%)")
    
    # -- 9. Agent Movement Verification --
    print(f"\n[9] AGENT MOVEMENT VERIFICATION:")
    # Compare initial home positions vs final positions to verify agents moved
    villager_count = sum(1 for a in model.agents if hasattr(a, 'economic_need'))
    print(f"    VillageAgent count: {villager_count}")
    print(f"    Movement mode: suitability_grid (vectorized, no ForestPatch objects)")

    # Measure displacement from home
    displacements = []
    for agent in model.agents:
        if hasattr(agent, 'economic_need') and agent.unique_id in model._agent_homes:
            home = model._agent_homes[agent.unique_id]
            curr = agent.pos
            dist = ((curr[0]-home[0])**2 + (curr[1]-home[1])**2)**0.5
            displacements.append(dist)

    if displacements:
        d = np.array(displacements)
        print(f"    Agents with home tracking: {len(d)}")
        print(f"    Displacement (cells): mean={d.mean():.1f}, median={np.median(d):.1f}, max={d.max():.1f}")
        print(f"    Displacement (km):    mean={d.mean()*0.1:.1f}, median={np.median(d)*0.1:.1f}, max={d.max()*0.1:.1f}")
        pct_moved = 100 * np.sum(d > 0) / len(d)
        pct_far = 100 * np.sum(d > 30) / len(d)  # >3km
        print(f"    Agents that moved: {pct_moved:.1f}%")
        print(f"    Agents >3km from home: {pct_far:.1f}%")
        if d.mean() < 5:
            print(f"    WARNING:  WARNING: Low mean displacement ({d.mean()*0.1:.1f}km) -- agents may be stuck")
        else:
            print(f"    [OK]  Agents show meaningful movement from settlements into landscape")

    # Suitability grid diagnostics
    print(f"\n    Suitability grid stats:")
    suit = model.suitability_grid
    print(f"      Range: [{suit.min():.4f}, {suit.max():.4f}]")
    print(f"      Mean: {suit.mean():.4f}, Std: {suit.std():.4f}")
    print(f"      Non-zero: {np.count_nonzero(suit)} ({100*np.count_nonzero(suit)/suit.size:.1f}%)")
    
    # -- 10. Temporal Profile --
    print(f"\n[10] Temporal Profile (daily ignitions over 90 days):")
    q1 = np.percentile(daily_ignitions, 25)
    q3 = np.percentile(daily_ignitions, 75)
    print(f"    Q1={q1:.0f}, Median={np.median(daily_ignitions):.0f}, Q3={q3:.0f}")
    print(f"    Coefficient of Variation: {np.std(daily_ignitions)/np.mean(daily_ignitions):.4f}")
    
    # -- FINAL VERDICT --
    print(f"\n{'='*70}")
    print(f"  FINAL VERDICT")
    print(f"{'='*70}")
    if best_raw_r < 0.01:
        print(f"  RAW Pearson R = {best_raw_r:.6f} -> ESSENTIALLY ZERO correlation")
    elif best_raw_r < 0.05:
        print(f"  RAW Pearson R = {best_raw_r:.6f} -> NEGLIGIBLE correlation")
    elif best_raw_r < 0.1:
        print(f"  RAW Pearson R = {best_raw_r:.6f} -> WEAK but DETECTABLE correlation")
    else:
        print(f"  RAW Pearson R = {best_raw_r:.6f} -> MODERATE correlation")
    
    print(f"  Hotspot IoU = {iou:.4f}")
    if iou < 0.05:
        print(f"  -> Hotspot overlap is VERY LOW. ABM and FIRMS fire zones DO NOT match well.")
    elif iou < 0.15:
        print(f"  -> Hotspot overlap is MARGINAL. Some spatial agreement exists.")
    else:
        print(f"  -> Hotspot overlap is PROMISING. Spatial agreement is meaningful.")
    
    if displacements:
        mean_km = np.mean(displacements) * 0.1
        if mean_km < 0.5:
            print(f"\n  WARNING:  WARNING: Mean displacement only {mean_km:.1f}km -- agents barely move")
            print(f"  WARNING:  Consider increasing movement radius or adjusting suitability landscape")
        else:
            print(f"\n  [OK]  Agent movement verified: mean {mean_km:.1f}km displacement over {90} steps")

if __name__ == "__main__":
    run_deep_audit()
