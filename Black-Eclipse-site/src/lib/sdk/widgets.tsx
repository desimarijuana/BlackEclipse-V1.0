'use client';

// ── SDK widgets — declarative, user-created widget definitions ───────────────
// A user widget is DATA: a closed primitive (`data-table`, `metric-card`, …)
// plus an allow-listed source and config. The host turns each record into a
// real WidgetDefinition whose renderer delegates to the existing generic
// widgets — no user code is executed, and a missing source still renders the
// honest UNAVAILABLE state from the data-source resolver.
//
// The Python runtime stores the definition and registers the component id
// (`sdk.<slug>`) in the UI catalog. This module is the host-side mirror that
// `renderDashboardWidget` and the Pages/Widget Library consume.

import React, { useEffect, useState } from 'react';
import type { WidgetDefinition, WidgetCategory } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';
import { WIDGET_CATEGORY_LABEL } from '@/lib/workspace/widget-def';
import { DataTableWidget, MetricCardWidget } from '@/lib/workspace/generic-widgets';
import { LineChartWidget, AreaChartWidget, BarChartWidget, PieChartWidget } from '@/lib/workspace/generic-charts';
import {
  ListWidget,
  MarkdownWidget,
  StatusIndicatorWidget,
  EmptyStateWidget,
  ErrorStateWidget,
} from '@/lib/workspace/generic-content';
import { ClockWidget } from '@/lib/dashboard/clock-widget';
import { registerWidget, unregisterWidget } from '@/lib/workspace/widget-registry';
import { eclipseSdk, type SdkWidgetPrimitive, type SdkWidgetRecord } from '@/lib/sdk';

export const SDK_WIDGET_PREFIX = 'sdk.';

type Listener = () => void;

const widgets = new Map<string, SdkWidgetRecord>();
const registered = new Set<string>();
const listeners = new Set<Listener>();
let hydratePromise: Promise<void> | null = null;

function notify() {
  for (const listener of listeners) listener();
}

function safeCategory(value: string): WidgetCategory {
  return (Object.prototype.hasOwnProperty.call(WIDGET_CATEGORY_LABEL, value) ? value : 'tools') as WidgetCategory;
}

function safeSizes(value: string[]): WidgetDefinition['sizes'] {
  const allowed = new Set(['small', 'medium', 'large', 'full']);
  const out = value.filter((size): size is WidgetDefinition['sizes'][number] => allowed.has(size));
  return out.length ? out : ['medium', 'large'];
}

function safeSurface(value: string | undefined): 'dashboard' | 'page' | 'both' {
  return value === 'dashboard' || value === 'page' ? value : 'both';
}

function defaultHeightFor(primitive: SdkWidgetPrimitive): number | undefined {
  if (primitive === 'metric-card' || primitive === 'status-indicator') return 140;
  if (primitive === 'clock') return 180;
  if (primitive === 'markdown' || primitive === 'empty-state' || primitive === 'error-state') return undefined;
  return 320;
}

function renderPrimitive(primitive: SdkWidgetPrimitive, placement: WidgetPlacement): React.ReactNode {
  switch (primitive) {
    case 'data-table': return <DataTableWidget placement={placement} />;
    case 'metric-card': return <MetricCardWidget placement={placement} />;
    case 'line-chart': return <LineChartWidget placement={placement} />;
    case 'area-chart': return <AreaChartWidget placement={placement} />;
    case 'bar-chart': return <BarChartWidget placement={placement} />;
    case 'pie-chart': return <PieChartWidget placement={placement} />;
    case 'list': return <ListWidget placement={placement} />;
    case 'markdown': return <MarkdownWidget placement={placement} />;
    case 'status-indicator': return <StatusIndicatorWidget placement={placement} />;
    case 'empty-state': return <EmptyStateWidget placement={placement} />;
    case 'error-state': return <ErrorStateWidget placement={placement} />;
    case 'clock': return <ClockWidget placement={placement} />;
    default:
      return (
        <div className="flex h-full items-center justify-center p-4 text-center text-xs italic text-amber-400/80">
          UNAVAILABLE — unknown SDK widget primitive.
        </div>
      );
  }
}

/** Convert one runtime record into the host's WidgetDefinition contract. */
export function sdkWidgetToDefinition(record: SdkWidgetRecord): WidgetDefinition {
  const primitive = record.primitive;
  const defaults: Record<string, unknown> = { ...record.config, title: record.label };
  if (record.source) defaults.source = record.source;
  return {
    id: record.componentId,
    category: safeCategory(record.category),
    label: record.label,
    desc: record.description || `User widget · ${primitive}`,
    icon: record.icon || 'dashboard',
    surface: safeSurface(record.surface),
    sizes: safeSizes(record.sizes),
    defaultHeight: defaultHeightFor(primitive),
    defaultConfig: defaults,
    catalogDataSources: record.source ? [record.source] : ['any'],
    configFields: [
      ...(record.source ? [{ key: 'source', label: 'Data source', type: 'text' as const, placeholder: record.source }] : []),
      ...(primitive === 'clock'
        ? [
            { key: 'timezone', label: 'Timezone', type: 'text' as const, placeholder: 'UTC, Europe/London, America/New_York…' },
            { key: 'format', label: 'Format', type: 'select' as const, options: [{ value: '24h', label: '24-hour' }, { value: '12h', label: '12-hour' }] },
            { key: 'showSeconds', label: 'Show seconds', type: 'boolean' as const },
            { key: 'showDate', label: 'Show date', type: 'boolean' as const },
          ]
        : []),
      { key: 'title', label: 'Title', type: 'text' as const, placeholder: record.label },
    ],
    render: (placement) => renderPrimitive(primitive, {
      ...placement,
      config: { ...defaults, ...(placement.config ?? {}) },
    }),
  };
}

export function listSdkWidgetRecords(): SdkWidgetRecord[] {
  return [...widgets.values()];
}

export function listSdkWidgetDefinitions(): WidgetDefinition[] {
  return listSdkWidgetRecords().map(sdkWidgetToDefinition);
}

export function getSdkWidgetDefinition(componentId: string): WidgetDefinition | undefined {
  const record = widgets.get(componentId);
  return record ? sdkWidgetToDefinition(record) : undefined;
}

export function subscribeSdkWidgets(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Pull the runtime's widget definitions into this browser tab. Idempotent. */
export function hydrateSdkWidgets(force = false): Promise<void> {
  if (hydratePromise && !force) return hydratePromise;
  hydratePromise = (async () => {
    try {
      const { widgets: records } = await eclipseSdk.widgets.list();
      widgets.clear();
      const next = new Set<string>();
      for (const record of records) {
        widgets.set(record.componentId, record);
        next.add(record.componentId);
        registerWidget(sdkWidgetToDefinition(record), { replace: true });
      }
      for (const componentId of [...registered]) {
        if (!next.has(componentId)) unregisterWidget(componentId);
      }
      registered.clear();
      for (const componentId of next) registered.add(componentId);
      notify();
    } catch {
      /* runtime unavailable — keep whatever is cached */
    }
  })();
  return hydratePromise;
}

/** Re-fetch after a create/delete so the library and pages update immediately. */
export function refreshSdkWidgets(): Promise<void> {
  return hydrateSdkWidgets(true);
}

/** Live list for React surfaces (Widget Library on a page, SDK screen). */
export function useSdkWidgets(): SdkWidgetRecord[] {
  const [records, setRecords] = useState<SdkWidgetRecord[]>(() => listSdkWidgetRecords());
  useEffect(() => {
    let cancelled = false;
    const update = () => { if (!cancelled) setRecords(listSdkWidgetRecords()); };
    const unsubscribe = subscribeSdkWidgets(update);
    void hydrateSdkWidgets().then(update);
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);
  return records;
}

export function useSdkWidgetDefinitions(): WidgetDefinition[] {
  const records = useSdkWidgets();
  return records.map(sdkWidgetToDefinition);
}
