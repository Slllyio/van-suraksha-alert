"""
VanAagni Generative Synthetic Data Factory
==========================================
Generates 'Black Swan' fire events for training the Prithvi-EO-2.0 backbone.
Uses the Muhurta-2D physics engine to guide the generation of synthetic 
spectral anomalies in Sentinel-2/HLS imagery.

Status: Cognitive Frontier (Level 6)
"""

import numpy as np
import logging
from pathlib import Path
from typing import Tuple

log = logging.getLogger(__name__)

class SyntheticFireFactory:
    def __init__(self):
        # Spectral signatures for 'burned' deciduous forest in Sentinel-2 bands
        # (Relative shifts in reflectance)
        self.BURN_SIGNATURE = {
            "Blue": 0.8,   # Slight drop (smoke scatter)
            "Green": 0.7,  # Drop (chlorophyll loss)
            "Red": 1.2,    # Slight spike (exposed soil)
            "NIR": 0.4,    # MASSIVE drop (cell structure destruction)
            "SWIR1": 1.8,  # Spike (moisture loss)
            "SWIR2": 2.5   # MASSIVE spike (ash and charcoal)
        }

    def generate_black_swan_event(
        self, 
        base_chip: np.ndarray, 
        phi_mask: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Takes a clean HLS chip (6 bands) and a physics-derived fire mask (phi).
        Injects synthetic spectral burn signatures into the pixels where phi <= 0.
        """
        # base_chip shape: (6, H, W)
        # phi_mask shape: (H, W)
        
        synthetic_chip = base_chip.copy()
        fire_pixels = phi_mask <= 0
        
        # Apply the spectral burn logic
        # Band order: Blue, Green, Red, NIR, SWIR1, SWIR2
        bands = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]
        
        for i, band_name in enumerate(bands):
            multiplier = self.BURN_SIGNATURE[band_name]
            # Add some natural variance to the synthetic burn
            noise = np.random.normal(1.0, 0.1, size=fire_pixels.shape)
            synthetic_chip[i, fire_pixels] *= (multiplier * noise[fire_pixels])

        # Add synthetic 'Smoke' haze over the NIR/Blue bands
        smoke_mask = fire_pixels.astype(float)
        # (Simplistic smoke blur implementation)
        synthetic_chip[0] += smoke_mask * 0.1 # Blue haze
        
        return synthetic_chip, fire_pixels.astype(np.uint8)

if __name__ == "__main__":
    # Test Scenario: 128x128 chip
    factory = SyntheticFireFactory()
    
    # Mock clean chip (normalized 0-1)
    clean_chip = np.random.uniform(0.1, 0.3, (6, 128, 128))
    
    # Mock physics mask (a diagonal fire front)
    y, x = np.ogrid[:128, :128]
    phi = x + y - 100 # Fire in the bottom-right corner
    
    synth_chip, label = factory.generate_black_swan_event(clean_chip, phi)
    
    print("\n--- 🎨 GENERATIVE SYNTHETIC FACTORY ---")
    print(f"Base Chip Mean Reflectance (NIR): {clean_chip[3].mean():.3f}")
    print(f"Synthetic Burn Mean (NIR): {synth_chip[3, label==1].mean():.3f}")
    print(f"Result: Success. Injected {label.sum()} synthetic burn pixels.")
    print("-" * 40)
