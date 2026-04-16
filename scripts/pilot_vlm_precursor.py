"""Stage VLM.1 — Pilot: can a VLM detect fire-precursor patterns on Sentinel-2?

Hypothesis: Before anthropogenic forest fires in MP, ground-clearing activity
(leaf-litter raking, brush-cutting, circular clearings around mahua trees,
agricultural burn preparation) is visible in recent Sentinel-2 imagery. A
zero-shot VLM should score ignited-cell imagery HIGHER than control-cell
imagery for precursor patterns.

Pilot design:
  - Select 200 (cell, date) pairs from 2025 hold-out audit:
    - 100 ignited cells (DBSCAN ignition on val Thursday D)
    - 100 matched controls (same beat, same Thursday, NO ignition)
  - For each: fetch least-cloudy Sentinel-2 scene from [D-14, D-1]
  - Render 6.7km×6.7km RGB patch centered on cell
  - Send to OpenAI GPT-4o-mini with vision + structured prompt
  - Parse score 0-10

Exit criteria:
  - Mean score (ignited) > Mean score (control) + 2 points
  - Mann-Whitney U p < 0.01
  - Spearman rho(score, ignited) >= 0.10

Output:
  data_lake/audits/vlm_pilot_scores.parquet — 200 rows (cell, date, ignited, score, evidence)
  data_lake/audits/vlm_pilot_chips/ — 200 RGB PNG chips for manual review
  docs/audits/vlm_pilot_finding.md — verdict + evidence

Usage:
  python scripts/pilot_vlm_precursor.py --n-pairs 100 --skip-vlm       # fetch chips only, no API calls
  python scripts/pilot_vlm_precursor.py --n-pairs 100                   # full pilot
  python scripts/pilot_vlm_precursor.py --n-pairs 5                     # smoke test
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

import ee
import numpy as np
import pandas as pd
import requests

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PCD = ROOT / "data_lake" / "audits" / "v17_audit_per_cell_date.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
OUT_DIR = ROOT / "data_lake" / "audits"
CHIP_DIR = OUT_DIR / "vlm_pilot_chips"
OUT_PATH = OUT_DIR / "vlm_pilot_scores.parquet"

# Load .env (NUL-robust)
env_file = ROOT / ".env"
if env_file.exists():
    text = env_file.read_bytes().decode("utf-8", errors="replace").replace("\x00", "")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k and v and k not in os.environ:
                try:
                    os.environ[k] = v
                except Exception:
                    pass

ee.Initialize(project="van-suraksha-alert")

CHIP_SIZE_M = 6700  # 6.7 km patch
CHIP_PIXELS = 224   # 224×224 at 30m/px = 6720m, matches v6e cell context
LOOKBACK_DAYS = 14
S2_CLOUD_MAX = 40

PROMPT = """You are analyzing a Sentinel-2 satellite RGB image of a 6.7 km × 6.7 km area in Madhya Pradesh, India (dry-deciduous forest during the Feb-May fire season).

Your task: score 0-10 the likelihood that this image shows evidence of ANTHROPOGENIC ground-clearing activity consistent with imminent forest fire (leaf-litter raking, brush-cutting, circular clearings around mahua/tendu trees, agricultural burn preparation, geometric bare-soil patches that don't match natural dry-season phenology).

Consider:
- Natural dry-season leaf-drop is EXPECTED and should NOT score high
- Only score high if there are UNNATURAL bare patches, geometric clearings, or signs of human intervention beyond normal phenology
- 0 = no evidence, 10 = strong evidence of active clearing

Respond with ONLY a JSON object:
{"score": <int 0-10>, "confidence": <float 0-1>, "evidence": "<one-sentence reason>"}
"""


def select_pilot_pairs(n_per_class: int = 100, seed: int = 42) -> pd.DataFrame:
    log.info("Loading audit per-cell-date parquet...")
    audit = pd.read_parquet(AUDIT_PCD)
    audit["date"] = pd.to_datetime(audit["date"])

    # Only consider low-Hawkes cells (the 77% miss zone — where we need help)
    low_h = audit[audit["hawkes_n_recent_10km_7d"] <= 1].copy()
    log.info("  Low-Hawkes subset: %d rows", len(low_h))

    ignited = low_h[low_h["label_dbscan_ignition"] == 1].copy()
    control = low_h[low_h["label_dbscan_ignition"] == 0].copy()
    log.info("  Ignited low-Hawkes: %d, Control low-Hawkes: %d", len(ignited), len(control))

    # Sample n_per_class ignited
    rng = np.random.default_rng(seed)
    if len(ignited) < n_per_class:
        log.warning("Only %d ignited low-Hawkes cells available, using all", len(ignited))
        ig_sample = ignited.reset_index(drop=True)
    else:
        ig_sample = ignited.sample(n=n_per_class, random_state=seed).reset_index(drop=True)

    # For each ignited, find a matched control (same division, same date, no ignition)
    matched_controls = []
    for _, r in ig_sample.iterrows():
        candidates = control[
            (control["date"] == r["date"]) & (control["division"] == r["division"])
        ]
        if len(candidates) == 0:
            candidates = control[control["date"] == r["date"]]
        if len(candidates) == 0:
            continue
        matched_controls.append(candidates.sample(n=1, random_state=seed).iloc[0])
    ctrl_sample = pd.DataFrame(matched_controls).reset_index(drop=True)
    log.info("  Matched-control cells selected: %d", len(ctrl_sample))

    ig_sample["class"] = "ignited"
    ctrl_sample["class"] = "control"
    keep_cols = ["cell_id", "date", "class", "centroid_lat", "centroid_lon",
                 "division", "beat", "ignition_risk", "within_day_rank", "band"]

    # Interleave matched pairs so partial completion still gives a balanced sample.
    # Truncate to common length (in case ctrl_sample lost rows in matching).
    n_pairs = min(len(ig_sample), len(ctrl_sample))
    ig_part = ig_sample[keep_cols].iloc[:n_pairs].reset_index(drop=True)
    ct_part = ctrl_sample[keep_cols].iloc[:n_pairs].reset_index(drop=True)
    interleaved = []
    for i in range(n_pairs):
        interleaved.append(ig_part.iloc[i])
        interleaved.append(ct_part.iloc[i])
    pairs = pd.DataFrame(interleaved).reset_index(drop=True)
    log.info("  Interleaved order: %d pairs (%d ignited + %d control alternating)",
             n_pairs, n_pairs, n_pairs)
    return pairs


def fetch_s2_chip(lat: float, lon: float, target_date: pd.Timestamp) -> bytes | None:
    """Fetch cloud-free Sentinel-2 RGB thumbnail for a cell in the 14-day pre-date window."""
    start = (target_date - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    end = (target_date - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    # ~3 km buffer at equator: 0.03° ≈ 3.3 km (we want 6.7 km total)
    half = (CHIP_SIZE_M / 2) / 110000.0
    region = ee.Geometry.Rectangle([lon - half, lat - half, lon + half, lat + half])
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", S2_CLOUD_MAX))
    )
    n = col.size().getInfo()
    if n == 0:
        return None
    # Take least-cloudy image
    img = col.sort("CLOUDY_PIXEL_PERCENTAGE").first()
    # RGB bands, stretch to 0-255
    rgb = img.select(["B4", "B3", "B2"])
    vis = rgb.visualize(min=0, max=3000, bands=["B4", "B3", "B2"])
    url = vis.getThumbURL({"region": region, "dimensions": CHIP_PIXELS, "format": "png"})
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        log.warning("  thumbnail fetch failed %s lat=%.3f lon=%.3f", resp.status_code, lat, lon)
        return None
    return resp.content


def _parse_score_json(content: str) -> dict:
    """Parse structured {score, confidence, evidence} JSON from a VLM response."""
    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(content)
        return {
            "score": int(parsed.get("score", -1)),
            "confidence": float(parsed.get("confidence", 0)),
            "evidence": parsed.get("evidence", ""),
        }
    except Exception as e:
        return {"score": -1, "confidence": 0.0, "evidence": f"parse_error: {e} || raw: {content[:200]}"}


def score_chip_with_ollama(png_bytes: bytes, model: str = "llava:7b",
                            temperature: float = 0.4,
                            host: str = "http://127.0.0.1:11434") -> dict:
    """Score a chip with a local Ollama vision model (no rate limits, no cost)."""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    payload = {
        "model": model,
        "prompt": PROMPT,
        "images": [b64],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 256,
            "seed": 42,
        },
    }
    try:
        r = requests.post(f"{host}/api/generate", json=payload, timeout=120)
    except requests.RequestException as e:
        return {"score": -1, "confidence": 0.0, "evidence": f"ollama_conn_error: {e}"}
    if r.status_code >= 400:
        return {"score": -1, "confidence": 0.0,
                "evidence": f"ollama_http_{r.status_code}: {r.text[:200]}"}
    raw = r.json().get("response", "")
    return _parse_score_json(raw)


def score_chip_with_vlm(png_bytes: bytes, backend: str = "ollama",
                         ollama_model: str = "llava:7b",
                         ollama_temperature: float = 0.4) -> dict:
    """Score a chip via the chosen VLM backend.

    backend: "ollama" (local, free, fast), "gemini" (Google API),
             "openai" (OpenAI API), or "auto" (pick based on env/availability).
    """
    if backend == "ollama":
        return score_chip_with_ollama(png_bytes, model=ollama_model,
                                       temperature=ollama_temperature)

    gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if backend == "auto":
        # Prefer ollama if daemon reachable; else gemini; else openai
        try:
            requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            return score_chip_with_ollama(png_bytes, model=ollama_model,
                                           temperature=ollama_temperature)
        except requests.RequestException:
            pass
        if gemini_key:
            backend = "gemini"
        elif openai_key:
            backend = "openai"
        else:
            return {"score": -1, "confidence": 0.0,
                    "evidence": "auto: no backend available"}

    b64 = base64.b64encode(png_bytes).decode("ascii")

    if backend == "gemini":
        if not gemini_key:
            return {"score": -1, "confidence": 0.0,
                    "evidence": "gemini backend requested but GOOGLE_API_KEY not set"}
        # Google Gemini 2.5 Flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ],
            }],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 1024,  # Gemini 2.5 burns thinking tokens; give headroom
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "confidence": {"type": "NUMBER"},
                        "evidence": {"type": "STRING"},
                    },
                    "required": ["score", "confidence", "evidence"],
                },
                "thinkingConfig": {"thinkingBudget": 0},  # disable chain-of-thought to save tokens
            },
        }
        for attempt in range(4):
            r = requests.post(url, json=payload, timeout=60)
            if r.status_code == 429:
                wait = 2 ** (attempt + 1)
                log.warning("  Gemini rate-limited, waiting %ds...", wait)
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                return {"score": -1, "confidence": 0.0,
                        "evidence": f"gemini_error {r.status_code}: {r.text[:200]}"}
            try:
                content = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return _parse_score_json(content)
            except Exception as e:
                return {"score": -1, "confidence": 0.0, "evidence": f"gemini_parse_error: {e}"}
        return {"score": -1, "confidence": 0.0, "evidence": "gemini_rate_limit_persistent"}

    if backend != "openai":
        return {"score": -1, "confidence": 0.0,
                "evidence": f"unknown backend: {backend}"}
    if not openai_key:
        return {"score": -1, "confidence": 0.0,
                "evidence": "openai backend requested but OPENAI_API_KEY not set"}

    # OpenAI GPT-4o-mini vision
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}},
            ],
        }],
        "max_tokens": 150, "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    for attempt in range(4):
        r = requests.post("https://api.openai.com/v1/chat/completions",
                           json=payload, headers=headers, timeout=60)
        if r.status_code == 429:
            wait = 2 ** (attempt + 1)
            log.warning("  OpenAI rate-limited, waiting %ds...", wait)
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            return {"score": -1, "confidence": 0.0,
                    "evidence": f"openai_error {r.status_code}: {r.text[:200]}"}
        content = r.json()["choices"][0]["message"]["content"]
        return _parse_score_json(content)
    return {"score": -1, "confidence": 0.0, "evidence": "openai_rate_limit_persistent"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-pairs", type=int, default=100, help="Pairs per class (default 100 ign + 100 ctrl)")
    parser.add_argument("--skip-vlm", action="store_true", help="Only fetch chips, don't call VLM")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--backend", choices=["ollama", "gemini", "openai", "auto"],
                        default="ollama", help="VLM backend (default: ollama, free local)")
    parser.add_argument("--ollama-model", default="llava:7b",
                        help="Ollama model name (default: llava:7b — verified vision-grounded)")
    parser.add_argument("--ollama-temperature", type=float, default=0.4,
                        help="Sampling temperature for ollama; 0 anchors to modal answer (default 0.4)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ignore existing parquet and re-score everything")
    args = parser.parse_args()

    CHIP_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=== VLM PRECURSOR PILOT — Stage VLM.1 ===\n")
    log.info("Backend: %s (model=%s)" if args.backend == "ollama" else "Backend: %s",
             args.backend, args.ollama_model)
    pairs = select_pilot_pairs(n_per_class=args.n_pairs, seed=args.seed)
    log.info("Pilot set: %d cells (%d ignited + %d control)",
             len(pairs), (pairs["class"] == "ignited").sum(), (pairs["class"] == "control").sum())

    # Resume: load existing parquet, build set of (cell_id, date_str, class, backend) keys
    # already scored. Same backend + valid score → skip.
    done_keys: set = set()
    cached_rows: dict = {}  # key → row dict to copy through unchanged
    if OUT_PATH.exists() and not args.no_resume:
        prev = pd.read_parquet(OUT_PATH)
        if "vlm_backend" not in prev.columns:
            prev["vlm_backend"] = "unknown"
        for _, prev_row in prev.iterrows():
            score = prev_row.get("vlm_score")
            backend_used = str(prev_row.get("vlm_backend", "unknown"))
            if score is None or pd.isna(score) or score < 0:
                continue
            if backend_used != args.backend:
                continue  # different backend, must rescore for consistency
            key = (str(prev_row["cell_id"]),
                   pd.Timestamp(prev_row["date"]).strftime("%Y-%m-%d"),
                   str(prev_row["class"]))
            done_keys.add(key)
            cached_rows[key] = prev_row.to_dict()
        log.info("Resume: %d rows already scored with backend=%s, will be skipped",
                 len(done_keys), args.backend)

    log.info("\nFetching S2 chips + scoring with VLM (this is the slow part)...")
    rows = []
    sleep_seconds = {"gemini": 7.0, "openai": 1.0, "ollama": 0.0, "auto": 1.0}[args.backend]
    n_skipped_resume = 0
    for i, r in pairs.iterrows():
        date = pd.Timestamp(r["date"])
        key = (str(r["cell_id"]), date.strftime("%Y-%m-%d"), str(r["class"]))
        if key in done_keys:
            rows.append(cached_rows[key])
            n_skipped_resume += 1
            continue
        chip_fname = CHIP_DIR / f"{r['class']}_{r['cell_id']}_{date.strftime('%Y%m%d')}.png"
        png = None
        if chip_fname.exists() and chip_fname.stat().st_size > 0:
            png = chip_fname.read_bytes()
        else:
            png = fetch_s2_chip(float(r["centroid_lat"]), float(r["centroid_lon"]), date)
            if png is not None:
                chip_fname.write_bytes(png)
        if png is None:
            log.warning("  [%d/%d] %s NO CHIP AVAILABLE", i + 1, len(pairs), r["cell_id"])
            rows.append({**r.to_dict(), "chip_available": False, "vlm_score": None,
                         "vlm_confidence": None, "vlm_evidence": None,
                         "vlm_backend": args.backend, "chip_bytes": 0})
            continue

        if args.skip_vlm:
            rows.append({**r.to_dict(), "chip_available": True, "vlm_score": None,
                         "vlm_confidence": None, "vlm_evidence": None,
                         "vlm_backend": args.backend, "chip_bytes": len(png)})
        else:
            try:
                result = score_chip_with_vlm(
                    png,
                    backend=args.backend,
                    ollama_model=args.ollama_model,
                    ollama_temperature=args.ollama_temperature,
                )
                rows.append({**r.to_dict(), "chip_available": True,
                              "vlm_score": result["score"], "vlm_confidence": result["confidence"],
                              "vlm_evidence": result["evidence"],
                              "vlm_backend": args.backend, "chip_bytes": len(png)})
            except Exception as e:
                log.warning("  VLM error on %s: %s", r["cell_id"], e)
                rows.append({**r.to_dict(), "chip_available": True, "vlm_score": -2,
                              "vlm_confidence": 0, "vlm_evidence": f"error: {e}",
                              "vlm_backend": args.backend, "chip_bytes": len(png)})

        if (i + 1) % 10 == 0:
            valid = sum(1 for x in rows
                        if isinstance(x, dict) and x.get("vlm_score") is not None
                        and (x.get("vlm_score") or -1) >= 0)
            log.info("  [%d/%d] processed (valid scores so far: %d, resumed: %d)",
                     i + 1, len(pairs), valid, n_skipped_resume)
        if not args.skip_vlm and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    df = pd.DataFrame(rows)
    df.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved: %s (%d rows; %d resumed, %d freshly scored)",
             OUT_PATH.relative_to(ROOT), len(df), n_skipped_resume,
             len(df) - n_skipped_resume)

    log.info("\n=== STAGE VLM.1 VERDICT ===")
    log.info("Chip availability: %d/%d (%.0f%%)",
             int(df["chip_available"].sum()), len(df), 100 * df["chip_available"].mean())

    valid = df[(df["chip_available"]) & (df["vlm_score"].notna()) & (df["vlm_score"] >= 0)]
    if len(valid) == 0 or args.skip_vlm:
        log.info("No VLM scores (skip_vlm=%s); pilot analysis will follow on next run", args.skip_vlm)
        return 0

    ignited_scores = valid[valid["class"] == "ignited"]["vlm_score"].astype(float).values
    control_scores = valid[valid["class"] == "control"]["vlm_score"].astype(float).values
    log.info("Ignited n=%d  mean_score=%.2f  median=%.1f",
             len(ignited_scores), np.mean(ignited_scores) if len(ignited_scores) else 0,
             np.median(ignited_scores) if len(ignited_scores) else 0)
    log.info("Control n=%d  mean_score=%.2f  median=%.1f",
             len(control_scores), np.mean(control_scores) if len(control_scores) else 0,
             np.median(control_scores) if len(control_scores) else 0)

    from scipy.stats import mannwhitneyu, spearmanr
    if len(ignited_scores) > 2 and len(control_scores) > 2:
        u_stat, u_p = mannwhitneyu(ignited_scores, control_scores, alternative="greater")
        log.info("Mann-Whitney U (ignited > control): U=%.1f  p=%.4f", u_stat, u_p)
        y = np.concatenate([np.ones(len(ignited_scores)), np.zeros(len(control_scores))])
        x = np.concatenate([ignited_scores, control_scores])
        rho, rho_p = spearmanr(x, y)
        log.info("Spearman rho(score, ignited): rho=%.3f  p=%.4f", rho, rho_p)
        delta = float(np.mean(ignited_scores) - np.mean(control_scores))
        log.info("\nExit criteria:")
        log.info("  [%s] delta_mean >= 2: delta=%.2f",
                 "PASS" if delta >= 2 else "FAIL", delta)
        log.info("  [%s] MW p < 0.01: p=%.4f",
                 "PASS" if u_p < 0.01 else "FAIL", u_p)
        log.info("  [%s] rho >= 0.10: rho=%.3f",
                 "PASS" if abs(rho) >= 0.10 else "FAIL", rho)
        all_pass = (delta >= 2) and (u_p < 0.01) and (abs(rho) >= 0.10)
        log.info("\n=== VERDICT: %s ===",
                 "PASS — proceed to Stage VLM.2 scale-up" if all_pass
                 else "FAIL — VLM can't see MP precursors; PARK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
