// FireMap — MapLibre basemap (dark) + deck.gl layers for v17 ignition cells and
// FIRMS VIIRS fires. Uses WebGL2 via deck.gl for fast rendering of 2k+ cells.

import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Deck } from 'deck.gl';
import { ScatterplotLayer, GeoJsonLayer } from '@deck.gl/layers';
import { HeatmapLayer } from '@deck.gl/aggregation-layers';
// `_TerrainExtension` is the deck.gl 9 export name (underscore-prefixed
// to signal experimental status). Aliased for clarity.
import { _TerrainExtension as TerrainExtension } from '@deck.gl/extensions';
import type { PickingInfo, Layer } from '@deck.gl/core';

// Single shared TerrainExtension instance so deck.gl's prop-diff cache
// recognizes "same extension" across re-renders and doesn't churn shaders.
// IMPORTANT: only attach this extension to layers when 3D terrain is
// ACTIVE on the MapLibre instance. Attaching it when no terrain source
// is registered causes deck.gl 9.3's `_TerrainExtension` (still
// underscore-prefixed / experimental) to silently drop the layer from
// the render pass — every layer with the extension goes invisible.
// Use `terrainProps` (computed inside the component, gated on the
// `terrain3D` prop) instead of including these props unconditionally.
const TERRAIN_EXT = new TerrainExtension();
import { colors } from '../designTokens';
import type {
  V17Cell,
  ViirsFire,
  GeoJSONFeatureCollection,
  HistoricalBurnPoint,
  HistoricalBurnPrior,
  FuelLoadRecord,
  BurnPrediction,
} from '../lib/api';
import 'maplibre-gl/dist/maplibre-gl.css';

const INITIAL_VIEW = {
  longitude: 78.5,  // MP state centroid (approx)
  latitude: 23.5,
  zoom: 5.8,
  pitch: 0,
  bearing: 0,
};

// Minimal CartoDB-style dark basemap (no API key required)
const MAP_STYLE =
  'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

interface FireMapProps {
  cells: V17Cell[];
  viirs: ViirsFire[];
  /** Optional MP forest-beats GeoJSON (MultiPolygon features). When null, the
   *  beats layer is not rendered. */
  beats?: GeoJSONFeatureCollection | null;
  /** Optional dissolved MP division polygons (87 features, ~8 MB ultra).
   *  Renders ABOVE beats but BELOW alerts so divisions outline the
   *  state-level context without obscuring the marker dots. */
  divisions?: GeoJSONFeatureCollection | null;
  /** Toggle 3D terrain. When true, attaches AWS Terrain Tiles as a raster-DEM
   *  source and animates pitch to 60°. See docs/3d_terrain_analysis.md. */
  terrain3D?: boolean;
  /** Vertical exaggeration multiplier for 3D terrain (default 1.5). */
  terrainExaggeration?: number;
  /** Mitigation 2 — past-5-year burn density heatmap. When provided +
   *  non-empty, deck.gl renders a HeatmapLayer underneath the alerts so
   *  officers can see WHERE fires actually keep happening vs WHERE the
   *  model predicts. */
  burnDensityPoints?: HistoricalBurnPoint[];
  /** Mitigation 2 — interior blind-spot rings: cells that historically
   *  burned in 3+ of the last 5 seasons but have NO matching v17 alert
   *  this cycle. Rendered as orange hollow circles. */
  blindSpotCells?: HistoricalBurnPrior[];
  /** Mitigation 3 — climatology-promoted WATCH cells. Officer-toggled
   *  override that surfaces deterministic prior-burn cells regardless
   *  of what v17 says. Rendered as amber double rings to make clear
   *  this is NOT a model prediction. */
  priorWatchCells?: HistoricalBurnPrior[];
  /** Per-cell fuel-load layer (t/ha). Renders as a HeatmapLayer with a
   *  teal→amber→brown ramp so it doesn't visually collide with the
   *  burn-density magenta or alert palettes. */
  fuelLoadRecords?: FuelLoadRecord[];
  /** Optional active burn-area prediction polygon. When set, deck.gl
   *  renders 3 nested GeoJsonLayers for the 6h/12h/24h spread polygons
   *  with increasing transparency. Set/cleared by MapFlyout. */
  burnPrediction?: BurnPrediction | null;
  onCellClick?: (cell: V17Cell) => void;
}

function bandColor(band: string): [number, number, number, number] {
  switch (band) {
    case 'CRITICAL': return [239, 68, 68, 210];
    case 'ALERT':    return [249, 115, 22, 200];
    case 'WATCH':    return [251, 191, 36, 190];
    default:         return [100, 116, 139, 160];
  }
}

function bandRadius(band: string, risk?: number): number {
  // Base radius by band + subtle risk-score weighting. Kept small so dense
  // clusters read as individual markers, not one blob.
  const base = band === 'CRITICAL' ? 2200 : band === 'ALERT' ? 1600 : 1200;
  const weight = typeof risk === 'number' ? Math.max(0.8, Math.min(1.2, risk * 1.1)) : 1;
  return base * weight;
}

export default function FireMap({
  cells,
  viirs,
  beats,
  divisions,
  terrain3D = false,
  terrainExaggeration = 1.5,
  burnDensityPoints,
  blindSpotCells,
  priorWatchCells,
  fuelLoadRecords,
  burnPrediction,
  onCellClick,
}: FireMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<Deck | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  // Hold the latest onCellClick so the mount-only map.on('click') handler
  // always sees the freshest callback (avoids stale closure — frontend
  // review CRIT #1).
  const onCellClickRef = useRef(onCellClick);
  useEffect(() => {
    onCellClickRef.current = onCellClick;
  }, [onCellClick]);

  // Conditional terrain-extension props. Spread into each layer config.
  // When 3D terrain is OFF the spread is `{}` so layers render at z=0
  // without the experimental extension that breaks no-terrain-source
  // rendering.
  const terrainProps = useMemo(
    () =>
      terrain3D
        ? ({ extensions: [TERRAIN_EXT], terrainDrawMode: 'drape' } as const)
        : ({} as const),
    [terrain3D],
  );

  // Animation tick — drives the pulsing rings on CRITICAL markers.
  // Cycles 0 → 1 every 1.6 s (rebuilt every 50 ms → ~32 rebuilds/cycle).
  const [pulse, setPulse] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => {
      setPulse((p) => (p + 0.03) % 1);
    }, 50);
    return () => clearInterval(interval);
  }, []);
  const criticalCells = useMemo(
    () => cells.filter((c) => c.band === 'CRITICAL'),
    [cells],
  );

  // Pulse layer is rebuilt every 50 ms on its own so the data layers below
  // don't churn. Data layers only rebuild when `cells`/`viirs`/`beats` change.
  const pulseLayer = useMemo(
    () =>
      new ScatterplotLayer<V17Cell>({
        id: 'critical-pulse',
        data: criticalCells,
        pickable: false,
        stroked: true,
        filled: false,
        radiusUnits: 'meters',
        radiusMinPixels: 3,
        radiusMaxPixels: 16,
        lineWidthUnits: 'pixels',
        lineWidthMinPixels: 0.5,
        getPosition: (d) => [d.lon, d.lat, 0],
        getRadius: 2200 + pulse * 4500,
        getFillColor: [0, 0, 0, 0],
        getLineColor: [239, 68, 68, Math.round((1 - pulse) * 150)],
        getLineWidth: 1 + (1 - pulse) * 1.2,
        updateTriggers: {
          getRadius: pulse,
          getLineColor: pulse,
          getLineWidth: pulse,
          data: criticalCells.length,
        },
        ...terrainProps,
      }),
    [criticalCells, pulse, terrainProps],
  );

  // Mitigation 2 — burn-density heatmap. Sits at the very bottom so
  // every other layer reads on top. Weight bins by 5y total fire count.
  // Color ramp: navy → blue → teal → amber → orange → MAGENTA terminus.
  // The magenta terminus is deliberate — keeps the warmest end OFF the
  // CRITICAL-red axis so heatmap warmth doesn't visually impersonate
  // a model alert.
  const burnDensityLayer = useMemo(() => {
    if (!burnDensityPoints || burnDensityPoints.length === 0) return null;
    return new HeatmapLayer<HistoricalBurnPoint>({
      id: 'burn-density-5y',
      data: burnDensityPoints,
      pickable: false,
      getPosition: (d) => [d.lon, d.lat],
      getWeight: (d) => d.w,
      radiusPixels: 30,
      intensity: 0.9,
      threshold: 0.04,
      colorRange: [
        [40, 60, 90, 0],
        [62, 109, 152, 110],
        [89, 159, 124, 140],
        [218, 175, 70, 170],
        [180, 60, 140, 200],   // magenta-600: distinct from any alert color
        [210, 80, 180, 220],   // magenta-500 terminus
      ],
      updateTriggers: {
        getWeight: burnDensityPoints.length,
      },
    });
  }, [burnDensityPoints, terrainProps]);

  // Mitigation 2 — interior blind-spot rings. PURPLE hollow circles
  // (token: colors.coverage.blindSpot = #7C3AED). Deliberately off the
  // red/orange/amber alert axis so officers cannot confuse these with
  // ALERT-orange model dots. Tightened pixel radius so blind-spots
  // never visually outrank live alerts.
  const blindSpotLayer = useMemo(() => {
    if (!blindSpotCells || blindSpotCells.length === 0) return null;
    return new ScatterplotLayer<HistoricalBurnPrior>({
      id: 'blind-spot-rings',
      data: blindSpotCells,
      pickable: false,
      stroked: true,
      filled: false,
      radiusUnits: 'meters',
      radiusMinPixels: 3,
      radiusMaxPixels: 9,
      lineWidthUnits: 'pixels',
      lineWidthMinPixels: 1,
      lineWidthMaxPixels: 1.5,
      getPosition: (d) => [d.lon, d.lat, 0],
      getRadius: 1800,
      getLineColor: [124, 58, 237, 230],   // purple — unambiguous vs ALERT orange
      getLineWidth: 1.4,
      ...terrainProps,
    });
  }, [blindSpotCells, terrainProps]);

  // Mitigation 3 — climatology-promoted cells. DARKER amber (amber-600
  // #D97706) and HOLLOW so the rings read as "watch this for historical
  // reasons" without being mistaken for a model WATCH (#FBBF24 amber-400,
  // filled). Pixel radius tightened to stay below ignitionLayer's
  // visual weight (the model output should remain dominant).
  const priorWatchLayer = useMemo(() => {
    if (!priorWatchCells || priorWatchCells.length === 0) return null;
    return new ScatterplotLayer<HistoricalBurnPrior>({
      id: 'prior-watch-promoted',
      data: priorWatchCells,
      pickable: false,
      stroked: true,
      filled: false,                       // hollow — distinguishes from filled WATCH dots
      radiusUnits: 'meters',
      radiusMinPixels: 3,
      radiusMaxPixels: 7,                  // smaller than ignitionLayer (8) → model wins visually
      lineWidthUnits: 'pixels',
      lineWidthMinPixels: 1,
      lineWidthMaxPixels: 2,
      getPosition: (d) => [d.lon, d.lat, 0],
      getRadius: 1200,
      getLineColor: [217, 119, 6, 230],    // amber-600, darker than WATCH amber-400
      getLineWidth: 1.6,
      ...terrainProps,
    });
  }, [priorWatchCells, terrainProps]);

  // Fuel-load CATEGORICAL ScatterplotLayer keyed by SB40 class. User
  // explicitly asked for separable colors so high leaf-litter forest
  // (TL2) is distinguishable from cropland (GR1) and grassland (GR2)
  // — a continuous heatmap blurred them. Each SB40 class gets a
  // distinct hue from `colors.fuelClass`, deliberately off the alert
  // palette + off the burn-density magenta. Cell radius is small
  // (~3px) so 25k cells don't blob; user controls density via zoom.
  const fuelLoadLayer = useMemo(() => {
    if (!fuelLoadRecords || fuelLoadRecords.length === 0) return null;
    const colorFor = (cls: string): [number, number, number, number] => {
      // Hex → RGBA. Lightweight inline parse; SB40 set is bounded.
      const hex = (colors.fuelClass as Record<string, { fg: string }>)[cls]?.fg
        ?? colors.fuelClass.NB9.fg;
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      return [r, g, b, 200];
    };
    return new ScatterplotLayer<FuelLoadRecord>({
      id: 'fuel-load-categorical',
      data: fuelLoadRecords,
      pickable: false,
      stroked: false,
      filled: true,
      radiusUnits: 'meters',
      radiusMinPixels: 2,
      radiusMaxPixels: 6,
      getPosition: (d) => [d.lon, d.lat, 0],
      // Bivariate encoding — COLOR is fuel CLASS (categorical, distinct
      // hue per SB40), SIZE is fuel LOAD (continuous, scales with
      // t/ha). 15 t/ha is the cap (forest litter). User asked for
      // separable categories so the class hue is the primary signal;
      // size adds within-class density variation.
      getRadius: (d) => 600 + (d.fuel_load_t_per_ha / 15) * 1200,
      getFillColor: (d) => colorFor(d.sb40_dominant),
      updateTriggers: {
        getFillColor: fuelLoadRecords.length,
        getRadius: fuelLoadRecords.length,
      },
      ...terrainProps,
    });
  }, [fuelLoadRecords, terrainProps]);

  // Burn-prediction polygons — 3 stacked GeoJsonLayers for 6h/12h/24h
  // with shrinking opacity (most recent prediction = most opaque).
  // These render only when the MapFlyout has fired a prediction.
  const burnPredLayers = useMemo(() => {
    if (!burnPrediction) return [];
    const horizons = [
      { id: 'burn-24h', data: burnPrediction.spread_24h, fill: [180, 60, 40, 60],   stroke: [180, 60, 40, 200],  width: 1.5 },
      { id: 'burn-12h', data: burnPrediction.spread_12h, fill: [220, 100, 50, 100], stroke: [220, 100, 50, 230], width: 1.6 },
      { id: 'burn-6h',  data: burnPrediction.spread_6h,  fill: [255, 180, 80, 150], stroke: [255, 180, 80, 250], width: 2.0 },
    ];
    return horizons.flatMap((h) => {
      const poly = h.data?.polygon;
      if (!poly || !poly.features?.length) return [];
      return [
        new GeoJsonLayer({
          id: h.id,
          data: poly as unknown as GeoJSON.FeatureCollection,
          pickable: false,
          stroked: true,
          filled: true,
          lineWidthUnits: 'pixels',
          lineWidthMinPixels: 1,
          lineWidthMaxPixels: 3,
          getFillColor: h.fill as [number, number, number, number],
          getLineColor: h.stroke as [number, number, number, number],
          getLineWidth: h.width,
          parameters: { blend: true, blendFunc: [770, 771] },
          ...terrainProps,
        }),
      ];
    });
  }, [burnPrediction, terrainProps]);

  // Dissolved 87 MP forest-division polygons. Slightly bolder stroke
  // than beats so divisions read as the state-level container, beats
  // as the granular detail. No fill — keeps the map readable.
  const divisionsLayer = useMemo(() => {
    if (!divisions) return null;
    return new GeoJsonLayer({
      id: 'divisions-boundary',
      data: divisions as unknown as GeoJSON.FeatureCollection,
      pickable: false,
      stroked: true,
      filled: false,
      lineWidthUnits: 'pixels',
      lineWidthMinPixels: 0.6,
      lineWidthMaxPixels: 1.4,
      getLineColor: [148, 163, 184, 90],   // slate-400 @ 35%
      getLineWidth: 0.9,
      parameters: { blend: true, blendFunc: [770, 771] },
      ...terrainProps,
    });
  }, [divisions, terrainProps]);

  const beatsLayer = useMemo(() => {
    if (!beats) return null;
    return new GeoJsonLayer({
      id: 'beats-boundary',
      data: beats as unknown as GeoJSON.FeatureCollection,
      pickable: false,
      stroked: true,
      filled: true,
      lineWidthUnits: 'pixels',
      lineWidthMinPixels: 0.4,
      lineWidthMaxPixels: 0.9,
      getFillColor: [129, 201, 149, 8],
      getLineColor: [129, 201, 149, 80],
      getLineWidth: 0.6,
      parameters: { blend: true, blendFunc: [770, 771] },
      ...terrainProps,
    });
  }, [beats, terrainProps]);

  const ignitionLayer = useMemo(
    () =>
      new ScatterplotLayer<V17Cell>({
        id: 'ignition-cells',
        data: cells,
        pickable: true,
        stroked: true,
        filled: true,
        radiusUnits: 'meters',
        lineWidthUnits: 'pixels',
        radiusMinPixels: 2.5,
        radiusMaxPixels: 8,
        lineWidthMinPixels: 0.5,
        getPosition: (d) => [d.lon, d.lat, 0],
        getRadius: (d) => bandRadius(d.band, d.risk_score),
        getFillColor: (d) => bandColor(d.band),
        getLineColor: (d) => {
          const [r, g, b] = bandColor(d.band);
          return [r, g, b, 255];
        },
        onClick: (info: PickingInfo) => {
          const cb = onCellClickRef.current;
          if (info.object && cb) cb(info.object as V17Cell);
        },
        updateTriggers: {
          getFillColor: cells.length,
          getRadius: cells.length,
        },
        ...terrainProps,
      }),
    [cells, terrainProps],
  );

  const viirsLayer = useMemo(
    () =>
      new ScatterplotLayer<ViirsFire>({
        id: 'viirs-fires',
        data: viirs,
        pickable: false,
        stroked: true,
        filled: true,
        radiusUnits: 'meters',
        radiusMinPixels: 2,
        radiusMaxPixels: 5,
        getPosition: (d) => [d.lon, d.lat, 0],
        getRadius: 900,
        getFillColor: [34, 197, 94, 210],
        getLineColor: [34, 197, 94, 255],
        lineWidthMinPixels: 0.5,
        ...terrainProps,
      }),
    [viirs, terrainProps],
  );

  // Final layer order (bottom → top):
  //   1. fuel-load heatmap        (where biomass is — STATIC backdrop)
  //   2. burn-density heatmap     (Mitigation 2 — base context)
  //   3. blind-spot rings         (Mitigation 2 — diff)
  //   4. prior-watch hollow rings (Mitigation 3 — climatology priors)
  //   5. beats polygons           (granular forest-beat outlines)
  //   6. divisions polygons       (87 division-level outlines, bolder)
  //   7. critical pulse           (animation under markers)
  //   8. v17 ignition cells       (clickable, top-of-content)
  //   9. VIIRS confirmed fires    (ground truth)
  //  10. burn-prediction polygons (per-click focus, TOP of all)
  const layers: Layer[] = useMemo(
    () =>
      [
        fuelLoadLayer,
        burnDensityLayer,
        blindSpotLayer,
        priorWatchLayer,
        beatsLayer,
        divisionsLayer,
        pulseLayer,
        ignitionLayer,
        viirsLayer,
        ...burnPredLayers,
      ].filter((l): l is Layer => Boolean(l)),
    [
      fuelLoadLayer,
      burnDensityLayer,
      blindSpotLayer,
      priorWatchLayer,
      beatsLayer,
      divisionsLayer,
      pulseLayer,
      ignitionLayer,
      viirsLayer,
      burnPredLayers,
    ],
  );

  // Mount MapLibre + Deck once
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      // Allow pitch up to 75° so 3D terrain mode can tilt the camera.
      // Default would cap at 60° which is fine, but explicit is safer.
      maxPitch: 75,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.once('load', () => {
      // Guard: component may have unmounted between `new Map` and 'load'.
      if (!containerRef.current) return;
      // Create an overlay canvas inside the map container for deck.gl
      const overlay = document.createElement('canvas');
      overlay.style.position = 'absolute';
      overlay.style.top = '0';
      overlay.style.left = '0';
      overlay.style.width = '100%';
      overlay.style.height = '100%';
      overlay.style.pointerEvents = 'none';
      containerRef.current.appendChild(overlay);
      overlayCanvasRef.current = overlay;

      const deck = new Deck({
        canvas: overlay,
        initialViewState: INITIAL_VIEW,
        controller: false,
        layers,
        // Forward picking events back through MapLibre's canvas
        getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab'),
      });
      deckRef.current = deck;

      // Keep deck.gl view synced to MapLibre
      const syncDeck = () => {
        const { lng, lat } = map.getCenter();
        deck.setProps({
          viewState: {
            longitude: lng,
            latitude: lat,
            zoom: map.getZoom(),
            pitch: map.getPitch(),
            bearing: map.getBearing(),
          },
        });
      };
      map.on('move', syncDeck);
      syncDeck();

      // Route clicks through MapLibre to deck.gl for picking. Dereferencing
      // the ref each fire keeps the handler in sync with re-renders that
      // change onCellClick.
      map.on('click', (e) => {
        const picked = deck.pickObject({
          x: e.point.x,
          y: e.point.y,
          radius: 8,
        });
        const cb = onCellClickRef.current;
        if (picked?.object && cb) {
          cb(picked.object as V17Cell);
        }
      });
    });

    return () => {
      deckRef.current?.finalize();
      // Unconditionally remove the overlay canvas — the 'load' event may
      // never have fired (CRIT #2: leak if component unmounts during load).
      const overlay = overlayCanvasRef.current;
      if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      overlayCanvasRef.current = null;
      mapRef.current?.remove();
      deckRef.current = null;
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push new layer data when `layers` changes
  useEffect(() => {
    if (deckRef.current) deckRef.current.setProps({ layers });
  }, [layers]);

  // 3D terrain side effect — attach AWS Terrain Tiles + animate pitch when
  // terrain3D flips on; tear down when it flips off. See
  // docs/3d_terrain_analysis.md for the picked path + future upgrade plan.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const onLoad = () => {
      try {
        if (terrain3D) {
          if (!map.getSource('aws-terrain')) {
            map.addSource('aws-terrain', {
              type: 'raster-dem',
              tiles: [
                'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
              ],
              encoding: 'terrarium',
              tileSize: 256,
              maxzoom: 14,
              attribution:
                '<a href="https://registry.opendata.aws/terrain-tiles/">AWS Terrain</a>',
            });
          }
          // Hillshade: actually paints the elevation gradient onto the mesh.
          // Without it, setTerrain only deforms geometry — invisible against
          // a dark vector basemap. Insert below the first symbol layer so
          // city labels stay legible on top.
          if (!map.getLayer('aws-hillshade')) {
            const layers = map.getStyle().layers ?? [];
            const firstSymbol = layers.find(
              (l: { type?: string; id: string }) => l.type === 'symbol',
            );
            map.addLayer(
              {
                id: 'aws-hillshade',
                type: 'hillshade',
                source: 'aws-terrain',
                paint: {
                  'hillshade-exaggeration': 0.7,
                  'hillshade-shadow-color': '#0a0e18',
                  'hillshade-highlight-color': '#7a8fa8',
                  'hillshade-accent-color': '#3b5878',
                  'hillshade-illumination-direction': 315,
                },
              },
              firstSymbol?.id,
            );
          }
          // Atmospheric sky for horizon depth at high pitch.
          try {
            (map as unknown as {
              setSky?: (s: Record<string, unknown>) => void;
            }).setSky?.({
              'sky-color': '#0b1220',
              'sky-horizon-blend': 0.6,
              'horizon-color': '#1a2d4a',
              'horizon-fog-blend': 0.5,
              'fog-color': '#0b1220',
              'fog-ground-blend': 0.85,
            });
          } catch {
            /* setSky only on MapLibre 5+; non-fatal */
          }
          map.setTerrain({
            source: 'aws-terrain',
            exaggeration: terrainExaggeration,
          });
          map.dragRotate.enable();
          map.touchZoomRotate.enableRotation();
          // Snap pitch + zoom in one step so the change reads obviously.
          map.setPitch(45);
          map.easeTo({ pitch: 65, zoom: Math.max(map.getZoom(), 7), duration: 900 });
          // eslint-disable-next-line no-console
          console.info('[FireMap] 3D enabled — pitch 65°, exag', terrainExaggeration);
        } else {
          if (map.getLayer('aws-hillshade')) map.removeLayer('aws-hillshade');
          map.setTerrain(null);
          map.easeTo({ pitch: 0, bearing: 0, duration: 600 });
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[FireMap] 3D terrain toggle failed:', err);
      }
    };
    if (map.isStyleLoaded()) onLoad();
    else map.once('load', onLoad);
  }, [terrain3D, terrainExaggeration]);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'absolute',
        inset: 0,
        background: colors.bg.canvas,
      }}
      aria-label="Madhya Pradesh forest fire risk map"
    />
  );
}
