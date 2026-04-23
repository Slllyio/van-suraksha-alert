"""
COVID Multi-Year Validation: 2019 (normal) vs 2020 (lockdown) vs 2021 (post-lockdown)

Tests the ABM's core causal hypothesis: human activity drives fire ignitions.
If lockdown (2020) correctly suppresses fires compared to normal years,
it validates the human-fire causal mechanism.

Compares ABM predictions against VIIRS 375m ground truth for each year.
"""
import sys, time, json
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter
from scipy.stats import pearsonr

sys.path.append(str(Path(__file__).parent.parent))
from src.abm.model import VillageFireEconomy

GRID_W, GRID_H = 1140, 1390

def run_year(year, n_days=90):
    """Run ABM for a given year and return ignition grid + daily counts."""
    print(f"\n  Running year={year}...")
    t0 = time.time()
    model = VillageFireEconomy(
        width=GRID_W, height=GRID_H, num_villagers=50000,
        year=year, human_density_multiplier=20.0
    )
    daily = []
    for d in range(n_days):
        model.step()
        daily.append(model.human_ignitions_today)
    elapsed = time.time() - t0
    grid = model.ignition_grid.astype(np.float64)
    print(f"    Time: {elapsed:.1f}s | Ignitions: {int(grid.sum())} | Daily mean: {np.mean(daily):.1f} | CV: {np.std(daily)/max(np.mean(daily),1):.3f}")
    return grid, daily


def compare_to_viirs(abm_grid, year):
    """Compare ABM grid to VIIRS ground truth for a given year."""
    viirs_path = Path(f"data_lake/fire_detections/viirs_fire_density_100m_{year}.npy")
    if not viirs_path.exists():
        print(f"    No VIIRS data for {year}")
        return None
    
    viirs = np.load(str(viirs_path)).astype(np.float64)
    
    results = {}
    for sigma in [0, 5, 10, 20, 50]:
        if sigma == 0:
            a, v = abm_grid, viirs
        else:
            a = gaussian_filter(abm_grid, sigma=sigma)
            v = gaussian_filter(viirs, sigma=sigma)
        try:
            r, _ = pearsonr(a.flatten(), v.flatten())
        except Exception:
            r = 0.0  # Zero-variance grid (e.g., full lockdown)
        results[sigma] = r
    
    return results


def main():
    print("=" * 70)
    print("  COVID MULTI-YEAR VALIDATION")
    print("  2019 (Normal) vs 2020 (Lockdown) vs 2021 (Post-lockdown)")
    print("=" * 70)
    
    years = [2019, 2020, 2021]
    all_results = {}
    
    for year in years:
        grid, daily = run_year(year)
        viirs_r = compare_to_viirs(grid, year)
        all_results[year] = {
            'total_ignitions': int(grid.sum()),
            'daily_mean': float(np.mean(daily)),
            'daily_cv': float(np.std(daily) / max(np.mean(daily), 1)),
            'nonzero_cells': int(np.count_nonzero(grid)),
            'viirs_r': viirs_r,
            'daily': daily
        }
    
    # ── COMPARISON TABLE ──
    print("\n" + "=" * 70)
    print("  MULTI-YEAR COMPARISON")
    print("=" * 70)
    
    print(f"\n{'Metric':<25} | {'2019 (Normal)':>15} | {'2020 (Lockdown)':>15} | {'2021 (Post)':>15}")
    print(f"{'-'*25}-+-{'-'*15}-+-{'-'*15}-+-{'-'*15}")
    
    for metric in ['total_ignitions', 'daily_mean', 'daily_cv', 'nonzero_cells']:
        vals = [all_results[y][metric] for y in years]
        if isinstance(vals[0], float):
            print(f"{metric:<25} | {vals[0]:>15.2f} | {vals[1]:>15.2f} | {vals[2]:>15.2f}")
        else:
            print(f"{metric:<25} | {vals[0]:>15,} | {vals[1]:>15,} | {vals[2]:>15,}")
    
    # VIIRS correlation
    print(f"\nVIIRS 375m Correlation:")
    for sigma in [0, 5, 10, 20, 50]:
        vals = []
        for y in years:
            r = all_results[y]['viirs_r']
            vals.append(r[sigma] if r else float('nan'))
        print(f"  sigma={sigma:3d} | {vals[0]:>+.6f} | {vals[1]:>+.6f} | {vals[2]:>+.6f}")
    
    # ── LOCKDOWN SUPPRESSION TEST ──
    print(f"\n{'='*70}")
    print(f"  LOCKDOWN SUPPRESSION TEST")
    print(f"{'='*70}")
    
    ign_2019 = all_results[2019]['total_ignitions']
    ign_2020 = all_results[2020]['total_ignitions']
    ign_2021 = all_results[2021]['total_ignitions']
    
    suppression = 1.0 - (ign_2020 / max(ign_2019, 1))
    recovery = (ign_2021 / max(ign_2019, 1)) - 1.0
    
    print(f"  2019 ignitions: {ign_2019:,}")
    print(f"  2020 ignitions: {ign_2020:,} ({100*suppression:+.1f}% vs 2019)")
    print(f"  2021 ignitions: {ign_2021:,} ({100*recovery:+.1f}% vs 2019)")
    
    # VIIRS ground truth comparison  
    print(f"\n  VIIRS Ground Truth (fire detections in Guna AOI):")
    for y in years:
        vp = Path(f"data_lake/fire_detections/viirs_fire_density_100m_{y}.npy")
        if vp.exists():
            v = np.load(str(vp))
            print(f"    {y}: {int(v.sum()):,} detections")
    
    # ── SAVE RESULTS ──
    with open('data_lake/fire_detections/covid_validation_results.json', 'w') as f:
        # Convert daily lists to scalars for JSON if needed, but here I'll just save the whole thing
        # but pearonr dict needs string keys for JSON
        serializable_results = {}
        for y, res in all_results.items():
            serializable_results[str(y)] = {
                'total_ignitions': res['total_ignitions'],
                'daily_mean': res['daily_mean'],
                'daily_cv': res['daily_cv'],
                'nonzero_cells': res['nonzero_cells'],
                'viirs_r': {str(k): v for k, v in res['viirs_r'].items()} if res['viirs_r'] else None
            }
        json.dump(serializable_results, f, indent=2)
    print(f"\n  Saved results to data_lake/fire_detections/covid_validation_results.json")

    print(f"\n  VERDICT:")
    if ign_2020 < ign_2019 * 0.5:
        print(f"  ABM: 2020 lockdown correctly SUPPRESSES fires ({100*suppression:.0f}% reduction)")
    elif ign_2020 < ign_2019 * 0.9:
        print(f"  ABM: 2020 lockdown PARTIALLY suppresses fires ({100*suppression:.0f}% reduction)")
    elif ign_2020 == 0:
        print(f"  ABM: 2020 lockdown COMPLETELY suppresses fires (100% reduction)")
    else:
        print(f"  ABM: 2020 lockdown has MINIMAL effect ({100*suppression:.0f}% change)")
        print(f"  WARNING: COVID lockdown should significantly reduce human ignitions!")


if __name__ == "__main__":
    main()
