import logging
import torch
import torch.nn as nn
import torch.nn.functional as F
from terratorch.models.backbones.prithvi_vit import PrithviViT

log = logging.getLogger(__name__)

_EO2_600M_ID = "ibm-nasa-geospatial/Prithvi-EO-2.0-600M"
_EO2_300M_ID = "ibm-nasa-geospatial/Prithvi-EO-2.0-300M"

_EO2_ARCH = {
    "600M":    {"embed_dim": 1280, "depth": 32, "num_heads": 16},
    "600M-TL": {"embed_dim": 1280, "depth": 32, "num_heads": 16},
    "300M":    {"embed_dim": 1024, "depth": 24, "num_heads": 16},
    "300M-TL": {"embed_dim": 1024, "depth": 24, "num_heads": 16},
}

class PrithviEO2Backbone(nn.Module):
    def __init__(self, pretrained, num_frames=3, in_chans=6, img_size=224, **kwargs):
        super().__init__()
        log.info(f"Loading Prithvi-EO-2.0 via PrithviViT: {pretrained}")
        
        self._backbone = PrithviViT(
            img_size=img_size,
            patch_size=14,
            num_frames=num_frames,
            in_chans=in_chans,
            embed_dim=kwargs.get("embed_dim", 1280),
            depth=kwargs.get("depth", 32),
            num_heads=kwargs.get("num_heads", 16),
            tubelet_size=1,
            pretrained=pretrained
        )

        self.embed_dim = kwargs.get("embed_dim", 1280)
        self.num_frames = num_frames
        
        # -- DirectML Compatibility Patch --------------------------------------
        if hasattr(self._backbone, "patch_embed"):
            target_pe = self._backbone.patch_embed
            if hasattr(target_pe, "proj") and isinstance(target_pe.proj, nn.Conv3d):
                log.info("Applying DirectML Conv3d compatibility patch...")
                old_proj = target_pe.proj
                new_proj = nn.Conv2d(
                    old_proj.in_channels, old_proj.out_channels,
                    kernel_size=old_proj.kernel_size[1:],
                    stride=old_proj.stride[1:],
                    padding=old_proj.padding[1:],
                    bias=(old_proj.bias is not None)
                )
                with torch.no_grad():
                    new_proj.weight.copy_(old_proj.weight.squeeze(2))
                    if old_proj.bias is not None:
                        new_proj.bias.copy_(old_proj.bias)
                
                target_pe.proj = new_proj
                
                def pe_forward(x):
                    B, C, T, H, W = x.shape
                    x = x.transpose(1, 2).reshape(B * T, C, H, W)
                    x = target_pe.proj(x)
                    _, D, Hp, Wp = x.shape
                    x = x.reshape(B, T, D, Hp, Wp).transpose(1, 2)
                    if hasattr(target_pe, "norm") and target_pe.norm is not None:
                        x = target_pe.norm(x)
                    return x
                
                target_pe.forward = pe_forward

    def forward(self, x):
        return self._backbone(x)

    def forward_features(self, x: torch.Tensor) -> torch.Tensor:
        """
        Extract full token sequence from the backbone.

        Args:
            x: (B, C, T, H, W)

        Returns:
            (B, N, embed_dim) token sequence (CLS token removed)
        """
        # patch_embed returns (B, D, T, Hp, Wp) for PrithviViT
        out = self._backbone.patch_embed(x)
        B, D, T, Hp, Wp = out.shape

        # Flatten to (B, T*Hp*Wp, D)
        out = out.flatten(2).transpose(1, 2)

        # Prepend CLS token
        if hasattr(self._backbone, "cls_token") and self._backbone.cls_token is not None:
            cls_tokens = self._backbone.cls_token.expand(B, -1, -1)
            out = torch.cat((cls_tokens, out), dim=1)

        # Add positional embeddings (best-effort; trim if size mismatch)
        if hasattr(self._backbone, "pos_embed") and self._backbone.pos_embed is not None:
            pe = self._backbone.pos_embed
            out = out + pe[:, : out.shape[1], :]

        for block in self._backbone.blocks:
            out = block(out)

        if hasattr(self._backbone, "norm"):
            out = self._backbone.norm(out)

        # Return without CLS token → (B, N, D)
        if hasattr(self._backbone, "cls_token") and self._backbone.cls_token is not None:
            out = out[:, 1:]

        return out  # (B, N, embed_dim)

    def get_intermediate_layers(self, x: torch.Tensor, n_last: int = 4):
        """
        Return token sequences from the last n_last transformer blocks.

        Returns:
            List of (B, N, embed_dim) tensors — length == min(n_last, depth)
        """
        # patch_embed returns (B, D, T, Hp, Wp)
        out = self._backbone.patch_embed(x)
        B, D, T, Hp, Wp = out.shape

        # Flatten to (B, T*Hp*Wp, D)
        out = out.flatten(2).transpose(1, 2)

        # Prepend CLS token
        if hasattr(self._backbone, "cls_token") and self._backbone.cls_token is not None:
            cls_tokens = self._backbone.cls_token.expand(B, -1, -1)
            out = torch.cat((cls_tokens, out), dim=1)

        # Add positional embeddings
        if hasattr(self._backbone, "pos_embed") and self._backbone.pos_embed is not None:
            pe = self._backbone.pos_embed
            out = out + pe[:, : out.shape[1], :]

        n_blocks = len(self._backbone.blocks)
        # Clamp n_last so we never request more layers than exist
        n_last = min(n_last, n_blocks)

        outputs = []
        for i, block in enumerate(self._backbone.blocks):
            out = block(out)
            if i >= (n_blocks - n_last):
                # Keep 3-D tokens (B, N or N+1, D); strip CLS for decoder
                feat = out[:, 1:] if (
                    hasattr(self._backbone, "cls_token")
                    and self._backbone.cls_token is not None
                ) else out
                outputs.append(feat)  # (B, N, embed_dim)

        return outputs

_EO2_HF_IDS = {
    "600M":    _EO2_600M_ID,
    "600M-TL": "ibm-nasa-geospatial/Prithvi-EO-2.0-600M-TL",
    "300M":    _EO2_300M_ID,
    "300M-TL": "ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL",
}

def build_prithvi_eo2(variant="600M", num_frames=3, in_chans=6, img_size=224):
    if variant not in _EO2_ARCH:
        raise ValueError(f"Unknown variant '{variant}'. Choose from: {list(_EO2_ARCH.keys())}")
    hf_id = _EO2_HF_IDS[variant]
    return PrithviEO2Backbone(pretrained=hf_id, num_frames=num_frames, in_chans=in_chans,
                              img_size=img_size, **_EO2_ARCH[variant])

def _patch_detach_prefix(model, n):
    pass
