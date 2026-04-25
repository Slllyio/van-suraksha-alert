# v17.5 Edge-Bias Brutal Analysis

**Author:** Claude Code session 2026-04-25
**Trigger:** Officer observed "all predictions at edges, no interior — seems faulty."
**Verdict:** **The observation is correct. The model is structurally edge-biased and the cause is fundamental, not a bug.**

---

## TL;DR

Today's prediction (`ignition_risk_v17_2026-04-24.json`, 1,570 banded alerts) measured against the dissolved MP forest-division boundary:

| Distance from forest/non-forest boundary | % of alerts |
|---|---:|
| Within **1 km** of edge | **71.2 %** |
| Within **5 km** of edge | **99.9 %** |
| Within **10 km** of edge | **100.0 %** |
| Deep interior (**> 20 km** from any edge) | **0.0 %** |

Median distance to nearest forest boundary, by band:

| Band | Median dist | Within 5 km | Deep interior |
|---|---:|---:|---:|
| CRITICAL (171) | 0.75 km | 100.0 % | 0.0 % |
| ALERT (268)    | 0.84 km | 100.0 % | 0.0 % |
| WATCH (1,131)  | 0.69 km |  99.9 % | 0.0 % |

**Zero of 1,570 alerts falls more than 20 km into the forest interior.** All three bands behave identically — this isn't a banding artefact, it's the underlying risk model.

---

## The structural confession (Hawkes feature dominance)

Per [`docs/3d_terrain_analysis.md`](3d_terrain_analysis.md) and `CLAUDE.md`, v17.5's top feature by gain is the Hawkes self-excitation term `hawkes_n_recent_10km_7d`, contributing **74 / 100** of relative gain — more than the next nine features combined.

Today's distribution:

```
HAWKES_LAMBDA (long-window self-excitation):
  mean=0.0061  median=0.0018  max=0.1317
  cells with hawkes==0:     9.3 %
  cells with hawkes>0.01:  19.0 %
  cells with hawkes>0.05:   1.0 %
```

Per-band Hawkes profile:

```
CRITICAL  n= 171  mean_lambda=0.0067  zero_pct= 8.2 %  high_pct=21.1 %
ALERT     n= 268  mean_lambda=0.0055  zero_pct=13.8 %  high_pct=17.2 %
WATCH     n=1131  mean_lambda=0.0062  zero_pct= 8.4 %  high_pct=19.1 %
```

**Hawkes is a contagion model.** It says "predict fires where fires recently happened." Most MP forest fires are anthropogenic — slash-and-burn at the agriculture–forest interface, NTFP collectors burning fringe undergrowth, accidental cigarette ignitions on the road system that runs along edges. Hawkes amplifies this:

> Edge fires beget edge labels → labels train the model → model predicts edges.

Interior cells with no recent fire history get λ ≈ 0 → never light up. CLAUDE.md's "cold-start blind spot" finding (5.9 % R@5 % in low-Hawkes cells, 25.5 % in high-Hawkes) is exactly this asymmetry.

---

## Why the predictions LOOK like they ring the forest

Three reinforcing factors — none individually a bug, together producing the visible pattern:

1. **Hawkes self-excitation** (above) — 74 % of feature gain
2. **Distance-to-road feature** (rank ~5 by gain) is correlated with edge-ness; roads run along forest perimeter where they meet villages
3. **Population-within-1 km** feature (rank ~6) is concentrated at edges where settlements sit

All three features encode "human proximity," and human proximity is strongly bimodal in MP: **either you're in a village/road network at the forest edge, or you're 10+ km into uninhabited dry deciduous teak forest.** The model has learned to predict the edge mode and is structurally blind to the interior mode.

---

## Is the interior actually fire-free? (Reality check)

**No.** Cross-referencing FIRMS VIIRS active-fire detections 2014-2024 (1.35 M rows in our consolidated parquet) with the MP forest-interior subset:

> **77 % of historical fires actually start in low-Hawkes cells**, per CLAUDE.md.

So the model misses the majority of true fire origins. It just happens to be **right** about contagion (existing fires spreading to neighbors via Hawkes) — that's the 25.5 % R@5 % in high-Hawkes regime.

The portal currently **looks confident** because it shows 1,570 specific alerts. The honest framing is:

- **Confident at edges where fires already happen.**
- **Near-random in the interior where most NEW outbreaks begin.**

---

## What's been tried (and failed)

Per CLAUDE.md, eight independent attempts to add interior signal have failed:

| Attempt | Method | Result |
|---|---|---|
| VLM zero-shot | LLaVA-7b on S2 chips | MW p=0.74 (no signal); image-agnostic responses |
| CLIP embeddings | ViT-L/14 + classifier | 5-fold ROC=0.562, perm p=0.095 |
| Temporal NDVI/BSI delta | 5-fold | ROC=0.539 |
| Sentinel-1 SAR amplitude | VV/VH both orbits | ρ≈0.01, p>0.3 |
| Dynamic World monthly LULC | bare/crops/trees deltas | model ignored features (1 of 30 in top-30 gain) |
| Prithvi-EO-2.0 BurnScars (US-pretrained) | Frozen | median F1=0.013 (does not transfer) |
| GDELT village-level NER | District-centroid only | 0 % yield |
| Hybrid Bayesian ranking | All λ-blend variants | DECREASE aggregate R@5 % |

**Common failure mode:** sub-cell signal. A 50–200 m² farmer clearing is invisible when averaged over a 4 km² (2 km × 2 km) cell. The data we have *cannot* see interior fires before they ignite.

---

## What COULD work but hasn't been tried

Sorted by promise vs. effort:

1. **Beat-level patrol reports** — forest officers already file ~5,000 patrol logs/season. If text is digitized and geocoded, NER on patrol notes ("dry leaves piled near beat X") would give pre-ignition human signal. **Effort: 6 weeks** (NER pipeline + geocoder + UI for patrol log entry).
2. **Raise spatial resolution to 500 m** — re-train on 500 m cells (~16 × current cell count = ~700 k cells). This *might* let sub-cell anthropogenic signal resolve. CLAUDE.md notes "next gain needs 500 m resolution OR new label source." **Effort: 2-3 weeks** (re-feature engineering + retrain + storage cost).
3. **Mobile phone density** — Google Community Mobility data already failed (correlation collapsed after detrending) but Indian carrier (Jio/Airtel) per-cell-tower data might still help if obtainable. **Effort: indeterminate** (data access blocked).
4. **NTFP collection calendar overlay** — tendu / mahua collection windows are predictable. Joining a calendar feature ("days into tendu season") might help with seasonality. **Effort: 1 week** (the calendar exists in forest-dept docs).
5. **Lightning strike feed** — natural ignition source. NLDN-equivalent for India is not free; Vaisala has an India product. **Effort: 2 weeks + data licensing $$**.

---

## What is **structurally impossible** with current data

- **Predicting individual interior NEW outbreaks** — 50 m clearings are invisible at 2 km cells; even at 30 m raster they'd be 2-7 pixels and our cleanest sensor (Sentinel-2) revisits every 5 days at best. **The model can't see the precursor.**
- **Catching arson** — no known feature has signal for malicious ignition.

---

## Recommended portal mitigations (UX honesty)

The model *can't* be fixed structurally without new data. But the portal can stop pretending the predictions are uniform-quality.

### Mitigation 1 — Surface the cold-start blind-spot transparently

Add a per-cell **"Trust strength" badge** in the MapFlyout:

| Cell condition | Badge | Officer guidance |
|---|---|---|
| `hawkes_lambda > 0.01` AND `n_recent_10km_7d > 0` | 🟢 **HIGH** | Act on this. v17.5 catches 25.5 % of fires in this regime. |
| Hawkes nonzero, no recent fires | 🟡 **MEDIUM** | Cross-check with patrol before dispatch. |
| `hawkes_lambda < 0.001` | 🔴 **LOW** | **Cold-start zone — this prediction is near-random.** Use only as awareness, do NOT dispatch on this cell alone. |

Today's distribution:

- HIGH: 19 % of alerts
- MEDIUM: ~71 % of alerts
- LOW (cold-start): ~9.3 % of alerts (zero-Hawkes — these are pure floor-promotion noise)

### Mitigation 2 — Show a "Coverage diagnostic" view

A second portal view that overlays:
- **Predicted alerts** (current scatter)
- **Past-5-year burnt-area heatmap** from MCD64 (where fires actually happened)
- **Difference layer:** cells that historically burned but have no current alert → **interior blind spots**

Officers can see at a glance the gap between "where fires happen" and "where the model predicts."

### Mitigation 3 — Explicit "Interior monitor" override

Add a sidebar control:

> ☐ Augment with historical-burn priors
>    Promotes any cell to WATCH if it burned in 3+ of the last 5 fire seasons,
>    regardless of the model's score.

This is a **deterministic** override, not an ML "fix." It surfaces the climatology floor that exists in the operational pipeline (`scripts/build_operational_alerts.py`) but isn't currently visible in the portal.

---

## Conclusion

> **Brutally honest:** the predictions cluster at edges because (a) the dominant feature (Hawkes self-excitation) is by definition a contagion-from-known-fires signal, (b) the supporting features (distance-to-road, population) are also edge-correlated, and (c) eight attempts to add interior-pre-ignition signal have failed because farmer clearings are sub-cell. **This is a known structural ceiling, documented as `CONFIRMED DEAD ENDS` in `CLAUDE.md`.**

The best the portal can do right now is **be transparent** about the limitation — surface the trust badge, expose the historical-burn diff, give officers an interior-monitor override.

The best the *model* could do (as a follow-up project) is **drop to 500 m cells + re-feature** (2-3 weeks) or **wait for patrol log digitization** (6 weeks). Neither is a same-day fix.

---

## Generated from

- `outputs/dashboard_feed/ignition_risk_v17_2026-04-24.json` (1,570 alerts)
- `data/aoi/mp_divisions_ultra.geojson` (87 dissolved division polygons)
- `CLAUDE.md` § "Production Status (2026-04-19, Pivot A v2 sprint COMPLETE)" + "CONFIRMED DEAD ENDS"
- Live `/api/v2/ignition-v17` — same payload the v4 portal renders
