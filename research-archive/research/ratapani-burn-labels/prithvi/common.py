"""Shared bits for the Prithvi-EO-2.0 burn-scar fine-tune (runs on Akkshay's PC, AMD GPU via DirectML)."""
import os, sys, glob, datetime as dt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import fetch, detect  # noqa: E402  (fetch builds the 20 m AOI grid on import; set RATAPANI_AOI off-container)

BANDS = ("blue", "green", "red", "nir", "swir1", "swir2")  # HLS order Prithvi was trained on
# Prithvi-EO-2.0 HLS normalisation (reflectance x 10000)
MEAN = np.array([1087.0, 1342.0, 1433.0, 2734.0, 1958.0, 1363.0], np.float32)
STD = np.array([2248.0, 2179.0, 2178.0, 1850.0, 1242.0, 1049.0], np.float32)
CHIP = 224
ROWS, COLS = np.where(fetch.INSIDE)


def season_files(obsdir):
    """One observation per date, as detect.load picks it (the file with more clear pixels)."""
    keep = {}
    for f in sorted(glob.glob(os.path.join(obsdir, "*.npz"))):
        d = dt.date.fromisoformat(os.path.basename(f)[:10])
        v = np.load(f)["valid"].mean()
        if d not in keep or v > keep[d][1]:
            keep[d] = (f, v)
    return {d: keep[d][0] for d in sorted(keep)}


def load_image(f):
    """6 x H x W int16 reflectance on the full grid (0 outside the AOI) and the H x W clear mask.
    Sentinel-2 NIR/SWIR is scaled onto Landsat, as in detect.py. Blue/green come from the same file
    ("six" fetch) or from bg/<date>_<sensor>_bg.npz ("bg" fetch)."""
    z = dict(np.load(f))
    if "blue" not in z:
        b = os.path.join(os.path.dirname(f), "bg", os.path.basename(f)[:-4] + "_bg.npz")
        z.update(np.load(b))
    s2 = f.endswith("_s2.npz")
    img = np.zeros((6,) + fetch.INSIDE.shape, np.int16)
    for i, k in enumerate(BANDS):
        v = z[k].astype(np.float32)
        if s2 and k in detect.S2_TO_LS:
            v *= detect.S2_TO_LS[k]
        img[i][fetch.INSIDE] = np.clip(v, -32000, 32000).astype(np.int16)
    valid = np.zeros(fetch.INSIDE.shape, bool)
    valid[fetch.INSIDE] = z["valid"]
    return img, valid


def normalise(x):
    """x: (..., 6, T, H, W) int16 -> float32 standardised."""
    return (x.astype(np.float32) - MEAN[:, None, None, None]) / STD[:, None, None, None]


def build_model(pretrained=True, size="100_tl"):
    import torch
    from terratorch.models import EncoderDecoderFactory
    depth = {"100_tl": 12, "300_tl": 24, "tiny_tl": 12}[size]
    idx = [depth // 4 - 1, depth // 2 - 1, 3 * depth // 4 - 1, depth - 1]
    m = EncoderDecoderFactory().build_model(
        task="segmentation", backbone=f"prithvi_eo_v2_{size}", backbone_pretrained=pretrained,
        backbone_bands=["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"], backbone_num_frames=2,
        necks=[{"name": "SelectIndices", "indices": idx}, {"name": "ReshapeTokensToImage", "effective_time_dim": 2},
               {"name": "LearnedInterpolateToPyramidal"}],
        decoder="UNetDecoder", decoder_channels=[512, 256, 128, 64], num_classes=2)

    class Conv3dAs2d(torch.nn.Module):
        """DirectML has no conv3d. Prithvi's patch embedding is a Conv3d with tubelet size 1,
        which equals a Conv2d applied to each frame."""
        def __init__(self, c3):
            super().__init__()
            assert c3.kernel_size[0] == 1 and c3.stride[0] == 1
            self.c2 = torch.nn.Conv2d(c3.in_channels, c3.out_channels, c3.kernel_size[1:], c3.stride[1:],
                                      bias=c3.bias is not None)
            self.c2.weight.data = c3.weight.data[:, :, 0].clone()
            if c3.bias is not None:
                self.c2.bias.data = c3.bias.data.clone()

        def forward(self, x):  # B C T H W
            B, C, T, H, W = x.shape
            y = self.c2(x.permute(0, 2, 1, 3, 4).reshape(B * T, C, H, W))
            return y.reshape(B, T, *y.shape[1:]).permute(0, 2, 1, 3, 4)

    for mod in list(m.modules()):
        for n, ch in list(mod.named_children()):
            if isinstance(ch, torch.nn.Conv3d):
                setattr(mod, n, Conv3dAs2d(ch))
    return m


def device():
    try:
        import torch_directml
        return torch_directml.device()
    except ImportError:
        import torch
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
