"""Check sanity of downloaded MP HLS tiles — verify bands have real reflectance values."""
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window

TILES_DIR = Path("data_lake/v6e_chips/_mp_hls_l30_2023_dryseason_tiles")


def main():
    tiles = sorted(TILES_DIR.glob("*.tif"))
    print(f"Checking {len(tiles)} tiles")
    print("=" * 90)
    all_ok = True
    rng = np.random.default_rng(42)
    for t in tiles:
        with rasterio.open(t) as src:
            H, W = src.shape
            size_gb = t.stat().st_size / 1e9
            # Sample 5 random 200x200 windows
            samples = []
            for _ in range(5):
                y = rng.integers(0, max(1, H - 200))
                x = rng.integers(0, max(1, W - 200))
                w = src.read(window=Window(x, y, 200, 200))
                samples.append(w)
            stacked = np.concatenate(samples, axis=2)  # (bands, 200, 1000)

            band_str = []
            mean_nonzero_pct = 0
            for b in range(src.count):
                band = stacked[b]
                nonzero = band[band > 0]
                pct = len(nonzero) / band.size * 100
                mean_nonzero_pct += pct
                if len(nonzero) > 0:
                    band_str.append(f"b{b+1}: {nonzero.mean():.0f} ({pct:.0f}%)")
                else:
                    band_str.append(f"b{b+1}: 0 (0%)")
            mean_nonzero_pct /= src.count

            name = t.name
            ok = mean_nonzero_pct > 10  # at least 10% of pixels should be valid
            status = "OK" if ok else "EMPTY"
            all_ok = all_ok and ok
            print(f"{status:6s} | {size_gb:5.2f} GB | {H}x{W} | {name}")
            print(f"       | {' '.join(band_str)}")

    print("=" * 90)
    if all_ok:
        print("ALL TILES SANE — ready to merge")
    else:
        print("SOME TILES EMPTY — check GEE export config")


if __name__ == "__main__":
    main()
