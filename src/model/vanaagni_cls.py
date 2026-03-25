"""
src/model/vanaagni_cls.py
=========================
VanAgni Patch Classification Model — Binary fire detection at the patch level.

Architecture:
  Prithvi-EO-2.0-600M-TL backbone (frozen or LoRA)
      → CLS token (1280-d) + spatial mean pool (1280-d) → concat (2560-d)
      → WeatherEncoder(10 → 128) + ForecastWeatherEncoder(10×7 → 128) → fused (128-d)
      → TerrainEncoder(terrain+lc+burn_age → 64-d global pool)
      → Concat all (2560 + 128 + 64 = 2752-d)
      → MLP head → 1 logit (BCE)

Why this works when segmentation doesn't:
  1. ViT's CLS token is *designed* for global classification — no spatial upsampling
  2. ~59% fire patches in training — nearly balanced (vs 0.65% fire pixels)
  3. BCE loss gives strong gradient signal on every sample
  4. Only ~2M trainable params (head + weather + terrain) with frozen backbone
"""

import logging
import math
from typing import Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.model.prithvi_eo2_backbone import PrithviEO2Backbone, build_prithvi_eo2
from src.model.film_layers import WeatherEncoder, ForecastWeatherEncoder

log = logging.getLogger(__name__)


class TerrainGlobalEncoder(nn.Module):
    """Encode terrain + landcover + burn_age into a global feature vector."""

    def __init__(self, terrain_ch=4, lc_ch=11, burn_age_ch=3, out_dim=64):
        super().__init__()
        in_ch = terrain_ch + lc_ch + burn_age_ch  # 18
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, 32, 3, stride=2, padding=1),
            nn.BatchNorm2d(32),
            nn.GELU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.GELU(),
            nn.AdaptiveAvgPool2d(1),  # (B, 64, 1, 1)
        )
        self.fc = nn.Linear(64, out_dim)

    def forward(self, terrain, landcover, burn_age):
        x = torch.cat([terrain, landcover, burn_age], dim=1)  # (B, 18, H, W)
        x = self.conv(x).flatten(1)  # (B, 64)
        return self.fc(x)  # (B, out_dim)


class VanAgniCls(nn.Module):
    """
    Patch-level binary fire classification using Prithvi-EO-2.0 CLS token.

    Forward returns dict:
      logit  (B, 1)  raw logit for BCE loss
      prob   (B, 1)  sigmoid probability
    """

    def __init__(
        self,
        eo2_variant: str = "600M-TL",
        num_frames: int = 3,
        in_chans: int = 6,
        img_size: int = 224,
        freeze_backbone: bool = True,
        # Weather
        weather_input_dim: int = 10,
        weather_cond_dim: int = 128,
        # Terrain
        terrain_ch: int = 4,
        landcover_ch: int = 11,
        burn_age_ch: int = 3,
        terrain_dim: int = 64,
        # Head
        head_hidden: int = 256,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.img_size = img_size

        # -- Backbone --
        log.info(f"Building Prithvi-EO-2.0-{eo2_variant} backbone for classification...")
        self.backbone = build_prithvi_eo2(
            variant=eo2_variant, num_frames=num_frames,
            in_chans=in_chans, img_size=img_size,
        )
        self.embed_dim = self.backbone.embed_dim
        self.num_frames = num_frames
        self.grid_size = img_size // 14  # 224/14 = 16

        if freeze_backbone:
            log.info("[FROZEN] Backbone parameters frozen for classification")
            for p in self.backbone.parameters():
                p.requires_grad = False

        # -- Weather encoders (reuse from segmentation) --
        self.weather_enc = WeatherEncoder(weather_input_dim, 64, weather_cond_dim)
        self.forecast_enc = ForecastWeatherEncoder(weather_input_dim, 64, weather_cond_dim)
        self.cond_fuse = nn.Sequential(
            nn.Linear(weather_cond_dim * 2, weather_cond_dim),
            nn.GELU(),
        )

        # -- Terrain global encoder --
        self.terrain_enc = TerrainGlobalEncoder(
            terrain_ch, landcover_ch, burn_age_ch, terrain_dim,
        )

        # -- Classification head --
        # CLS (embed_dim) + mean_pool (embed_dim) + weather (cond_dim) + terrain (terrain_dim)
        feat_dim = self.embed_dim * 2 + weather_cond_dim + terrain_dim
        self.head = nn.Sequential(
            nn.LayerNorm(feat_dim),
            nn.Linear(feat_dim, head_hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(head_hidden, head_hidden // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(head_hidden // 2, 1),
        )

        # Bias init: ~59% fire in train → prior ≈ 0.59
        with torch.no_grad():
            fire_prior = 0.59
            self.head[-1].bias.data.fill_(math.log(fire_prior / (1 - fire_prior)))

        self._log_params()

    def _extract_cls_and_pool(self, hls: torch.Tensor):
        """
        Run backbone and extract CLS token + spatial mean pool.

        The backbone is frozen, so we run it under torch.no_grad() to avoid
        allocating intermediate activation tensors for backward — this saves
        ~4-6 GB VRAM on the 32-block 600M ViT.  Outputs are detached before
        returning so the head's backward graph starts fresh.

        Returns: (cls_feat, pool_feat) each (B, embed_dim)
        """
        bb = self.backbone._backbone
        B = hls.shape[0]

        # ── Frozen backbone: no_grad to save VRAM ──────────────────────
        with torch.no_grad():
            # Patch embed
            x = bb.patch_embed(hls)  # (B, D, T, Hp, Wp)
            Bx, D, T, Hp, Wp = x.shape
            x = x.flatten(2).transpose(1, 2)  # (B, T*Hp*Wp, D)

            # CLS token
            if hasattr(bb, "cls_token") and bb.cls_token is not None:
                cls_tokens = bb.cls_token.expand(B, -1, -1)
                x = torch.cat((cls_tokens, x), dim=1)

            # Positional embedding
            if hasattr(bb, "pos_embed") and bb.pos_embed is not None:
                x = x + bb.pos_embed

            # Run all transformer blocks
            for block in bb.blocks:
                x = block(x)

            # Apply final norm
            if hasattr(bb, "norm") and bb.norm is not None:
                x = bb.norm(x)

            # Extract CLS token (index 0) and spatial tokens
            cls_feat = x[:, 0, :]  # (B, D)
            spatial = x[:, 1:, :]  # (B, T*Hp*Wp, D)

            # Simple mean pool over spatial+temporal dimensions
            pool_feat = spatial.mean(dim=1)  # (B, D)

        # Detach so backward only flows through the head
        return cls_feat.detach(), pool_feat.detach()

    def forward(
        self,
        hls: torch.Tensor,
        weather: torch.Tensor,
        weather_7d: torch.Tensor,
        terrain: torch.Tensor,
        burn_age: torch.Tensor,
        landcover: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        # Backbone features
        cls_feat, pool_feat = self._extract_cls_and_pool(hls)

        # Weather conditioning
        w_curr = self.weather_enc(weather)
        w_7d = self.forecast_enc(weather_7d)
        weather_feat = self.cond_fuse(torch.cat([w_curr, w_7d], dim=1))

        # Terrain features
        terrain_feat = self.terrain_enc(terrain, landcover, burn_age)

        # Concat all features
        feat = torch.cat([cls_feat, pool_feat, weather_feat, terrain_feat], dim=1)

        # Classification head
        logit = self.head(feat)  # (B, 1)
        prob = torch.sigmoid(logit)

        return {"logit": logit, "prob": prob}

    def _log_params(self):
        total = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        backbone = sum(p.numel() for p in self.backbone.parameters())
        head = total - backbone
        log.info(
            f"VanAgniCls: {total:,} total  ({trainable:,} trainable)  "
            f"backbone={backbone:,} (frozen)  head={head:,}"
        )


def build_vanaagni_cls(cfg: dict) -> VanAgniCls:
    """Build VanAgniCls from config dict."""
    m = cfg.get("model", cfg)
    return VanAgniCls(
        eo2_variant=m.get("eo2_variant", "600M-TL"),
        num_frames=m.get("num_frames", 3),
        in_chans=m.get("in_chans", 6),
        img_size=m.get("img_size", 224),
        freeze_backbone=m.get("freeze_backbone", True),
        weather_input_dim=m.get("weather_input_dim", 10),
        weather_cond_dim=m.get("weather_cond_dim", 128),
        head_hidden=m.get("head_hidden", 256),
        dropout=m.get("dropout", 0.3),
    )
