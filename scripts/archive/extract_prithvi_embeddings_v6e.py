"""Plan B.2 — Extract Prithvi-EO-2.0 1280-dim CLS embeddings for all v6e cell chips.

Reads chips from `data_lake/v6e_chips/chips/{cell_id}.npz` (saved by build_v6e_cell_chips.py).
For each chip, runs Prithvi-EO-2.0 backbone (frozen, inference mode) and extracts:
  - CLS token: (embed_dim,) — global representation
  - Spatial mean: (embed_dim,) — mean-pooled spatial tokens

Saves combined embeddings to a single parquet for downstream merge with v6e dataset.

Usage:
    python scripts/extract_prithvi_embeddings_v6e.py
    python scripts/extract_prithvi_embeddings_v6e.py --variant 600M-TL --batch 4
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

# ── PROJ/GDAL env fix ──
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.utils.proj_fix import setup_proj_env  # noqa: E402

setup_proj_env()

from src.model.prithvi_eo2_backbone import build_prithvi_eo2  # noqa: E402

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
CHIPS_DIR = ROOT / "data_lake" / "v6e_chips" / "chips"
OUT_PATH = ROOT / "data_lake" / "v6e_chips" / "embeddings_prithvi_1280.parquet"


def get_device():
    try:
        import torch_directml  # noqa: F401
        return torch_directml.device()
    except ImportError:
        pass
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="300M", choices=["300M", "300M-TL", "600M", "600M-TL"])
    ap.add_argument("--batch", type=int, default=2, help="Batch size (DirectML may need 4 or less)")
    ap.add_argument("--num-frames", type=int, default=1, help="Time steps (chip is single composite)")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of chips for testing")
    args = ap.parse_args()

    device = get_device()
    log.info("Device: %s", device)

    log.info("Loading Prithvi-EO-2.0-%s ...", args.variant)
    backbone = build_prithvi_eo2(variant=args.variant, num_frames=args.num_frames,
                                 in_chans=6, img_size=224)
    backbone.to(device)
    backbone.train(False)
    embed_dim = backbone.embed_dim
    log.info("Backbone loaded, embed_dim=%d", embed_dim)

    chips = sorted(CHIPS_DIR.glob("*.npz"))
    if args.limit > 0:
        chips = chips[: args.limit]
    log.info("Chips to process: %d", len(chips))

    if len(chips) == 0:
        log.error("No chips found at %s", CHIPS_DIR)
        log.error("Run build_v6e_cell_chips.py first")
        return 1

    cell_ids: list = []
    cls_embeds: list = []
    spatial_embeds: list = []

    bb = backbone._backbone
    t0 = time.time()
    n_done = 0

    def process_batch(batch_chips):
        x = np.stack([c["hls"] for c in batch_chips], axis=0)
        x_t = torch.from_numpy(x).float().to(device)

        with torch.no_grad():
            out = bb.patch_embed(x_t)
            if isinstance(out, tuple):
                out = out[0]
            B, D, T, Hp, Wp = out.shape
            tokens = out.flatten(2).transpose(1, 2)

            if hasattr(bb, "cls_token") and bb.cls_token is not None:
                cls = bb.cls_token.expand(B, -1, -1)
                tokens = torch.cat((cls, tokens), dim=1)

            if hasattr(bb, "pos_embed") and bb.pos_embed is not None:
                pe = bb.pos_embed
                tokens = tokens + pe[:, : tokens.shape[1], :]

            for block in bb.blocks:
                tokens = block(tokens)

            if hasattr(bb, "norm") and bb.norm is not None:
                tokens = bb.norm(tokens)

            cls_feat = tokens[:, 0, :].cpu().numpy()
            spatial_feat = tokens[:, 1:, :].mean(dim=1).cpu().numpy()

        return cls_feat, spatial_feat

    for i in range(0, len(chips), args.batch):
        batch_files = chips[i : i + args.batch]
        batch_data: list = []
        batch_ids: list = []
        for f in batch_files:
            try:
                d = np.load(f)
                hls = d["hls"]
                if hls.shape[1] != args.num_frames:
                    if hls.shape[1] < args.num_frames:
                        last = hls[:, -1:, :, :]
                        pad = np.repeat(last, args.num_frames - hls.shape[1], axis=1)
                        hls = np.concatenate([hls, pad], axis=1)
                    else:
                        hls = hls[:, : args.num_frames, :, :]
                batch_data.append({"hls": hls})
                batch_ids.append(f.stem)
            except Exception as e:
                log.warning("Failed to load %s: %s", f.name, e)

        if not batch_data:
            continue

        try:
            cls_b, sp_b = process_batch(batch_data)
            cell_ids.extend(batch_ids)
            cls_embeds.append(cls_b)
            spatial_embeds.append(sp_b)
            n_done += len(batch_data)
        except Exception as e:
            log.error("Batch %d failed: %s", i, e)
            continue

        if (i // args.batch) % 10 == 0 and i > 0:
            elapsed = time.time() - t0
            rate = n_done / elapsed
            eta = (len(chips) - n_done) / max(rate, 0.01)
            log.info("  %d/%d chips (%.0fs, %.1f chips/s, ETA %.0fs)",
                     n_done, len(chips), elapsed, rate, eta)

    log.info("All batches done in %.0fs", time.time() - t0)

    cls_arr = np.concatenate(cls_embeds, axis=0)
    sp_arr = np.concatenate(spatial_embeds, axis=0)
    log.info("Final shapes: cls=%s spatial=%s", cls_arr.shape, sp_arr.shape)

    df = pd.DataFrame({"cell_id": cell_ids})
    for i in range(embed_dim):
        df[f"pcls_{i:04d}"] = cls_arr[:, i]
    for i in range(embed_dim):
        df[f"psp_{i:04d}"] = sp_arr[:, i]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    log.info("Saved: %s (%.0f MB)", OUT_PATH.relative_to(ROOT), OUT_PATH.stat().st_size / 1e6)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
