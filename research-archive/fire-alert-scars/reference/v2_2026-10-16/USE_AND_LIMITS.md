# Scar outlines v2: limits

Everything in `../v1_2026-10-15/USE_AND_LIMITS.md` still holds, with two changes.

## 1. Edge clipping is fixed
The v1 error bands were a median of 9% false area at the edge and 22% missed ground within 250 m.
- **Small and medium fires** were rarely at the edge, so their bands still apply in v2.
- **Large fires.** Their v1 "missed" share was partly the chip edge, and v2 adds a median 52% for redrawn FIRMS fires. Their v2 missed share is lower, but it has not been re-measured.
- **Cut-off outlines.** 214 outlines still touch even the 12 km chip (`still_at_edge`). Treat those as cut off.

## 2. The "must touch an alert" rule is still in v2, and this is what it does
A burned patch is part of a fire's outline only if it touches a 200 m circle round one of the fire's alert points (600 m for MODIS). Growth then follows connected burned ground from there. The spread review's concern is right: the outline is built around the alert points, so a model that is fed those same points has a small head start when scored against it.

**Test** (`check/no_circle.py`). It covers 199 fire events and 199 control points from the all-MP check sample. Controls are 3 km away, in forest, with no alert within 1.5 km and 30 days. Burned area was counted within 1 km of each point, with and without the rule (no growth step in either case):

| within 1 km | with the rule | without the rule |
|---|---|---|
| fires: mean burned ha | 23.9 | 31.7 (+33%) |
| fires: median burned ha | 9.8 | 19.8 |
| controls: sites with any "burned" patch | 4% | 28% |
| controls: mean "burned" ha | 0.1 | 1.6 |

**What a version without the rule would look like.** It is a seasonal burned-area map: every persistent burned patch of 0.5 ha or more, with no alert needed.
- Near fires it adds about 8 ha per fire within 1 km.
- About 1.6 ha of that is the background rate seen at control points, which is around 0.5 ha per km² per image pair. That background is a mix of real burns with no alert (FIRMS misses many small fires: 59% of Sentinel-2/Landsat fire-pixel clusters had no alert) and false patches such as shadow, harvest or haze.
- So roughly 80% of the extra ground near fires looks real. The cost is about 0.5 ha per km² of patches that may be false, and patches can no longer be tied to a particular fire.

**Recommendation.** For scoring spread models, use the v2 outlines and report the head start, or score against a fire-independent burned map built the same way without the circle rule. That map is not built yet; it is the next step if a thread needs it. For per-alert monitoring by officials, keep the rule, because it is what ties a scar to its alert.

## 3. Note from the spread thread (16 Oct)
The spread thread scores within 2.6 km of each fire's detections. That window holds 94% of v2 burned area for its 1,686 fires, and 88% for the regrown fires; 41 fires lose more than a tenth of their area. Tables from that thread name the outline version they use.
