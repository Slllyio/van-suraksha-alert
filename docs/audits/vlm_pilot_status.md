# VLM Precursor Pilot — BLOCKED on API credentials

## Status (2026-04-16 11:32)

**Pipeline built and validated end-to-end on chip fetching (free).**
**VLM scoring step BLOCKED — OpenAI key returns `insufficient_quota` (account out of credit).**

## What works

- `scripts/pilot_vlm_precursor.py` — complete pilot runner
- **Sentinel-2 chip fetch via GEE is 100% functional**
  - Pulls least-cloudy S2 scene in [D-14, D-1] window per cell
  - Exports 6.7 km × 6.7 km RGB patch @ 224×224 pixels via `getThumbURL`
  - ~3 seconds per chip
  - Chips cached to `data_lake/audits/vlm_pilot_chips/`
- **Pilot pair selection is deterministic + reproducible**
  - 100 ignited low-Hawkes cells sampled from 2025 hold-out
  - 100 matched controls (same beat, same Thursday, no ignition)
- **OpenAI GPT-4o-mini vision API integration is code-complete**
  - Structured prompt returns `{score, confidence, evidence}`
  - Retry with exponential backoff (2/4/8/16s)
  - Low-detail mode (~$0.005/call)
- **Statistical verdict framework ready**
  - Mann-Whitney U test (ignited > control)
  - Spearman ρ(score, class)
  - Mean delta ≥ 2 exit criterion

## What's blocked

`OPENAI_API_KEY` in `.env` returns:
```
{"error":{"message":"You exceeded your current quota, please check your plan and billing details.","type":"insufficient_quota"}}
```

Cost to unblock: **~$15-20** for the 200-cell pilot (200 calls × ~$0.005-0.01 each).

## No alternative VLM credentials found

Checked `.env` for GEMINI_API_KEY, GOOGLE_API_KEY (present but empty), ANTHROPIC_API_KEY, AZURE, GROQ, TOGETHER, REPLICATE, HUGGINGFACE, OPENROUTER — none present.

## Options to unblock

| Option | Cost | Effort |
|--------|------|--------|
| Top up OpenAI account | ~$20 | 5 min — script runs unchanged |
| Get free Gemini API key from AI Studio | $0 (free tier 15 RPM) | 10 min — change 3 lines in script to Gemini SDK |
| Run local LLaVA / Qwen2-VL via Ollama | $0 | 2-3 hours — set up local VLM server, rewrite API call |
| Fall back to CLIP embeddings (no VLM text) | $0 | 3-4 hours — swap API call for CLIP embedding extraction + train sub-model |

## What's fetched so far

200 Sentinel-2 RGB PNG chips (100 ignited + 100 control, low-Hawkes cells, 14-day pre-Thursday window) are cached at `data_lake/audits/vlm_pilot_chips/` ready for any VLM pipeline. Total size ~8 MB.

When any credentials land:
```bash
# Just rerun the pilot — chips are cached, won't re-fetch
python scripts/pilot_vlm_precursor.py --n-pairs 100
```

This will produce `data_lake/audits/vlm_pilot_scores.parquet` + a statistical verdict against the Stage VLM.1 exit criteria (mean delta ≥ 2, MW p < 0.01, ρ ≥ 0.10).

## Recommended path

**Get a free Gemini API key** (15 req/min free tier is enough for the 200-cell pilot). Adjust `score_chip_with_vlm()` to call `generativeai` SDK instead of OpenAI. Total work: ~20 minutes.

If the pilot PASSES, then the decision becomes "is it worth paying for OpenAI/Gemini at production scale" — which is a separate conversation.
