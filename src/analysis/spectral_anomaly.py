"""
VanAagni Spectral Anomaly Analyzer
==================================
Uses the Spectral Auto-Encoder to flag unseen changes in forest pixels.
This complements Prithvi-EO by identifying anomalies that don't fit 
historical burn patterns (e.g., new infrastructure, illegal logging, 
unknown disease).
"""

import torch
import numpy as np
import logging
from pathlib import Path
from src.model.spectral_ae import SpectralAE

log = logging.getLogger(__name__)

class SpectralAnomalyAnalyzer:
    def __init__(self, model_path: Optional[str] = None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SpectralAE().to(self.device)
        
        if model_path and Path(model_path).exists():
            self.model.load_state_dict(torch.load(model_path, map_location=self.device))
            log.info(f"Loaded Spectral AE from {model_path}")
        else:
            log.warning("No Spectral AE weights found. Using baseline initialization.")

    def score_chip(self, chip: np.ndarray) -> np.ndarray:
        """
        Scores a multi-spectral chip (6, H, W).
        Returns a (H, W) anomaly map.
        """
        # 1. Prepare data
        # chip shape: (6, H, W) -> flatten to (H*W, 6)
        c, h, w = chip.shape
        pixels = chip.reshape(c, -1).T
        pixels_t = torch.from_numpy(pixels).float().to(self.device)
        
        # 2. Compute Anomaly Score (MSE)
        scores_t = self.model.compute_anomaly_score(pixels_t)
        
        # 3. Reshape back to (H, W)
        scores = scores_t.cpu().numpy().reshape(h, w)
        
        # Normalize for visualization
        scores_norm = (scores - scores.min()) / (scores.max() - scores.min() + 1e-6)
        
        return scores_norm

if __name__ == "__main__":
    from typing import Optional
    logging.basicConfig(level=logging.INFO)
    
    # Test with dummy 128x128 chip
    analyzer = SpectralAnomalyAnalyzer()
    dummy_chip = np.random.uniform(0.1, 0.4, (6, 128, 128))
    
    # Inject a 'Spectral Anomaly' (e.g. a bright square)
    dummy_chip[:, 60:80, 60:80] = 0.9
    
    anomaly_map = analyzer.score_chip(dummy_chip)
    
    print(f"Chip Shape: {dummy_chip.shape}")
    print(f"Max Anomaly Score in injected zone: {anomaly_map[70, 70]:.3f}")
    print(f"Mean Background Anomaly: {anomaly_map[10, 10]:.3f}")
