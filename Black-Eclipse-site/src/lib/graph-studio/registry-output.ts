// Output node contracts: a chart from a payload, and a notification.
//
// `output.chart` is pure and local (a ChartSpec + the plotly figure the chart
// engine draws). `output.notify` sends through the ONE channel service, so it
// declares the `network` effect and a test run can never send.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

// Mirrors `graph_runtime/output_nodes.CHART_KINDS`.
export const CHART_KINDS = ['line', 'area', 'bar', 'scatter', 'pie', 'donut'] as const;

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const OUTPUT_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'output.chart',
    version: '1.0.0',
    category: 'output',
    label: 'Chart',
    description: 'Builds a chart spec (and its figure) from a payload.',
    icon: 'chart',
    inputs: [port({ id: 'series', name: 'Series', type: 'any' })],
    outputs: [
      port({ id: 'spec', name: 'Spec', type: 'object' }),
      port({ id: 'figure', name: 'Figure', type: 'object', nullable: true }),
      port({ id: 'rendered', name: 'Rendered', type: 'boolean' }),
    ],
    configSchema: z.object({
      kind: z.enum(CHART_KINDS).default('line'),
      title: z.string().max(200).default(''),
      xLabel: z.string().max(120).default(''),
      yLabel: z.string().max(120).default(''),
      xField: z.string().max(120).default(''),
      yField: z.string().max(120).default(''),
    }),
    defaultConfig: () => ({ kind: 'line', title: '', xLabel: '', yLabel: '', xField: '', yField: '' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Accepts a chart spec, a number list, {values, categories}, {series, categories} or {rows} with X/Y fields. Plotly missing is `rendered: false` with the spec still returned — never a fake image.',
  },
  {
    type: 'output.notify',
    version: '1.0.0',
    category: 'output',
    label: 'Notify',
    description: 'Sends one message through a configured channel.',
    icon: 'globe',
    inputs: [
      port({ id: 'message', name: 'Message', type: 'string', optional: true }),
      port({ id: 'data', name: 'Data', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'delivered', name: 'Delivered', type: 'boolean' }),
      port({ id: 'detail', name: 'Detail', type: 'object' }),
    ],
    configSchema: z.object({
      channel: z.string().max(40).default(''),
      destination: z.string().max(200).default(''),
      title: z.string().max(200).default(''),
      message: z.string().max(4_000).default(''),
    }),
    defaultConfig: () => ({ channel: '', destination: '', title: '', message: '' }),
    capabilities: ['notification.send'],
    sideEffects: 'network',
    allowedModes: ALL_MODES,
    docs: 'The channel must be configured and linked in Settings. A delivery failure fails the node with the provider\'s reason. Network effect: a test run can never send.',
  },
];
