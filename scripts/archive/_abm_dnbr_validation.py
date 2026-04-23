"""
ABM Secondary Validation: dNBR (Non-Forest)

Correlates ABM ensemble ignition density against Sentinel-2 dNBR labels.
Focuses ONLY on non-forest pixels (biomass < threshold) to avoid 
false positives from deciduous forest senescence in March/April.

Data Sources:
- ABM: data_lake/fire_detections/abm_ensemble_density_100m.npy
- Biomass: data_lake/land_cover/abm_biomass_1140x1390.npy
- Labels: data_lake/fire_labels_v2/ (label_*.tif)
"""
from pyproj import Transformer

# Configuration
GRID_W, GRID_H = 1140, 1390
LON_RANGE = (76.80, 77.85)
LAT_RANGE = (23.85, 25.10)

BIOMASS_THRESHOLD = 0.1  # Non-forest < 0.1 (agriculture/scrub)

def main():
    print("=" * 70)
    print("  ABM SECONDARY VALIDATION: dNBR (NON-FOREST)")
    print("=" * 70)
    
    # 1. Load ABM Ensemble
    abm_path = Path("data_lake/fire_detections/abm_ensemble_density_100m.npy")
    if not abm_path.exists():
        print(f"  ERROR: {abm_path} not found. Run ensemble script first.")
        return
    abm_grid = np.load(abm_path).astype(np.float64)
    
    # 2. Load Biomass and create Non-Forest Mask
    bio_path = Path("data_lake/land_cover/abm_biomass_1140x1390.npy")
    if not bio_path.exists():
        print(f"  ERROR: {bio_path} not found.")
        return
    biomass = np.load(bio_path)
    # Match the 'Fixed' ABM grid orientation (row 0 = North)
    biomass = np.flipud(np.fliplr(biomass))
    non_forest_mask = (biomass < BIOMASS_THRESHOLD)
    print(f"  Non-Forest Pixels: {non_forest_mask.sum():,} / {GRID_W*GRID_H:,} ({100*non_forest_mask.sum()/(GRID_W*GRID_H):.1f}%)")
    
    # 3. Prepare Grid Coordinates (Centers)
    lats = np.linspace(LAT_RANGE[1], LAT_RANGE[0], GRID_H)
    lons = np.linspace(LON_RANGE[0], LON_RANGE[1], GRID_W)
    LON_G, LAT_G = np.meshgrid(lons, lats)
    
    # 4. Aggregate 2019 dNBR Labels
    print("\n  Aggregating 2019 Sentinel-2 dNBR labels...")
    label_dir = Path("data_lake/fire_labels_v2")
    label_files = list(label_dir.rglob("label_2019*.tif"))
    print(f"  Found {len(label_files)} labels for 2019.")
    
    dnbr_grid = np.zeros((GRID_H, GRID_W), dtype=np.float32)
    
    for i, lp in enumerate(label_files):
        if i % 10 == 0:
            print(f"    Processing [{i}/{len(label_files)}] {lp.name}...")
            
        with rasterio.open(lp) as src:
            # Transformer from WGS84 to Raster CRS
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_to_coords=True)
            
            # Map grid centers to raster coords
            x_raw, y_raw = transformer.transform(LON_G, LAT_G)
            
            # Filter points within raster bounds to avoid out-of-bounds index errors
            bounds = src.bounds
            in_bounds = (x_raw >= bounds.left) & (x_raw <= bounds.right) & \
                        (y_raw >= bounds.bottom) & (y_raw <= bounds.top)
            
            if not np.any(in_bounds):
                continue
                
            # Sample raster at in-bounds points
            rows, cols = src.index(x_raw[in_bounds], y_raw[in_bounds])
            data = src.read(1)
            
            # Use clipped indices
            rows = np.clip(rows, 0, src.height - 1)
            cols = np.clip(cols, 0, src.width - 1)
            
            samples = data[rows, cols]
            
            # Update grid (handle NaNs as 0)
            local_vals = np.zeros_like(x_raw, dtype=np.float32)
            local_vals[in_bounds] = np.nan_to_num(samples)
            dnbr_grid += local_vals
            
    # 5. Filter and Mask
    # Mask out Forest
    abm_nf = abm_grid[non_forest_mask]
    dnbr_nf = dnbr_grid[non_forest_mask]
    
    # Remove NaNs and Infs (just in case)
    valid = np.isfinite(abm_nf) & np.isfinite(dnbr_nf)
    abm_final = abm_nf[valid]
    dnbr_final = dnbr_nf[valid]
    
    print(f"\n  Final Non-Forest Comparison Size: {len(abm_final):,} pixels")
    
    # 5. Correlation
    print(f"\n  {'Sigma':>8} | {'Non-Forest R':>15}")
    print(f"  {'-'*8}-+-{'-'*15}")
    
    for sigma in [0, 5, 10, 20, 50]:
        if sigma == 0:
            a, d = abm_grid, dnbr_grid
        else:
            a = gaussian_filter(abm_grid, sigma=sigma)
            d = gaussian_filter(dnbr_grid, sigma=sigma)
            
        # Apply mask AFTER smoothing
        a_nf = a[non_forest_mask]
        d_nf = d[non_forest_mask]
        
        r, _ = pearsonr(a_nf.flatten(), d_nf.flatten())
        print(f"  {sigma:8d} | {r:>15.6f}")

if __name__ == "__main__":
    main()
