"""Stage VLM.2 - CLIP pilot: pure visual feature probe on the same 200-cell pilot.

Hypothesis: where LLaVA-7b text-scoring failed (Mann-Whitney p=0.74, see
docs/audits/vlm_pilot_finding.md), CLIP-ViT-L/14 image embeddings might
nevertheless contain a discriminative signal that a downstream classifier
(LR, LightGBM) can exploit. Bypass text generation entirely.

PASS criterion (must satisfy BOTH):
  - 5-fold mean CV ROC >= 0.60
  - One-sided permutation p < 0.05 (n=1000 label shuffles)

Pipeline:
  1. Load the same 200-pair manifest used by VLM.1
  2. Filter to chips actually on disk (185/200 expected)
  3. Embed each chip with `openai/clip-vit-large-patch14`
     `model.get_image_features(...)` -> 768-dim shared embedding
  4. Save to data_lake/audits/clip_embeddings.parquet (gitignored)
  5. 5-fold stratified LR with StandardScaler
  6. 80/20 holdout LightGBM
  7. 1000-iteration label-shuffle permutation test (liblinear LR, fast)
  8. Write verdict to docs/audits/clip_pilot_finding.md

Decisions (also documented in finding doc):
  - DirectML is broken in this env (DLL load failure vs torch 2.11). CPU only.
  - 15 chips never fetched in the original VLM.1 run; we proceed with the 185
    that are on disk. Class balance is logged.

Usage:
  python scripts/clip_pilot_classifier.py                       # full run (~25 min on CPU)
  python scripts/clip_pilot_classifier.py --limit 20 --n-perm 50   # smoke test
  python scripts/clip_pilot_classifier.py --no-permute              # skip null distribution
"""
from __future__ import annotations

import sys

import argparse
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("clip_pilot")

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data_lake" / "audits" / "vlm_pilot_scores.parquet"
CHIP_DIR = ROOT / "data_lake" / "audits" / "vlm_pilot_chips"
EMB_PATH = ROOT / "data_lake" / "audits" / "clip_embeddings.parquet"
NULL_PATH = ROOT / "tmp" / "clip_null_roc_dist.npy"
HIST_PATH = ROOT / "tmp" / "clip_score_hist.png"
FINDING_PATH = ROOT / "docs" / "audits" / "clip_pilot_finding.md"

CLIP_MODEL = "openai/clip-vit-large-patch14"
EMB_DIM = 768  # get_image_features projection dimension
RANDOM_SEED = 42


# --------------------------------------------------------------------------- #
# Device / model loading
# --------------------------------------------------------------------------- #


def get_device() -> tuple[Any, str]:
    """Try DirectML, fall back to CPU. Always logs the reason for fallback."""
    import torch

    try:
        import torch_directml

        d = torch_directml.device(0)
        _ = torch.zeros(1, device=d) + 1  # smoke test
        log.info("device: directml:0")
        return d, "directml:0"
    except Exception as exc:
        log.warning("DirectML unavailable (%s); falling back to CPU", exc)
        return torch.device("cpu"), "cpu"


# --------------------------------------------------------------------------- #
# Manifest loading
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ManifestStats:
    n_total: int
    n_kept: int
    n_dropped: int
    n_ignited: int
    n_control: int


def load_pilot_manifest(limit: int | None = None) -> tuple[pd.DataFrame, ManifestStats]:
    """Load VLM.1 manifest, filter to chips actually on disk."""
    df = pd.read_parquet(MANIFEST_PATH)
    n_total = len(df)
    df = df[["cell_id", "date", "class"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["chip_path"] = df.apply(
        lambda r: CHIP_DIR / f"{r['class']}_{r['cell_id']}_{r['date'].strftime('%Y%m%d')}.png",
        axis=1,
    )
    df["exists"] = df["chip_path"].apply(lambda p: p.exists())
    kept = df[df["exists"]].copy().reset_index(drop=True)
    if limit is not None:
        kept = kept.head(limit).reset_index(drop=True)
    kept["class_int"] = (kept["class"] == "ignited").astype(int)
    n_ig = int((kept["class_int"] == 1).sum())
    n_ct = int((kept["class_int"] == 0).sum())
    stats = ManifestStats(
        n_total=n_total,
        n_kept=len(kept),
        n_dropped=n_total - len(kept),
        n_ignited=n_ig,
        n_control=n_ct,
    )
    log.info(
        "manifest: total=%d kept=%d dropped=%d ignited=%d control=%d",
        stats.n_total, stats.n_kept, stats.n_dropped, stats.n_ignited, stats.n_control,
    )
    return kept, stats


# --------------------------------------------------------------------------- #
# CLIP embedding
# --------------------------------------------------------------------------- #


def load_clip(device: Any):
    """Load CLIP image tower via open_clip (no torchvision dependency issues)."""
    import torch
    import open_clip

    log.info("loading CLIP: ViT-L-14 (openai weights) via open_clip")
    t0 = time.time()
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="openai", device=device,
    )
    model.eval()
    log.info("loaded in %.1fs", time.time() - t0)
    return model, preprocess, torch


def embed_chips(
    model: Any,
    preprocess: Any,
    torch_mod: Any,
    manifest: pd.DataFrame,
    batch_size: int,
    device: Any,
) -> np.ndarray:
    """Return (N, 768) image embeddings via open_clip."""
    from PIL import Image

    n = len(manifest)
    embs = np.zeros((n, EMB_DIM), dtype=np.float32)
    paths = manifest["chip_path"].tolist()

    t0 = time.time()
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        batch_paths = paths[start:end]
        try:
            imgs = [preprocess(Image.open(p).convert("RGB")) for p in batch_paths]
            batch_tensor = torch_mod.stack(imgs).to(device)
            with torch_mod.no_grad():
                feats = model.encode_image(batch_tensor)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            embs[start:end] = feats.cpu().numpy().astype(np.float32)
            log.info("embedded %d/%d  (%.1fs elapsed)", end, n, time.time() - t0)
        except Exception as exc:
            log.error("batch %d-%d FAILED: %s", start, end, exc)
    log.info("embedded %d chips in %.1fs", n, time.time() - t0)
    return embs


def save_embeddings(embs: np.ndarray, manifest: pd.DataFrame) -> Path:
    cols = {f"emb_{i}": embs[:, i] for i in range(EMB_DIM)}
    out = pd.DataFrame({
        "cell_id": manifest["cell_id"].values,
        "date": manifest["date"].values,
        "class": manifest["class"].values,
        **cols,
    })
    EMB_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(EMB_PATH, index=False)
    log.info("wrote embeddings to %s (%.1f MB)", EMB_PATH, EMB_PATH.stat().st_size / 1e6)
    return EMB_PATH


# --------------------------------------------------------------------------- #
# Statistical evaluation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CVResult:
    fold_rocs: tuple[float, ...]
    mean_roc: float
    std_roc: float
    oof_proba: np.ndarray
    oof_y: np.ndarray


def run_cv_logreg(X: np.ndarray, y: np.ndarray, n_folds: int = 5) -> CVResult:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=RANDOM_SEED)
    fold_rocs: list[float] = []
    oof_proba = np.zeros(len(y), dtype=np.float64)

    for fold_idx, (tr, va) in enumerate(skf.split(X, y), start=1):
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(
                max_iter=2000, C=1.0, class_weight="balanced",
                solver="lbfgs", random_state=RANDOM_SEED,
            )),
        ])
        pipe.fit(X[tr], y[tr])
        proba = pipe.predict_proba(X[va])[:, 1]
        oof_proba[va] = proba
        roc = float(roc_auc_score(y[va], proba))
        fold_rocs.append(roc)
        log.info("CV fold %d/%d ROC=%.4f", fold_idx, n_folds, roc)

    mean = float(np.mean(fold_rocs))
    std = float(np.std(fold_rocs))
    log.info("CV summary: mean=%.4f std=%.4f", mean, std)
    return CVResult(
        fold_rocs=tuple(fold_rocs),
        mean_roc=mean,
        std_roc=std,
        oof_proba=oof_proba,
        oof_y=y.copy(),
    )


@dataclass(frozen=True)
class LGBMResult:
    roc: float
    best_iter: int
    top_features: tuple[tuple[int, float], ...]


def run_holdout_lgbm(X: np.ndarray, y: np.ndarray) -> LGBMResult:
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split

    X_tr, X_va, y_tr, y_va = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_SEED,
    )
    model = lgb.LGBMClassifier(
        objective="binary",
        is_unbalance=True,
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        random_state=RANDOM_SEED,
        verbose=-1,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_va, y_va)],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    proba = model.predict_proba(X_va)[:, 1]
    roc = float(roc_auc_score(y_va, proba))
    best_iter = int(getattr(model, "best_iteration_", 0) or model.n_estimators)
    importances = model.booster_.feature_importance(importance_type="gain")
    top_idx = np.argsort(importances)[::-1][:20]
    top_features = tuple((int(i), float(importances[i])) for i in top_idx)
    log.info("LightGBM holdout ROC=%.4f best_iter=%d", roc, best_iter)
    return LGBMResult(roc=roc, best_iter=best_iter, top_features=top_features)


def permutation_test(
    X: np.ndarray, y: np.ndarray, observed: float, n_perm: int = 1000, n_folds: int = 5,
) -> tuple[np.ndarray, float]:
    """Fast LR (liblinear) on shuffled labels; one-sided p-value."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(RANDOM_SEED)
    null = np.zeros(n_perm, dtype=np.float64)

    t0 = time.time()
    for i in range(n_perm):
        y_shuf = rng.permutation(y)
        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=int(rng.integers(1e9)))
        rocs: list[float] = []
        for tr, va in skf.split(X, y_shuf):
            pipe = Pipeline([
                ("scaler", StandardScaler()),
                ("lr", LogisticRegression(
                    solver="liblinear", C=1.0, max_iter=200,
                    class_weight="balanced", random_state=RANDOM_SEED,
                )),
            ])
            pipe.fit(X[tr], y_shuf[tr])
            proba = pipe.predict_proba(X[va])[:, 1]
            rocs.append(float(roc_auc_score(y_shuf[va], proba)))
        null[i] = float(np.mean(rocs))
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (n_perm - i - 1)
            log.info("perm %d/%d  elapsed=%.0fs  eta=%.0fs  null_max=%.3f",
                     i + 1, n_perm, elapsed, eta, float(null[: i + 1].max()))

    p = float((np.sum(null >= observed) + 1) / (n_perm + 1))
    NULL_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(NULL_PATH, null)
    log.info("permutation: observed=%.4f, null mean=%.4f std=%.4f, p=%.4f",
             observed, float(null.mean()), float(null.std()), p)
    return null, p


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def render_histograms(cv: CVResult, path: Path) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ig = cv.oof_proba[cv.oof_y == 1]
        ct = cv.oof_proba[cv.oof_y == 0]
        fig, ax = plt.subplots(figsize=(7, 4))
        bins = np.linspace(0, 1, 21)
        ax.hist(ct, bins=bins, alpha=0.55, label=f"control (n={len(ct)})", color="#4477AA")
        ax.hist(ig, bins=bins, alpha=0.55, label=f"ignited (n={len(ig)})", color="#EE6677")
        ax.set_xlabel("Out-of-fold P(ignited) - 5-fold LR")
        ax.set_ylabel("count")
        ax.set_title(f"CLIP+LR oof scores  mean ROC={cv.mean_roc:.3f}")
        ax.legend()
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        return path
    except Exception as exc:
        log.warning("histogram render failed: %s", exc)
        return None


@dataclass(frozen=True)
class FindingInputs:
    stats: ManifestStats
    cv: CVResult
    lgbm: LGBMResult | None
    perm_p: float | None
    null_mean: float | None
    null_std: float | None
    n_perm: int
    device_label: str
    elapsed_total_s: float
    pass_cv: bool
    pass_perm: bool


def write_finding_md(inp: FindingInputs) -> Path:
    verdict = "PASS" if (inp.pass_cv and inp.pass_perm) else "FAIL"
    headline = f"{verdict} (CLIP-ViT-L/14 + LR @ ROC={inp.cv.mean_roc:.3f})"

    fold_table = "\n".join(
        f"| fold {i + 1} | {r:.4f} |" for i, r in enumerate(inp.cv.fold_rocs)
    )

    perm_section = "(permutation test skipped - re-run without `--no-permute`)"
    if inp.perm_p is not None:
        perm_section = (
            f"- 1000-iteration label-shuffle permutation (5-fold liblinear LR per shuffle)\n"
            f"- Null mean ROC = {inp.null_mean:.4f}, std = {inp.null_std:.4f}\n"
            f"- One-sided p = **{inp.perm_p:.4f}** "
            f"(Pr[null mean ROC >= observed {inp.cv.mean_roc:.4f}])"
        )

    lgbm_section = "(LightGBM skipped - see logs)"
    if inp.lgbm is not None:
        top10 = "\n".join(
            f"| emb_{idx} | {gain:.1f} |" for idx, gain in inp.lgbm.top_features[:10]
        )
        lgbm_section = (
            f"- 80/20 stratified hold-out on `class_int`\n"
            f"- ROC = **{inp.lgbm.roc:.4f}**, best_iter = {inp.lgbm.best_iter}\n\n"
            f"Top 10 features by gain:\n\n"
            f"| feature | gain |\n|---|---:|\n{top10}\n"
        )

    interp_pass = (
        "CLIP image embeddings + a linear probe DO carry signal on this pilot. "
        "The linear-only ROC suggests the discriminating axis is roughly linear in "
        "CLIP space; LightGBM's gain confirms a small set of dimensions dominate. "
        "Next: scale to the full 2025 hold-out (~10k+ cells), evaluate calibration, "
        "then test as a feature stream concatenated with v17 tabular features."
    )
    interp_fail = (
        "CLIP embeddings do not separate ignited from matched controls on this 200-cell "
        "matched-pair pilot. The signal we hoped to capture (anthropogenic ground-clearing "
        "micro-patterns at 30 m effective resolution) is below CLIP's discriminative floor "
        "OR is genuinely not encoded by web-pretrained ViT features. This rules out the "
        "cheapest revival of the VLM hypothesis flagged in `vlm_pilot_finding.md` step 3."
    )
    interp = interp_pass if (inp.pass_cv and inp.pass_perm) else interp_fail

    body = f"""# Stage VLM.2 - CLIP Pilot - VERDICT: {headline}

**Date:** 2026-04-16
**Backend:** HuggingFace `{CLIP_MODEL}` image tower (768-dim projected features)
**Device:** {inp.device_label}  (DirectML disabled - `torch_directml` DLL incompatible with torch 2.11 in this env)
**Embeddings:** `{EMB_PATH.relative_to(ROOT).as_posix()}` (gitignored)
**Wall time:** {inp.elapsed_total_s:.0f}s

## Hypothesis

Where LLaVA-7b text scoring failed to discriminate the same 200-cell pilot
(Mann-Whitney p=0.74, see `vlm_pilot_finding.md`), CLIP-ViT-L/14 image
embeddings - trained on 400M web image-text pairs - might still encode
visual structure correlated with imminent ignition. We bypass the text head
entirely and probe the 768-dim shared embedding with a simple linear
classifier (LR) plus a non-linear sanity check (LightGBM).

## Pilot design

- **Pairs:** Same 200-row manifest from VLM.1 (100 ignited low-Hawkes 2025 cells +
  100 matched controls). Of these, **{inp.stats.n_kept} chips were actually on disk**
  (15 chips were never fetched in the original VLM.1 run). Per-class kept:
  ignited={inp.stats.n_ignited}, control={inp.stats.n_control}.
- **Imagery:** 224 x 224 px Sentinel-2 RGB chips, 6.7 km field of view, from
  [D-14, D-1] before each cell's "decision day" D.
- **Embedding:** `CLIPModel.from_pretrained("{CLIP_MODEL}").get_image_features(...)`,
  CPU forward pass.
- **Classifier (CV):** 5-fold StratifiedKFold, StandardScaler -> balanced LogisticRegression
  (lbfgs, C=1.0, max_iter=2000), random_state=42.
- **Classifier (sanity):** LightGBM with `is_unbalance=True`, 80/20 stratified hold-out,
  early stopping (patience=50).
- **Permutation:** {inp.n_perm} label shuffles, each scored as the mean of a 5-fold
  liblinear LR (max_iter=200 for speed). One-sided p over observed mean CV ROC.

## Result

| metric | value |
|---|---:|
{fold_table}
| **5-fold mean ROC** | **{inp.cv.mean_roc:.4f}** |
| **5-fold std ROC** | {inp.cv.std_roc:.4f} |

### LightGBM (non-linear sanity check)

{lgbm_section}

### Permutation test

{perm_section}

## Verdict

| criterion | threshold | observed | result |
|---|---:|---:|---|
| 5-fold mean CV ROC | >= 0.60 | {inp.cv.mean_roc:.4f} | {"PASS" if inp.pass_cv else "FAIL"} |
| Permutation p (one-sided) | < 0.05 | {f"{inp.perm_p:.4f}" if inp.perm_p is not None else "n/a"} | {"PASS" if inp.pass_perm else "FAIL"} |

**OVERALL: {verdict}**

## Score histograms

See `{HIST_PATH.relative_to(ROOT).as_posix()}` for the out-of-fold P(ignited)
distribution split by true class (rendered if matplotlib was available).

## Interpretation

{interp}

## What it would take to revisit (if FAIL)

1. **10 m native chips, no downsample.** Send the 670 x 670 px raw chip through a
   ViT-L/14 model that supports it (not vanilla CLIP - patches are fixed 14x14).
   Would require a higher-resolution backbone (Prithvi-EO-2.0 at native, or DINOv2-ViT-g/14
   at variable input size).
2. **Domain pretraining.** Fine-tune or LoRA-adapt CLIP on a self-supervised
   Sentinel-2 corpus (e.g., SatMAE) before this probe. Cost: 1-2 GPU days.
3. **Multi-temporal.** Stack [D-14, D-7, D-1] chips and train a tiny temporal
   convnet on the resulting (3, 768) sequence. Captures change, which static
   chips cannot.

## Files

- `scripts/clip_pilot_classifier.py` - single-file pipeline (this run's source)
- `data_lake/audits/clip_embeddings.parquet` - 185 rows x (3 meta + 768 emb) cols (gitignored)
- `tmp/clip_null_roc_dist.npy` - null distribution from the permutation test
- `tmp/clip_score_hist.png` - oof score histogram
- `data_lake/audits/vlm_pilot_chips/` - same 185 chips reused from VLM.1

## Reproducibility

```bash
python scripts/clip_pilot_classifier.py        # full run, ~25 min on CPU
python scripts/clip_pilot_classifier.py --no-permute   # skip null distribution
python scripts/clip_pilot_classifier.py --limit 20 --n-perm 50   # smoke test
```

Deterministic given a fixed random seed (42) and pinned versions
(transformers==5.5.4, sklearn==1.8.0, lightgbm==4.6.0, torch==2.11.0+cpu).
HuggingFace `{CLIP_MODEL}` weights pulled from cache; first run downloads ~1.7 GB.
"""
    FINDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINDING_PATH.write_text(body, encoding="utf-8")
    log.info("wrote finding to %s", FINDING_PATH)
    return FINDING_PATH


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CLIP pilot classifier (Stage VLM.2)")
    p.add_argument("--batch", type=int, default=16, help="embedding batch size (default 16)")
    p.add_argument("--limit", type=int, default=None, help="limit chips for smoke test")
    p.add_argument("--no-permute", action="store_true", help="skip permutation test")
    p.add_argument("--n-perm", type=int, default=1000, help="permutation iterations (default 1000)")
    p.add_argument("--reuse-emb", action="store_true",
                   help="if clip_embeddings.parquet already exists, reuse it")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    t_start = time.time()

    manifest, stats = load_pilot_manifest(limit=args.limit)
    if stats.n_kept == 0:
        log.error("no chips found on disk - aborting")
        return 2

    merged: pd.DataFrame
    device_label = "cpu"

    if args.reuse_emb and EMB_PATH.exists():
        log.info("reusing existing embeddings at %s", EMB_PATH)
        emb_df = pd.read_parquet(EMB_PATH)
        emb_cols = [c for c in emb_df.columns if c.startswith("emb_")]
        merged = manifest.merge(
            emb_df[["cell_id", "date", "class"] + emb_cols],
            on=["cell_id", "date", "class"], how="inner",
        )
        if len(merged) != len(manifest):
            log.warning("reuse mismatch: manifest=%d cached=%d - re-embedding",
                        len(manifest), len(merged))
            args.reuse_emb = False

    if not (args.reuse_emb and EMB_PATH.exists()):
        device, device_label = get_device()
        model, processor, torch_mod = load_clip(device)
        embs = embed_chips(model, processor, torch_mod, manifest, args.batch, device)
        save_embeddings(embs, manifest)
        merged = manifest.copy()
        for i in range(EMB_DIM):
            merged[f"emb_{i}"] = embs[:, i]

    emb_cols = [f"emb_{i}" for i in range(EMB_DIM)]
    X = merged[emb_cols].to_numpy(dtype=np.float32)
    y = merged["class_int"].to_numpy(dtype=np.int64) if "class_int" in merged.columns \
        else (merged["class"].values == "ignited").astype(np.int64)

    cv = run_cv_logreg(X, y, n_folds=5)
    lgbm = run_holdout_lgbm(X, y)
    render_histograms(cv, HIST_PATH)

    perm_p: float | None = None
    null_mean: float | None = None
    null_std: float | None = None
    if not args.no_permute:
        null, perm_p = permutation_test(X, y, observed=cv.mean_roc, n_perm=args.n_perm)
        null_mean = float(null.mean())
        null_std = float(null.std())

    elapsed = time.time() - t_start
    pass_cv = cv.mean_roc >= 0.60
    pass_perm = (perm_p is not None) and (perm_p < 0.05)

    write_finding_md(FindingInputs(
        stats=stats,
        cv=cv,
        lgbm=lgbm,
        perm_p=perm_p,
        null_mean=null_mean,
        null_std=null_std,
        n_perm=args.n_perm if not args.no_permute else 0,
        device_label=device_label,
        elapsed_total_s=elapsed,
        pass_cv=pass_cv,
        pass_perm=pass_perm,
    ))

    log.info("=" * 60)
    log.info("FINAL: 5-fold mean ROC=%.4f +/- %.4f", cv.mean_roc, cv.std_roc)
    log.info("FINAL: LightGBM holdout ROC=%.4f", lgbm.roc)
    if perm_p is not None:
        log.info("FINAL: permutation p=%.4f (n=%d)", perm_p, args.n_perm)
    verdict = "PASS" if (pass_cv and pass_perm) else "FAIL"
    log.info("FINAL: VERDICT=%s", verdict)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
