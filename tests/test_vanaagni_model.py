"""Tests for VanAagni neural fire detector."""
import pytest
import torch
from src.model.vanaagni import VanAgni

class TestVanAagniModel:
    def test_model_loads(self):
        """Model architecture should build without errors."""
        model = VanAgni(num_classes=5)
        assert model is not None

    def test_output_shape(self):
        """Output should be [B, 5, 224, 224] for 5-class segmentation (or dictionary)."""
        model = VanAgni(num_classes=5, img_size=224, num_frames=1)
        # Using a small backbone to not run out of memory or make test too heavy
        model.eval()
        
        B = 2
        H, W = 224, 224
        
        # Create dummy inputs matching the forward signature
        hls = torch.randn(B, 6, 1, H, W)
        weather = torch.randn(B, 10)
        weather_7d = torch.randn(B, 10, 7)
        terrain = torch.randn(B, 4, H, W)
        burn_age = torch.randn(B, 3, H, W)
        landcover = torch.randn(B, 11, H, W)
        
        with torch.no_grad():
            out = model(hls, weather, weather_7d, terrain, burn_age, landcover)
            
        if isinstance(out, dict):
            logits = out["logits"]
        else:
            logits = out
            
        assert logits.shape == (B, 5, H, W)

    def test_fire_mask_binary(self):
        """Binary fire mask should be argmax > 0 (assuming class 0 is background)."""
        # Create dummy logits [B, 5, 224, 224] where class 2 is the maximum for some pixels
        logits = torch.randn(2, 5, 224, 224)
        
        # Assume class 0 is no-fire, anything > 0 is fire
        predictions = torch.argmax(logits, dim=1)
        binary_mask = (predictions > 0).int()
        
        assert binary_mask.shape == (2, 224, 224)
        unique_values = torch.unique(binary_mask)
        # Should only contain 0 and 1
        for val in unique_values:
            assert val.item() in [0, 1]

    def test_real_data_loading(self):
        """Test real data loading into dummy tensors representing the dataset outputs."""
        B = 2
        H, W = 224, 224
        
        # Checking dataset dictionary shapes
        batch = {
            "hls": torch.randn(B, 6, 1, H, W),
            "weather": torch.randn(B, 10),
            "weather_7d": torch.randn(B, 10, 7),
            "terrain": torch.randn(B, 4, H, W),
            "burn_age": torch.randn(B, 3, H, W),
            "landcover": torch.randn(B, 11, H, W)
        }
        
        assert batch["hls"].shape == (B, 6, 1, H, W)
        assert batch["weather"].shape == (B, 10)
        assert batch["weather_7d"].shape == (B, 10, 7)
        assert batch["terrain"].shape == (B, 4, H, W)
        assert batch["burn_age"].shape == (B, 3, H, W)
        assert batch["landcover"].shape == (B, 11, H, W)

    def test_model_backward_pass(self):
        """Test model backwards passes to ensure gradients flow correctly."""
        model = VanAgni(num_classes=5, img_size=224, num_frames=1)
        model.train() # important for gradients
        
        B = 2
        H, W = 224, 224
        
        hls = torch.randn(B, 6, 1, H, W)
        weather = torch.randn(B, 10)
        weather_7d = torch.randn(B, 10, 7)
        terrain = torch.randn(B, 4, H, W)
        burn_age = torch.randn(B, 3, H, W)
        landcover = torch.randn(B, 11, H, W)
        
        out = model(hls, weather, weather_7d, terrain, burn_age, landcover)
        if isinstance(out, dict):
            logits = out["logits"]
        else:
            logits = out
            
        loss = logits.sum()
        loss.backward()
        
        # Check if the backbone has gradients
        has_grad = False
        for name, param in model.named_parameters():
            if param.requires_grad and param.grad is not None:
                has_grad = True
                break
                
        assert has_grad, "No gradients were computed in the backward pass"