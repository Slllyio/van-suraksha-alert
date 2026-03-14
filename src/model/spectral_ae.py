"""
VanAagni Spectral Fingerprint Auto-Encoder
==========================================
Learns the 'normal' spectral relationship between Sentinel-2 bands for the 
Guna Forest ecosystem. Used for sub-pixel anomaly detection (unseen change).

Architecture: Simple MLP Bottleneck
Input: 6 spectral bands (B02, B03, B04, B8A, B11, B12)
Output: Reconstructed 6 bands
Metric: MSE (Reconstruction Error) -> Anomaly Score
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

class SpectralAE(nn.Module):
    def __init__(self, n_bands=6, latent_dim=2):
        super(SpectralAE, self).__init__()
        
        # Encoder: 6 -> 4 -> 2
        self.encoder = nn.Sequential(
            nn.Linear(n_bands, 4),
            nn.ReLU(),
            nn.Linear(4, latent_dim),
            nn.ReLU()
        )
        
        # Decoder: 2 -> 4 -> 6
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 4),
            nn.ReLU(),
            nn.Linear(4, n_bands),
            nn.Sigmoid() # HLS data is normalized 0-1
        )

    def forward(self, x):
        # x shape: (N, 6)
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent

    def compute_anomaly_score(self, x):
        """
        Returns the pixel-wise MSE reconstruction error.
        Higher error = Higher Anomaly.
        """
        self.eval()
        with torch.no_grad():
            reconstructed, _ = self.forward(x)
            # Per-pixel MSE across bands
            error = torch.mean((x - reconstructed)**2, dim=1)
        return error

if __name__ == "__main__":
    # Test with dummy pixel data
    model = SpectralAE()
    # 100 pixels, 6 bands each
    dummy_pixels = torch.rand(100, 6)
    
    recon, latent = model(dummy_pixels)
    score = model.compute_anomaly_score(dummy_pixels)
    
    print(f"Input Shape: {dummy_pixels.shape}")
    print(f"Latent Shape: {latent.shape}")
    print(f"Mean Anomaly Score: {score.mean().item():.6f}")
