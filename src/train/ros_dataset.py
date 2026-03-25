"""
Muhurta-2D ROS Training Dataset
===============================
Prepares 7-channel environmental tensors for training the ROS U-Net.
Pairs historical fire states (T_0) with subsequent observed states (T_1)
using REAL FIRMS detections, terrain GeoTIFFs, and FWI weather data.

Input Stack (7 Channels):
0: Fire Mask T_0
1: Slope (degrees, from Copernicus DEM)
2: Aspect Sin (from Copernicus DEM)
3: Aspect Cos (from Copernicus DEM)
4: Fuel Dryness (FWI DMC z-score as proxy)
5: Wind U (from FWI weather, km/h * cos(wind_dir))
6: Wind V (from FWI weather, km/h * sin(wind_dir))

Target:
Fire Mask T_1 (observed FIRMS detections 24-48h later)
"""

import torch
from torch.utils.data import Dataset
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta
import logging

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_LAKE = ROOT / "data_lake"
TERRAIN_DIR = DATA_LAKE / "terrain"

# Spatial parameters
GRID_SIZE = 128          # pixels per side
PIXEL_RES_DEG = 0.0003  # ~30m at 24°N latitude
CLUSTER_DIST_DEG = 0.05  # ~5km — fires within this distance are same event
MAX_GAP_DAYS = 2         # T_1 must be 1-2 days after T_0


class ROSSpreadDataset(Dataset):
    def __init__(self, firms_csv_path=None, terrain_dir=None, transform=None):
        self.terrain_dir = Path(terrain_dir) if terrain_dir else TERRAIN_DIR
        self.transform = transform

        # Load real FIRMS data
        self.df = self._load_firms_data(firms_csv_path)
        self.samples = self._prepare_temporal_pairs()

        # Lazy-loaded terrain rasters
        self._slope_src = None
        self._aspect_src = None

        # Load FWI weather data
        self._fwi = self._load_fwi()

        log.info(f"ROS Dataset: {len(self.samples)} real temporal pairs from "
                 f"{len(self.df)} FIRMS detections")

    def _load_firms_data(self, csv_path):
        """Load real FIRMS fire detections from MODIS SP parquets."""
        if csv_path and Path(csv_path).exists():
            df = pd.read_csv(csv_path)
            df["acq_date"] = pd.to_datetime(df["acq_date"])
            return df

        # Default: load all MODIS SP parquets
        frames = []
        modis_dir = DATA_LAKE / "fire_detections" / "firms_modis_sp"
        for f in sorted(modis_dir.glob("*.parquet")):
            frames.append(pd.read_parquet(f))
        if not frames:
            log.warning("No FIRMS data found — dataset will be empty")
            return pd.DataFrame(columns=["latitude", "longitude", "acq_date", "frp"])

        df = pd.concat(frames, ignore_index=True)
        df["acq_date"] = pd.to_datetime(df["acq_date"])
        return df

    def _load_fwi(self):
        """Load FWI daily data for weather context."""
        fwi_path = DATA_LAKE / "fire_weather" / "fwi_daily.parquet"
        if not fwi_path.exists():
            return None
        fwi = pd.read_parquet(fwi_path)
        fwi["date"] = pd.to_datetime(fwi["date"])
        return fwi

    def _prepare_temporal_pairs(self):
        """
        Find real consecutive-day fire observations in the same area.
        A temporal pair is: detections on day D (T_0) and day D+1 or D+2 (T_1)
        within CLUSTER_DIST_DEG of each other, indicating fire persistence/spread.
        """
        if len(self.df) == 0:
            return []

        df = self.df.copy()
        df = df.dropna(subset=["latitude", "longitude", "acq_date"])
        df = df.sort_values("acq_date").reset_index(drop=True)

        pairs = []
        dates = sorted(df["acq_date"].dt.date.unique())

        for i, d0 in enumerate(dates):
            fires_t0 = df[df["acq_date"].dt.date == d0]

            for gap in range(1, MAX_GAP_DAYS + 1):
                d1 = d0 + timedelta(days=gap)
                fires_t1 = df[df["acq_date"].dt.date == d1]
                if fires_t1.empty:
                    continue

                # For each T_0 cluster center, check if T_1 has fires nearby
                for _, f0 in fires_t0.iterrows():
                    lat0, lon0 = f0["latitude"], f0["longitude"]
                    nearby = fires_t1[
                        (abs(fires_t1["latitude"] - lat0) < CLUSTER_DIST_DEG) &
                        (abs(fires_t1["longitude"] - lon0) < CLUSTER_DIST_DEG)
                    ]
                    if len(nearby) > 0:
                        pairs.append({
                            "lat": lat0, "lon": lon0,
                            "t0": str(d0), "t1": str(d1),
                            "frp_t0": float(f0.get("frp", 10.0)),
                            "n_t0": len(fires_t0[
                                (abs(fires_t0["latitude"] - lat0) < CLUSTER_DIST_DEG) &
                                (abs(fires_t0["longitude"] - lon0) < CLUSTER_DIST_DEG)
                            ]),
                            "n_t1": len(nearby),
                            "fires_t0": fires_t0[
                                (abs(fires_t0["latitude"] - lat0) < CLUSTER_DIST_DEG) &
                                (abs(fires_t0["longitude"] - lon0) < CLUSTER_DIST_DEG)
                            ][["latitude", "longitude", "frp"]].to_dict("records"),
                            "fires_t1": nearby[["latitude", "longitude", "frp"]].to_dict("records"),
                        })

        # Deduplicate by (lat rounded, lon rounded, t0) to avoid overlapping pairs
        seen = set()
        unique_pairs = []
        for p in pairs:
            key = (round(p["lat"], 2), round(p["lon"], 2), p["t0"])
            if key not in seen:
                seen.add(key)
                unique_pairs.append(p)

        log.info(f"Found {len(unique_pairs)} temporal pairs from {len(dates)} fire days")
        return unique_pairs

    def _open_terrain(self):
        """Lazy-load terrain rasters."""
        if self._slope_src is not None:
            return
        try:
            import rasterio
            slope_path = self.terrain_dir / "slope_guna_30m.tif"
            aspect_path = self.terrain_dir / "aspect_guna_30m.tif"
            if slope_path.exists():
                self._slope_src = rasterio.open(slope_path)
            if aspect_path.exists():
                self._aspect_src = rasterio.open(aspect_path)
        except Exception as e:
            log.warning(f"Could not open terrain rasters: {e}")

    def _extract_terrain_patch(self, lat, lon):
        """Extract slope/aspect patches from real GeoTIFFs centered on (lat, lon)."""
        self._open_terrain()
        half = GRID_SIZE // 2

        slope_patch = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32)
        aspect_patch = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32)

        if self._slope_src is not None:
            try:
                from rasterio.transform import rowcol
                row, col = rowcol(self._slope_src.transform, lon, lat)
                H, W = self._slope_src.shape
                r0 = max(0, row - half)
                c0 = max(0, col - half)
                r1 = min(H, r0 + GRID_SIZE)
                c1 = min(W, c0 + GRID_SIZE)

                if r1 > r0 and c1 > c0:
                    s = self._slope_src.read(1)[r0:r1, c0:c1]
                    slope_patch[:s.shape[0], :s.shape[1]] = s

                if self._aspect_src is not None:
                    a = self._aspect_src.read(1)[r0:r1, c0:c1]
                    aspect_patch[:a.shape[0], :a.shape[1]] = a
            except Exception:
                pass

        return slope_patch, aspect_patch

    def _get_weather(self, date_str):
        """Get real weather values for a date from FWI data."""
        if self._fwi is None:
            return 0.0, 5.0, 0.0  # fallback: no dryness, light wind

        dt = pd.to_datetime(date_str)
        row = self._fwi[self._fwi["date"] == dt]
        if row.empty:
            return 0.0, 5.0, 0.0

        r = row.iloc[0]
        # Fuel dryness: DMC z-score (higher = drier = more flammable)
        dmc_mean = self._fwi["dmc"].mean()
        dmc_std = max(self._fwi["dmc"].std(), 1.0)
        dryness = (r.get("dmc", 0) - dmc_mean) / dmc_std

        wind_kmh = r.get("wind_kmh", 5.0)
        # Wind direction not in FWI data — use a simplified approach:
        # predominant westerly wind direction in central India during fire season
        wind_dir_rad = np.radians(270)  # approximate westerly
        wind_u = wind_kmh * np.cos(wind_dir_rad)
        wind_v = wind_kmh * np.sin(wind_dir_rad)

        return float(dryness), float(wind_u), float(wind_v)

    def _build_fire_mask(self, center_lat, center_lon, fire_points):
        """Build a binary fire mask from real FIRMS detection points."""
        mask = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32)
        half = GRID_SIZE // 2

        for fp in fire_points:
            dlat = fp["latitude"] - center_lat
            dlon = fp["longitude"] - center_lon
            # Convert degree offset to pixel offset
            row = half - int(dlat / PIXEL_RES_DEG)
            col = half + int(dlon / PIXEL_RES_DEG)

            if 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE:
                # FIRMS detection covers ~375m (VIIRS) ≈ ~12 pixels at 30m
                frp = fp.get("frp", 10.0)
                radius = max(2, min(8, int(frp / 10)))  # FRP-scaled footprint
                r0 = max(0, row - radius)
                r1 = min(GRID_SIZE, row + radius + 1)
                c0 = max(0, col - radius)
                c1 = min(GRID_SIZE, col + radius + 1)
                mask[r0:r1, c0:c1] = 1.0

        return mask

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        lat, lon = sample["lat"], sample["lon"]

        # Build fire masks from real FIRMS points
        fire_mask_t0 = self._build_fire_mask(lat, lon, sample["fires_t0"])
        fire_mask_t1 = self._build_fire_mask(lat, lon, sample["fires_t1"])

        # Load real terrain
        slope, aspect = self._extract_terrain_patch(lat, lon)

        # Load real weather
        dryness, wind_u, wind_v = self._get_weather(sample["t0"])

        # Build 7-channel input stack
        aspect_rad = np.radians(aspect)
        stack = np.stack([
            fire_mask_t0,
            slope,
            np.sin(aspect_rad),
            np.cos(aspect_rad),
            np.full((GRID_SIZE, GRID_SIZE), dryness, dtype=np.float32),
            np.full((GRID_SIZE, GRID_SIZE), wind_u, dtype=np.float32),
            np.full((GRID_SIZE, GRID_SIZE), wind_v, dtype=np.float32),
        ], axis=0)

        target = fire_mask_t1[np.newaxis, ...]  # (1, H, W)

        if self.transform:
            stack = self.transform(stack)

        return torch.from_numpy(stack), torch.from_numpy(target)


if __name__ == "__main__":
    ds = ROSSpreadDataset()
    print(f"Dataset size: {len(ds)} samples")
    if len(ds) > 0:
        x, y = ds[0]
        print(f"Input shape: {x.shape}, Target shape: {y.shape}")
        print(f"Fire pixels T0: {(x[0] > 0).sum()}, T1: {(y[0] > 0).sum()}")
        print(f"Slope range: {x[1].min():.1f}-{x[1].max():.1f} degrees")
        print(f"Sample: lat={ds.samples[0]['lat']:.3f}, lon={ds.samples[0]['lon']:.3f}")
        print(f"  T0={ds.samples[0]['t0']}, T1={ds.samples[0]['t1']}")
        print(f"  n_fires: T0={ds.samples[0]['n_t0']}, T1={ds.samples[0]['n_t1']}")
