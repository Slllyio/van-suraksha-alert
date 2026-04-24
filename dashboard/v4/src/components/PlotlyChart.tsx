// Thin wrapper around react-plotly.js to apply dark-mode defaults and the
// fire-EWS color palette. We use plotly.js-dist-min via the factory so we
// avoid pulling the full 3 MB plotly.js bundle.

import PlotDefault from 'react-plotly.js';
import type { PlotParams } from 'react-plotly.js';
import type { Layout, Config } from 'plotly.js';
import { colors, chartColors, fontFamily } from '../designTokens';

// Vite's CJS-interop for react-plotly.js ships the module's `exports` object
// (with `__esModule: true` and `default: <Component>`) as the default import.
// Unwrap: if it's already a component, use it; otherwise reach into `.default`.
const Plot = (typeof PlotDefault === 'function'
  ? PlotDefault
  : (PlotDefault as unknown as { default: React.ComponentType<PlotParams> }).default
) as React.ComponentType<PlotParams>;

export type PlotlyChartProps = Omit<PlotParams, 'layout' | 'config'> & {
  /** Height in px. Width always stretches to parent. */
  height?: number;
  layout?: Partial<Layout>;
  config?: Partial<Config>;
};

const DEFAULT_LAYOUT: Partial<Layout> = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: {
    family: fontFamily.ui,
    color: colors.text.secondary,
    size: 12,
  },
  margin: { l: 56, r: 16, t: 24, b: 44 },
  xaxis: {
    gridcolor: chartColors.grid,
    zerolinecolor: chartColors.grid,
    linecolor: chartColors.axis,
    tickcolor: chartColors.axis,
    tickfont: { family: fontFamily.mono, size: 11, color: colors.text.tertiary },
  },
  yaxis: {
    gridcolor: chartColors.grid,
    zerolinecolor: chartColors.grid,
    linecolor: chartColors.axis,
    tickcolor: chartColors.axis,
    tickfont: { family: fontFamily.mono, size: 11, color: colors.text.tertiary },
  },
  legend: {
    bgcolor: 'rgba(30, 41, 59, 0.7)',
    bordercolor: colors.border.subtle,
    borderwidth: 1,
    font: { size: 11, color: colors.text.secondary },
  },
  hoverlabel: {
    bgcolor: colors.bg.overlay,
    bordercolor: colors.border.base,
    font: { family: fontFamily.mono, size: 12, color: colors.text.primary },
  },
};

const DEFAULT_CONFIG: Partial<Config> = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: [
    'lasso2d',
    'select2d',
    'autoScale2d',
    'toggleSpikelines',
  ],
  toImageButtonOptions: {
    format: 'png',
    filename: 'jwalanetra-chart',
    scale: 2,
  },
};

export default function PlotlyChart({
  height = 320,
  layout,
  config,
  style,
  ...rest
}: PlotlyChartProps) {
  const animatedLayout: Partial<Layout> = {
    ...DEFAULT_LAYOUT,
    ...layout,
    transition: { duration: 700, easing: 'cubic-in-out' },
  };
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height,
        overflow: 'hidden',
        animation: 'plotlyReveal 900ms cubic-bezier(0.22, 1, 0.36, 1) both',
      }}
    >
      <style>{plotlyRevealKeyframes}</style>
      <Plot
        {...rest}
        layout={animatedLayout}
        config={{ ...DEFAULT_CONFIG, ...config }}
        style={{ width: '100%', height, ...style }}
        useResizeHandler
      />
    </div>
  );
}

const plotlyRevealKeyframes = `
@keyframes plotlyReveal {
  0%   { clip-path: inset(0 100% 0 0); opacity: 0.4; }
  50%  { opacity: 1; }
  100% { clip-path: inset(0 0 0 0);    opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  @keyframes plotlyReveal {
    from { opacity: 0.6; }
    to   { opacity: 1; }
  }
}
`;
