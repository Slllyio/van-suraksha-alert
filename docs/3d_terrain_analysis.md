# 3D Terrain in v4 Portal — Deep Analysis

**Author:** Claude Code session 2026-04-25
**Branch:** `feature/portal-ge-dark`
**Asks:** add 3D terrain to the Live Map tab (deck.gl + MapLibre) so officers can see ridge-and-valley fire propagation, slope-aspect bias of CRITICAL cells, and aspect-of-attack vectors for dispatching ground crews.

---

## TL;DR (decision)

**Ship now:** AWS Terrain Tiles (free, public, no key) wired via MapLibre's
native `setTerrain` + a sidebar 3D toggle. Total work ≈ 60 LoC, ≈ 30 min.

**Upgrade later (own-data path):** bake Copernicus DEM 30m → terrain-RGB
PMTiles, serve from `/api/v2/terrain/{z}/{x}/{y}.png`, swap MapLibre source.
Day-of-work but eliminates the AWS dependency and uses the higher-quality DEM
we already have on disk.

Both paths produce the same UX. The recommendation is to ship the quick path
this session and queue the local-DEM path as a follow-up issue.

---

## 1. Problem statement

The current Live Map renders 2,629 banded alerts as flat scatter dots over a
2-D CartoDB dark basemap. MP forest officers have specifically asked for:

1. **Ridge / valley awareness** — fire spreads up-slope and along ridge lines.
   A 3-D view makes this geometrically obvious.
2. **Slope-aspect bias** — most ignitions cluster on south/southwest aspects
   (sun-baked, drier fuel). Currently invisible without a separate aspect
   raster.
3. **Aspect-of-attack vectors** — when dispatching, officers need to know
   whether to send a crew up-hill (slow, dangerous) or down-hill (fast).
4. **3-D extruded markers** — CRITICAL cells could rise above the terrain
   like spikes, scaled by `risk_score`, so the riskiest cells "punch out"
   visually even when many markers cluster.

---

## 2. Options compared

| Option | What it is | Setup | Ongoing cost | Quality | Recommended? |
|---|---|---|---|---|---|
| A | **deck.gl `TerrainLayer`** — pure deck.gl, mesh built from height-encoded raster tiles | needs an elevation tile source | tile $$ if hosted, free if self-hosted | Excellent — fully GPU-accelerated, integrates with picking | When you want deck.gl to own the entire view stack |
| B | **MapLibre native `setTerrain`** — basemap renders 3-D mesh, deck.gl scatter sits over it | 1 source + 1 setTerrain call | tile $$ source-dependent | Excellent — atmospheric perspective, fog, sky | **Picked** — least change to existing FireMap.tsx |
| C | **deck.gl extruded `PolygonLayer`** — divisions / cells extruded by a metric | none | none | Limited — schematic, not real terrain | Pair with A or B as a data overlay |
| D | **CesiumJS** — full 3-D globe | rip-and-replace the basemap | Cesium ION free tier ok, self-host complex | Best in class; overkill for state-scale viz | Not now |
| E | **External: Mapbox GL Terrain** | add Mapbox token, swap MapLibre → Mapbox | Mapbox $$ after free tier | Excellent | Pay-to-play; ruled out |

---

## 3. Tile-source comparison (for Option B, the picked path)

| Source | URL | Encoding | Cost | Coverage | Latency |
|---|---|---|---|---|---|
| **AWS Terrain Tiles** | `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` | Terrarium (R+G+B linear) | Free, public S3 | Global ≤ z15 | ~150 ms first tile |
| **MapTiler Terrain-RGB** | `https://api.maptiler.com/tiles/terrain-rgb-v2/{z}/{x}/{y}.png?key=…` | Terrain-RGB (Mapbox spec) | Free tier ≤ 100 k tiles/mo | Global | ~80 ms |
| **Mapbox Terrain-RGB** | `https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=…` | Terrain-RGB | Pay after free tier | Global | ~80 ms |
| **Self-hosted Copernicus DEM 30 m** | `/api/v2/terrain/{z}/{x}/{y}.png` (to be built) | Terrarium or Terrain-RGB | Zero — we own the source data | MP only (good — that's all we need) | < 50 ms localhost |

**Picked:** AWS Terrain Tiles for the now-shipping toggle. Terrarium encoding
is supported by both deck.gl and MapLibre out of the box. Zero account setup.

---

## 4. Local-DEM upgrade path (for the future issue)

We already have:

```
data/rasters/dem_30m.cog.tif          (Cloud-Optimized GeoTIFF, the goal format)
data/rasters/dem_mp_30m.tif           (full MP @ 30 m, ~1.5 GB)
data/rasters/dem_mp_240m.tif          (downsampled @ 240 m, ~24 MB — state overview)
data_lake/terrain/copernicus_dem_30m_mp/   (per-tile chunks)
```

To self-host terrain tiles:

1. **Tile the COG into Terrarium-encoded PNG**:

   ```bash
   pip install rio-rgbify rio-tiler
   rio rgbify --base-val -10000 --interval 0.1 \
     data/rasters/dem_30m.cog.tif \
     data/rasters/terrarium.mbtiles
   ```

2. **Serve from `dashboard/v3/serve.py`**:

   ```python
   elif re.match(r"^/api/v2/terrain/(\d+)/(\d+)/(\d+)\.png$", path):
       z, x, y = ...
       blob = sqlite_get_tile(MBTILES, z, x, y)
       self.send_response(200)
       self.send_header("Content-Type", "image/png")
       self.send_header("Cache-Control", "public, max-age=86400")
       ...
   ```

3. **Swap MapLibre source** in `FireMap.tsx`:

   ```ts
   map.addSource('terrain', {
     type: 'raster-dem',
     tiles: ['/api/v2/terrain/{z}/{x}/{y}.png'],   // was AWS URL
     encoding: 'terrarium',
     tileSize: 256,
     maxzoom: 14,
   });
   ```

Estimated effort: 4 hours (MBTiles bake is ~30 min for full MP @ 30 m, plus
backend route + cache headers + cache layer).

---

## 5. UX design

### Sidebar toggle (sits next to "Forest beats" / "Active fires")

```
☐ 3D terrain          ← off by default
    Exaggeration  [▮▮▮▯▯▯▯▯]  1.5×
    Pitch        [▮▮▮▮▯▯▯▯]  60°
```

### Map behavior

- Toggling **3D on**: animate `pitch` from 0° → 60°, fade in terrain mesh
- Toggling **3D off**: animate `pitch` 60° → 0°, remove terrain
- All deck.gl scatter / pulse / beats layers continue to work — they overlay
  the 3D mesh and are picked at z=0 against the projected screen-space
- Drag-rotate enabled when 3D is on (`map.dragRotate.enable()`)
- Zoom limit raised to 14 in 3D mode (terrain detail breaks down beyond)

### Future enhancement: extruded CRITICAL spikes

In a follow-up commit, replace the 140 CRITICAL `ScatterplotLayer` markers
with `ColumnLayer` cylinders extruded by `risk_score` × 5000 m. Each spike
becomes a fire-tower visualization that rises above the ridges.

```ts
new ColumnLayer<V17Cell>({
  id: 'critical-spikes',
  data: criticalCells,
  diskResolution: 12,
  radius: 600,
  extruded: true,
  pickable: true,
  elevationScale: 5000,
  getElevation: (d) => d.risk_score ?? 0,
  getPosition: (d) => [d.lon, d.lat, 0],
  getFillColor: [239, 68, 68, 220],
});
```

---

## 6. Performance considerations

| Concern | Impact | Mitigation |
|---|---|---|
| Terrain mesh + deck.gl over-draw | ~20 ms/frame on integrated GPU | Limit terrain `maxzoom` to 12; lazy-load terrain only when toggle flips on |
| Tile download from AWS | 30-50 tiles initial @ ~25 KB each | Browser caches; 1× cost on first 3D activation |
| `requestAnimationFrame` jank during pitch animation | Visible stutter during pitch ease | Use MapLibre's `easeTo` (built-in raf-friendly) instead of manual interpolation |
| Memory: 3D mesh allocates ~100 MB GPU | OK on 8 GB+ devices | If portal is run on low-spec field tablets, downgrade to 2D below screen-width 1024 px |

---

## 7. Risks + mitigations

1. **AWS terrain endpoint goes down or moves** — historically stable since
   2018, but if it does, swap to MapTiler free tier (5-line change) or
   accelerate the local-DEM upgrade path.
2. **Officers find 3D distracting** — keep the toggle off-by-default;
   measure adoption via the access log (look for `?terrain=on` query param
   if we add it).
3. **Pitch breaks the floating flyout positioning** — verify after wiring;
   may need to project the picked cell back to map-relative coords.
4. **PMTiles vs MBTiles backend choice** — MBTiles (sqlite) has zero
   external deps and works with Python's stdlib `sqlite3`. PMTiles needs a
   Go binary or pmtiles Python package. Pick MBTiles for the local upgrade.

---

## 8. Verification plan

After shipping:

```bash
# 1. Toggle 3D on, expect pitch animation
browse --ws 9222 click '[data-action="toggle-3d"]'

# 2. AWS terrain tiles loaded
browse --ws 9222 eval "performance.getEntriesByType('resource')
  .filter(e => e.name.includes('elevation-tiles-prod')).length"

# 3. deck.gl scatter still picks correctly in 3D
browse --ws 9222 click_xy 800 400  # picks a CRITICAL cell, opens flyout

# 4. Pitch returns to 0 when toggled off
browse --ws 9222 click '[data-action="toggle-3d"]'
browse --ws 9222 eval "deckRef.current?.props?.viewState?.pitch"  # expect 0
```

---

## 9. Out of scope (explicit non-goals for the v1 ship)

- 3D buildings (no 3D building footprints in MP forest divisions)
- Sky atmosphere (`map.setSky`) — could add but not requested
- Cloud / rain animation overlay (tempting but distracting for ops)
- Time-of-day shadow casting
- Globe view (CesiumJS-class feature)
