"""Prithvi-EO-2.0-300M encoder for 3 frames x 6 HLS bands at 224 px, loaded exactly from the local Hugging Face checkpoint (timm blocks, Conv3d tubelet 1
replaced by Conv2d for DirectML, sin-cos position table sliced to 3 frames), plus a light segmentation head. Split forward so the frozen blocks run once
and only the last K blocks + head are trained (equivalent to unfreezing the last K blocks)."""
import glob

import torch
import torch.nn as nn
import torch.nn.functional as F
from timm.models.vision_transformer import Block

CKPT = glob.glob(r"C:/Users/S.C.C/.cache/huggingface/hub/models--ibm-nasa-geospatial--Prithvi-EO-2.0-300M/snapshots/*/Prithvi_EO_V2_300M.pt")[0]
MEAN = [1087.0, 1342.0, 1433.0, 2734.0, 1958.0, 1363.0]
STD = [2248.0, 2179.0, 2178.0, 1850.0, 1242.0, 1049.0]
D, DEPTH, HEADS, P, IMG, TF = 1024, 24, 16, 16, 224, 3
G = IMG // P


class Encoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = nn.Conv2d(6, D, P, P)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, D))
        self.register_buffer("pos_embed", torch.zeros(1, 1 + TF * G * G, D))
        self.blocks = nn.ModuleList([Block(D, HEADS, 4.0, qkv_bias=True, norm_layer=lambda d, **kw: nn.LayerNorm(d, eps=1e-6, **kw)) for _ in range(DEPTH)])
        self.norm = nn.LayerNorm(D, eps=1e-6)
        sd = torch.load(CKPT, map_location="cpu", weights_only=True)
        sd = sd.get("model", sd)
        e = {k[8:]: v for k, v in sd.items() if k.startswith("encoder.")}
        e["proj.weight"] = e.pop("patch_embed.proj.weight")[:, :, 0]
        e["proj.bias"] = e.pop("patch_embed.proj.bias")
        e["pos_embed"] = e["pos_embed"][:, :1 + TF * G * G]          # t-major sin-cos table: first 3 frames
        missing, unexpected = self.load_state_dict(e, strict=False)
        assert not missing and not unexpected, (missing, unexpected)

    def embed(self, x):
        """x: (B, T, 6, 224, 224) normalised -> tokens (B, 1 + T*196, D)."""
        B = x.shape[0]
        t = self.proj(x.flatten(0, 1)).flatten(2).transpose(1, 2)          # (B*T, 196, D)
        t = t.reshape(B, TF * G * G, D)
        return torch.cat([self.cls_token.expand(B, -1, -1), t], 1) + self.pos_embed

    def run(self, t, a, b):
        for blk in self.blocks[a:b]:
            t = blk(t)
        return t


_U = {}


def up_bilinear(x, size):
    """Bilinear upsampling (align_corners=False) as two matrix products. F.interpolate(mode="bilinear") is wrong on DirectML
    (about 90% relative error forward and backward vs CPU, 7 Nov 2026); the interpolation matrices are built once on CPU with F.interpolate."""
    h, w = x.shape[-2:]
    H, W = size
    key = (h, w, H, W, str(x.device))
    if key not in _U:
        uh = F.interpolate(torch.eye(h).view(h, 1, h, 1), size=(H, 1), mode="bilinear", align_corners=False).view(h, H).T
        uw = F.interpolate(torch.eye(w).view(w, 1, 1, w), size=(1, W), mode="bilinear", align_corners=False).view(w, W).T
        _U[key] = (uh.contiguous().to(x.device), uw.contiguous().to(x.device))
    uh, uw = _U[key]
    return torch.matmul(torch.matmul(uh, x), uw.T)


class Head(nn.Module):
    """Tokens of the 3 frames concatenated per location -> 3-class logits at full 224 px."""
    def __init__(self, n_cls=3):
        super().__init__()
        self.c1 = nn.Conv2d(TF * D, 256, 1)
        self.c2 = nn.Conv2d(256, 128, 3, padding=1)
        self.c3 = nn.Conv2d(128, n_cls, 1)

    def forward(self, t):
        B = t.shape[0]
        x = t[:, 1:].reshape(B, TF, G, G, D).permute(0, 1, 4, 2, 3).reshape(B, TF * D, G, G)
        x = F.gelu(self.c1(x))
        x = up_bilinear(x, (4 * G, 4 * G))
        x = F.gelu(self.c2(x))
        x = up_bilinear(x, (IMG, IMG))
        return self.c3(x)


def masked_ce(logits, y, weight=None):
    """Cross-entropy over pixels with y >= 0 (y = -1 ignored): log_softmax, gather the target log-prob with targets clamped to a valid class, multiply by a
    float valid mask (times the class weight), sum / weighted count. Same value and gradient as CPU F.cross_entropy(weight, ignore_index=-1); returns 0 with
    zero gradient when every pixel is ignored. F.cross_entropy(ignore_index) gives wrong gradients on DirectML (51-61% vs CPU, 8 Nov 2026); avoid it and
    boolean-mask selection. Checked against CPU in e113_dml_checks.py."""
    yc = y.clamp(min=0)
    valid = (y >= 0).float()
    nll = -F.log_softmax(logits, 1).gather(1, yc.unsqueeze(1)).squeeze(1)
    w = valid if weight is None else weight.gather(0, yc.flatten()).view_as(valid) * valid
    return (nll * w).sum() / w.sum().clamp(min=1e-6)


def masked_ce_onehot(logits, y, weight=None):
    """Earlier form (one-hot by comparison with arange), kept for the DirectML check."""
    valid = (y >= 0).float()
    oh = (y.clamp(min=0).unsqueeze(1) == torch.arange(logits.shape[1], device=y.device).view(1, -1, 1, 1)).float()     # one_hot fails on DirectML
    nll = -(F.log_softmax(logits, 1) * oh).sum(1)
    w = (oh * weight.view(1, -1, 1, 1)).sum(1) * valid if weight is not None else valid
    return (nll * w).sum() / w.sum().clamp(min=1e-6)


def normalise(a):
    """a: (18, H, W) int16 HLS stack (3 seasons x 6 bands, -9999 missing) -> (3, 6, H, W) float32 normalised, missing = 0."""
    x = torch.as_tensor(a.astype("float32")).reshape(3, 6, *a.shape[1:])
    m = torch.tensor(MEAN).view(1, 6, 1, 1)
    s = torch.tensor(STD).view(1, 6, 1, 1)
    bad = torch.as_tensor(a == -9999).reshape(3, 6, *a.shape[1:])
    x = (x - m) / s
    x[bad] = 0
    return x
