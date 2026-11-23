"""Dynamic Prithvi-EO-2.0-300M-TL embeddings per 500 m cell per 10-day step (AMD GPU via DirectML).
For step d the model sees 3 frames: the HLS composites at d-20, d-10 and d (each the median of clear looks in the 15 days
before), with temporal (year, day of year) and location (lat, lon) coordinates. One ViT token (16 px x 31.25 m) = one cell.
The cell's embedding is its last-layer token averaged over the 3 frames (1024-d). Gaps (-9999) are filled from the previous
frame, then with the band mean (zero after normalising).  Output: emb/{season}_{MMDD}.npy (3614 x 1024 float16).
Usage: python embed.py [seasons...]"""
import os, sys, json, glob, time, numpy as np, pandas as pd, torch
from pyproj import Transformer
sys.path.insert(0, r'E:\FIRE\ratapani_burn\prithvi')
HERE = r'E:\FIRE\ratapani\prithvi_dyn'; HLS = HERE + r'\hls'; OUT = HERE + r'\emb'; os.makedirs(OUT, exist_ok=True)
MEAN = np.array([1087.0, 1342.0, 1433.0, 2734.0, 1958.0, 1363.0], np.float32)[:, None, None]
STD = np.array([2248.0, 2179.0, 2178.0, 1850.0, 1242.0, 1049.0], np.float32)[:, None, None]
X0, Y1, S = 739500.0, 2558500.0, 500.0
G = json.load(open(r'E:\FIRE\ratapani\grid_500m.geojson'))['features']
cid = np.array([f['properties']['cell_id'] for f in G])
rr = np.round((Y1 - (np.array([f['properties']['y0'] for f in G]) + S)) / S).astype(int)
cc = np.round((np.array([f['properties']['x0'] for f in G]) - X0) / S).astype(int)
HC, WC = 70, 154   # cells, padded to whole 14-cell tiles
inv = Transformer.from_crs('EPSG:32643', 'EPSG:4326', always_xy=True).transform
def load(f, prev):
    a = np.load(f).astype(np.float32)
    if prev is not None: a = np.where(a == -9999, prev, a)
    return a
def norm(a):
    x = (np.where(a == -9999, MEAN, a) - MEAN) / STD
    out = np.zeros((6, HC * 16, WC * 16), np.float32); out[:, :x.shape[1], :x.shape[2]] = x; return out
def device():
    try:
        import torch_directml; return torch_directml.device()
    except ImportError: return torch.device('cpu')
def build():
    from terratorch.registry import BACKBONE_REGISTRY
    m = BACKBONE_REGISTRY.build('terratorch_prithvi_eo_v2_300_tl', pretrained=True, num_frames=3,
                                bands=['BLUE', 'GREEN', 'RED', 'NIR_NARROW', 'SWIR_1', 'SWIR_2'])
    class Conv3dAs2d(torch.nn.Module):
        def __init__(s, c3):
            super().__init__(); s.c2 = torch.nn.Conv2d(c3.in_channels, c3.out_channels, c3.kernel_size[1:], c3.stride[1:], bias=c3.bias is not None)
            s.c2.weight.data = c3.weight.data[:, :, 0].clone()
            if c3.bias is not None: s.c2.bias.data = c3.bias.data.clone()
        def forward(s, x):
            B, C, T, H, W = x.shape; y = s.c2(x.permute(0, 2, 1, 3, 4).reshape(B * T, C, H, W)); return y.reshape(B, T, *y.shape[1:]).permute(0, 2, 1, 3, 4)
    for mod in list(m.modules()):
        for n, ch in list(mod.named_children()):
            if isinstance(ch, torch.nn.Conv3d): setattr(mod, n, Conv3dAs2d(ch))
    return m.eval()
dev = device(); net = build().to(dev); print('model on', dev, flush=True)
seasons = [int(v) for v in sys.argv[1:]] or list(range(2017, 2027))
for Y in seasons:
    files = sorted(glob.glob(HLS + rf'\{Y}_*.npy')); frames = []; prev = None
    for f in files: prev = load(f, prev); frames.append((f, prev))
    for k in range(2, len(frames)):
        f = frames[k][0]; out = os.path.join(OUT, os.path.basename(f))
        if os.path.exists(out): continue
        t0 = time.time(); x = np.stack([norm(frames[j][1]) for j in (k - 2, k - 1, k)], 1)   # 6 x 3 x H x W
        dates = [pd.Timestamp(os.path.basename(frames[j][0])[:4] + '-' + os.path.basename(frames[j][0])[5:7] + '-' + os.path.basename(frames[j][0])[7:9]) for j in (k - 2, k - 1, k)]
        tc = torch.tensor([[[d.year, d.dayofyear] for d in dates]], dtype=torch.float32)
        E = np.zeros((HC, WC, 1024), np.float32)
        with torch.no_grad():
            for ti in range(HC // 14):
                for tj in range(WC // 14):
                    chip = torch.from_numpy(x[None, :, :, ti * 224:(ti + 1) * 224, tj * 224:(tj + 1) * 224].copy())
                    lon, lat = inv(X0 + (tj * 14 + 7) * S, Y1 - (ti * 14 + 7) * S)
                    lc = torch.tensor([[lat, lon]], dtype=torch.float32)
                    feats = net(chip.to(dev), temporal_coords=tc.to(dev), location_coords=lc.to(dev))
                    tok = feats[-1][0, 1:].float().cpu().numpy().reshape(3, 14, 14, -1).mean(0)   # drop cls, average frames
                    E[ti * 14:(ti + 1) * 14, tj * 14:(tj + 1) * 14] = tok
        Ec = np.zeros((3614, 1024), np.float16); Ec[cid] = E[rr, cc]; np.save(out, Ec); print(Y, os.path.basename(f), f'{time.time() - t0:.0f}s', flush=True)
print('EMBED_DONE')
