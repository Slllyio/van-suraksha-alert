// Thin wrapper around react-plotly.js to apply dark-mode defaults and the
// fire-EWS color palette. We use plotly.js-dist-min via the factory so we
// avoid pulling the full 3 MB plotly.js bundle.

import * as factoryModule from 'react-plotly.js/factory';
// @ts-expect-error — plotly.js-dist-min has no bundled types; the factory
// accepts the runtime module.
import Plotly from 'plotly.js-dist-min';
import type { PlotParams } from 'react-plotly.js';
import type { Layout, Config } from 'plotly.js';
import { colors, chartColors, fontFamily } from '../designTokens';

// The factory module is published as CommonJS; Vite wraps it inside a
// `{ default: fn }` namespace shim, but some environments expose the function
// directly. Handle both.
const createPlotlyComponent =
  (factoryModule as unknown as { default?: unknown }).default ?? factoryModule;

const Plot = (createPlotlyComponent as (p: typeof Plotly) => React.ComponentType<PlotParams>)(
  Plotly,
);

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
  return (
    <Plot
      {...rest}
      layout={{ ...DEFAULT_LAYOUT, ...layout }}
      config={{ ...DEFAULT_CONFIG, ...config }}
      style={{ width: '100%', height, ...style }}
      useResizeHandler
    />
  );
}
