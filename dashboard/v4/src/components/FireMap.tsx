// FireMap — MapLibre basemap (dark) + deck.gl layers for v17 ignition cells and
// FIRMS VIIRS fires. Uses WebGL2 via deck.gl for fast rendering of 2k+ cells.

import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Deck } from 'deck.gl';
import { ScatterplotLayer, GeoJsonLayer } from '@deck.gl/layers';
// `_TerrainExtension` is the deck.gl 9 export name (underscore-prefixed
// to signal experimental status). Aliased for clarity.
import { _TerrainExtension as TerrainExtension } from '@deck.gl/extensions';
import type { PickingInfo, Layer } from '@deck.gl/core';

// Single shared TerrainExtension instance so deck.gl's prop-diff cache
// recognizes "same extension" across re-renders and doesn't churn shaders.
// Setting `terrainDrawMode: 'drape'` per-layer below tells deck.gl to
// project that layer onto the active terrain mesh from MapLibre.
const TERRAIN_EXT = new TerrainExtension();
import { colors } from '../designTokens';
import type { V17Cell, ViirsFire, GeoJSONFeatureCollection } from '../lib/api';
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
  /** Toggle 3D terrain. When true, attaches AWS Terrain Tiles as a raster-DEM
   *  source and animates pitch to 60°. See docs/3d_terrain_analysis.md. */
  terrain3D?: boolean;
  /** Vertical exaggeration multiplier for 3D terrain (default 1.5). */
  terrainExaggeration?: number;
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
  terrain3D = false,
  terrainExaggeration = 1.5,
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
        extensions: [TERRAIN_EXT],
        terrainDrawMode: 'drape',
      }),
    [criticalCells, pulse],
  );

  const dataLayers: Layer[] = useMemo(
    () => [
      // Beats polygon overlay (rendered UNDER the scatter so markers stay on top).
      // Original 8,973 MP forest-beat MultiPolygons. Render with soft fill +
      // anti-aliased thin stroke to avoid the "sharp edges" look officers
      // flagged on the dissolved divisions.
      ...(beats
        ? [
            new GeoJsonLayer({
              id: 'beats-boundary',
              data: beats as unknown as GeoJSON.FeatureCollection,
              pickable: false,
              stroked: true,
              filled: true,
              lineWidthUnits: 'pixels',
              lineWidthMinPixels: 0.4,
              lineWidthMaxPixels: 0.9,
              // Soft slate fill + thin teal stroke for forest feel
              getFillColor: [129, 201, 149, 8],   // green @ ~3% (forest)
              getLineColor: [129, 201, 149, 80],  // green @ 31% — visible but soft
              getLineWidth: 0.6,
              parameters: {
                blend: true,
                blendFunc: [770, 771],  // SRC_ALPHA, ONE_MINUS_SRC_ALPHA
              },
              // Drape this polygon layer onto the 3D terrain mesh so beat
              // boundaries follow ridges/valleys instead of floating at z=0.
              extensions: [TERRAIN_EXT],
              terrainDrawMode: 'drape',
            }),
          ]
        : []),
      // v17 ignition cells — scatterplot circles
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
        extensions: [TERRAIN_EXT],
        terrainDrawMode: 'drape',
      }),

      // FIRMS VIIRS fires — smaller, confirmed green circles
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
        extensions: [TERRAIN_EXT],
        terrainDrawMode: 'drape',
      }),
    ],
    [cells, viirs, beats],
  );

  // Final layer list inserts the pulse layer just after beats so it sits
  // under the ignition scatter (so markers remain the hit target).
  const layers: Layer[] = useMemo(
    () => [dataLayers[0], pulseLayer, ...dataLayers.slice(1)].filter(
      (l): l is Layer => Boolean(l),
    ),
    [dataLayers, pulseLayer],
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
