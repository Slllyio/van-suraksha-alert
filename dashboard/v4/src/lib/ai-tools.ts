// AI tool implementations — called by AIBriefDrawer to supply context to the LLM.
// Each function hits an existing /api/v2/* endpoint and returns a compact summary
// string suitable for inline injection into a chat message.

import { api } from './api';

/** Top-N divisions by CRITICAL alert count, with key risk signals. */
export async function getDivisionOverview(topN = 10): Promise<string> {
  const divisions = await api.divisionOverview();
  const top = divisions
    .filter((d) => d.critical > 0 || d.alert > 0)
    .sort((a, b) => b.critical - a.critical || b.alert - a.alert)
    .slice(0, topN);

  if (top.length === 0) return 'No active alert divisions found.';

  const silent = divisions.filter((d) => d.silent_in_danger);

  const lines = top.map(
    (d) =>
      `${d.name}: ${d.critical} CRITICAL / ${d.alert} ALERT / ${d.watch} WATCH` +
      ` | confidence=${d.confidence}` +
      ` | hawkes_high=${d.hawkes_high_pct}%` +
      (d.silent_in_danger ? ' [SILENT-IN-DANGER]' : ''),
  );

  const silentNote =
    silent.length > 0
      ? `\nSilent-in-danger divisions (floor-promoted): ${silent.map((d) => d.name).join(', ')}`
      : '';

  return lines.join('\n') + silentNote;
}

/** CRITICAL-band cells: top 20 by risk score, with coordinates and Hawkes λ. */
export async function getCriticalCells(): Promise<string> {
  const env = await api.ignitionV17(undefined, { limit: 2000 });
  const cells = env.data.filter((c) => c.band === 'CRITICAL');

  if (cells.length === 0) return 'No CRITICAL cells today.';

  const top20 = cells
    .sort((a, b) => {
      const ra = a.risk_score ?? a.calibrated_risk ?? a.ignition_risk ?? 0;
      const rb = b.risk_score ?? b.calibrated_risk ?? b.ignition_risk ?? 0;
      return rb - ra;
    })
    .slice(0, 20);

  const lines = top20.map((c) => {
    const risk = (c.risk_score ?? c.calibrated_risk ?? c.ignition_risk ?? 0) as number;
    const lambda = typeof c.hawkes_lambda === 'number' ? c.hawkes_lambda.toFixed(4) : 'n/a';
    return (
      `cell ${c.cell_id} (${c.division ?? '?'}) ` +
      `lat=${c.lat.toFixed(3)} lon=${c.lon.toFixed(3)} ` +
      `risk=${risk.toFixed(3)} hawkes_lambda=${lambda}`
    );
  });

  return `Top ${top20.length} CRITICAL cells (of ${cells.length} total):\n${lines.join('\n')}`;
}

/** Recent VIIRS fire detections in a division over the last N days. */
export async function getRecentFires(division: string, days = 7): Promise<string> {
  const today = new Date();
  const from = new Date(today.getTime() - days * 86_400_000)
    .toISOString()
    .slice(0, 10);
  const to = today.toISOString().slice(0, 10);

  const env = await api.viirsFires(from, to);
  const fires = env.data.filter(
    (f) =>
      !division ||
      (f.division ?? '').toLowerCase().includes(division.toLowerCase()),
  );

  if (fires.length === 0) {
    return `No VIIRS fire detections in ${division} over the past ${days} days.`;
  }

  const byDate: Record<string, number> = {};
  for (const f of fires) {
    byDate[f.date] = (byDate[f.date] ?? 0) + 1;
  }
  const summary = Object.entries(byDate)
    .sort(([a], [b]) => b.localeCompare(a))
    .slice(0, 7)
    .map(([d, n]) => `${d}: ${n} detections`)
    .join('\n');

  return (
    `VIIRS detections in ${division} (past ${days}d): ${fires.length} total\n${summary}`
  );
}

// ---- Tool name → function dispatch (used by the backend stub path in the client) ----

export type ToolName = 'getDivisionOverview' | 'getCriticalCells' | 'getRecentFires';

export async function callTool(
  name: ToolName,
  args: Record<string, unknown>,
): Promise<string> {
  switch (name) {
    case 'getDivisionOverview':
      return getDivisionOverview((args.topN as number) ?? 10);
    case 'getCriticalCells':
      return getCriticalCells();
    case 'getRecentFires':
      return getRecentFires(
        (args.division as string) ?? '',
        (args.days as number) ?? 7,
      );
    default:
      return `Unknown tool: ${name as string}`;
  }
}
