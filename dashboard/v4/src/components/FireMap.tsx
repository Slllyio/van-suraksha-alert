// FireMap — MapLibre basemap (dark) + deck.gl layers for v17 ignition cells and
// FIRMS VIIRS fires. Uses WebGL2 via deck.gl for fast rendering of 2k+ cells.

import { useEffect, useMemo, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { Deck } from 'deck.gl';
import { ScatterplotLayer } from '@deck.gl/layers';
import type { PickingInfo, Layer } from '@deck.gl/core';
import { colors } from '../designTokens';
import type { V17Cell, ViirsFire } from '../lib/api';
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
  // Base radius by band + subtle risk-score weighting
  const base = band === 'CRITICAL' ? 6000 : band === 'ALERT' ? 4500 : 3200;
  const weight = typeof risk === 'number' ? Math.max(0.7, Math.min(1.4, risk * 1.2)) : 1;
  return base * weight;
}

export default function FireMap({ cells, viirs, onCellClick }: FireMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<Deck | null>(null);

  // Build deck.gl layer list (memoized — rebuilt only when data changes)
  const layers: Layer[] = useMemo(
    () => [
      // v17 ignition cells — scatterplot circles
      new ScatterplotLayer<V17Cell>({
        id: 'ignition-cells',
        data: cells,
        pickable: true,
        stroked: true,
        filled: true,
        radiusUnits: 'meters',
        lineWidthUnits: 'pixels',
        radiusMinPixels: 4,
        radiusMaxPixels: 28,
        lineWidthMinPixels: 1,
        getPosition: (d) => [d.lon, d.lat, 0],
        getRadius: (d) => bandRadius(d.band, d.risk_score),
        getFillColor: (d) => bandColor(d.band),
        getLineColor: (d) => {
          const [r, g, b] = bandColor(d.band);
          return [r, g, b, 255];
        },
        onClick: (info: PickingInfo) => {
          if (info.object && onCellClick) onCellClick(info.object as V17Cell);
        },
        updateTriggers: {
          getFillColor: cells.length,
          getRadius: cells.length,
        },
      }),

      // FIRMS VIIRS fires — smaller, confirmed green circles
      new ScatterplotLayer<ViirsFire>({
        id: 'viirs-fires',
        data: viirs,
        pickable: false,
        stroked: true,
        filled: true,
        radiusUnits: 'meters',
        radiusMinPixels: 3,
        radiusMaxPixels: 10,
        getPosition: (d) => [d.lon, d.lat, 0],
        getRadius: 1600,
        getFillColor: [34, 197, 94, 180],
        getLineColor: [34, 197, 94, 255],
        lineWidthMinPixels: 1,
      }),
    ],
    [cells, viirs, onCellClick],
  );

  // Mount MapLibre + Deck once
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.once('load', () => {
      // Create an overlay canvas inside the map container for deck.gl
      const overlay = document.createElement('canvas');
      overlay.style.position = 'absolute';
      overlay.style.top = '0';
      overlay.style.left = '0';
      overlay.style.width = '100%';
      overlay.style.height = '100%';
      overlay.style.pointerEvents = 'none';
      containerRef.current!.appendChild(overlay);

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

      // Route clicks through MapLibre to deck.gl for picking
      map.on('click', (e) => {
        const picked = deck.pickObject({
          x: e.point.x,
          y: e.point.y,
          radius: 8,
        });
        if (picked?.object && onCellClick) {
          onCellClick(picked.object as V17Cell);
        }
      });
    });

    return () => {
      deckRef.current?.finalize();
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
