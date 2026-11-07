# Prithvi survey-model: handoff (parked 8 Nov 2026)

**Goal (owner):** a pretrained Prithvi-EO-2.0 model fine-tuned on the 2015 Guna stock survey (forest / open / farm), turned into a change map,
and scored head to head against the v1 rule. Full diagnosis: `prithvi_diagnosis.md`.

## State
- Two DirectML bugs found and fixed, both verified against CPU:
  1. `F.interpolate` / `nn.Upsample` bilinear with align_corners=False, replaced by `up_bilinear()`;
  2. `F.cross_entropy(ignore_index=...)`, replaced by `masked_ce()`. `F.one_hot` also fails on DirectML.
- Valid results: C LightGBM 70.7%, d LightGBM on cleaned labels 70.6%, B AlphaEarth MLP 68.5%, e frozen-Prithvi token probe 64.2% (pure tokens 77.5%).
- Not yet rerun with both fixes: A (fine-tuned, last 4 blocks), a (frozen + linear head), b (fixed recipe, last 2 blocks, augmented crop bank, early stopping), c (b on cleaned labels).
- The GPU is free. No Prithvi process is running.

## Files
- Code (all in `forest_loss_monitor/scripts`):
  - `e105_hls_guna.py`: HLS fetch, done; 115 tiles x 2015 and 2017-25 in `work/hls_guna`.
  - `e106_survey_data.py`: labels at 30 m; `work/survey_model/labels30.npz`, `ranges.csv`.
  - `e107_survey_states.py`: B, C, Cc.
  - `e108_prithvi_net.py`: encoder loader, heads, `up_bilinear`, `masked_ce`.
  - `e109_prithvi_survey.py`: A (cache / cv / final). The token cache at block 20 is in `work/survey_model/prithvi_tok2015`.
  - `e111_prithvi_audit.py`: label audit; `clean_lab.npy`.
  - `e112_prithvi_variants.py`: a, b, c, e. The crop bank at block 22 is built in `work/survey_model/prithvi_bank22`.
  - `e110_survey_score.py`: head-to-head on every label set.
- Invalid outputs kept for the record: `invalid_bilinear_bug/`, `invalid_ce_bug/` (outputs and work).

## Next steps, in order
```
python e109_prithvi_survey.py cv
python e109_prithvi_survey.py final
python e112_prithvi_variants.py cv a
python e112_prithvi_variants.py final a
python e112_prithvi_variants.py cv b
python e112_prithvi_variants.py final b
python e112_prithvi_variants.py cv c
python e112_prithvi_variants.py final c
python e110_survey_score.py
```
Times on the RX 9060 XT: A and a about 1 h together; b and c about 3-4 h each; scoring about 15 min.
The variants are pre-declared (`prithvi_diagnosis.md` section 3): do not change settings after seeing test labels.
Before trusting any new DirectML op, check it against CPU (see the op table in section 4).

## Also open
The fire project's DirectML models use the broken bilinear op (and may use ignore_index CE). VanAagni v1.0 and others should be re-scored on CPU.
