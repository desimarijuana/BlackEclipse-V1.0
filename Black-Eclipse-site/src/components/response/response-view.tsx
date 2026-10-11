'use client';

// ── ResponseView — the Universal Response Renderer ────────────────────────────
//
// A small, explicit REGISTRY (block type → component) rather than a growing
// conditional chain. Unknown types never reach a renderer: the contract parser
// tags them `unknown` and they degrade to a readable diagnostic card.
//
// Every block is wrapped in `BlockBoundary`, so a render failure in one block
// (e.g. a chart) cannot destroy the surrounding answer — error isolation is the
// whole point of rendering blocks independently.

import React, { type ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { AlertTriangle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { ParsedResponse, ValidatedBlock } from '@/lib/response/contract';
import {
  CalloutBlock,
  CitationsBlock,
  DetailsBlock,
  DiagnosticsPanel,
  HeadingBlock,
  KeyValueBlock,
  MarkdownBlock,
  MetricGridBlock,
  ResponseHeader,
  TabsBlock,
  TimelineBlock,
  UnknownBlockCard,
} from './blocks';
import { DataTableBlock } from './data-table-block';
import { DiagramBlock } from './diagram-block';
import { ControlsBlock } from './controls-block';
import { ResponseActions } from './response-actions';

// ECharts is ~1MB; only fetched when a chart block actually renders.
const ResponseChart = dynamic(() => import('./response-chart'), {
  ssr: false,
  loading: () => <BlockSkeleton height={260} />,
});

// Mermaid and the financial chart provider stack are both heavy; lazy-loaded.
const MermaidBlock = dynamic(() => import('./mermaid-block'), {
  ssr: false,
  loading: () => <BlockSkeleton height={220} />,
});

const ResponseFinancialChart = dynamic(() => import('./financial-chart'), {
  ssr: false,
  loading: () => <BlockSkeleton height={440} />,
});

function BlockSkeleton({ height }: { height: number }) {
  return (
    <div className="flex items-center justify-center rounded-xl border border-white/10 bg-accent/10" style={{ height }}>
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
    </div>
  );
}

export interface RenderContext {
  compact?: boolean;
  renderBlocks: (blocks: ValidatedBlock[]) => ReactNode;
  onFollowup?: (prompt: string) => void;
}

type BlockOf<T extends ValidatedBlock['type']> = Extract<ValidatedBlock, { type: T }>;

/**
 * The registry. Adding a block type means adding its schema to the contract and
 * one entry here — no change to the chat renderer.
 */
const REGISTRY = {
  markdown: (b: BlockOf<'markdown'>, ctx: RenderContext) => <MarkdownBlock markdown={b.markdown} compact={ctx.compact} />,
  heading: (b: BlockOf<'heading'>, ctx: RenderContext) => <HeadingBlock text={b.text} level={b.level} compact={ctx.compact} />,
  callout: (b: BlockOf<'callout'>, ctx: RenderContext) => (
    <CalloutBlock tone={b.tone} title={b.title} markdown={b.markdown} compact={ctx.compact} />
  ),
  key_value: (b: BlockOf<'key_value'>) => <KeyValueBlock title={b.title} items={b.items} />,
  details: (b: BlockOf<'details'>, ctx: RenderContext) => (
    <DetailsBlock summary={b.summary} markdown={b.markdown} open={b.open} compact={ctx.compact} />
  ),
  metric_grid: (b: BlockOf<'metric_grid'>) => (
    <MetricGridBlock title={b.title} source={b.source} asOf={b.asOf} columns={b.columns} metrics={b.metrics} />
  ),
  data_table: (b: BlockOf<'data_table'>, ctx: RenderContext) => (
    <DataTableBlock
      title={b.title}
      caption={b.caption}
      source={b.source}
      asOf={b.asOf}
      columns={b.columns}
      rows={b.rows}
      filterable={b.filterable}
      sortable={b.sortable}
      pageSize={b.pageSize}
      compact={ctx.compact}
    />
  ),
  chart: (b: BlockOf<'chart'>) => (
    <div className="w-full">
      {b.title && <h4 className="mb-1.5 text-sm font-semibold text-foreground">{b.title}</h4>}
      <ResponseChart block={b} />
      {(b.source || b.asOf || b.description) && (
        <p className="mt-1 text-[10px] text-muted-foreground/60">
          {b.description}
          {b.description && (b.source || b.asOf) ? ' · ' : ''}
          {b.source}
          {b.source && b.asOf ? ' · ' : ''}
          {b.asOf}
        </p>
      )}
    </div>
  ),
  diagram: (b: BlockOf<'diagram'>) => <DiagramBlock block={b} />,
  mermaid: (b: BlockOf<'mermaid'>) => <MermaidBlock diagram={b.diagram} title={b.title} description={b.description} />,
  financial_chart: (b: BlockOf<'financial_chart'>) => (
    <div className="w-full">
      {b.title && <h4 className="mb-1.5 text-sm font-semibold text-foreground">{b.title}</h4>}
      <ResponseFinancialChart block={b} />
      {(b.source || b.asOf) && (
        <p className="mt-1 font-mono text-[10px] text-muted-foreground/60">
          {b.source}
          {b.source && b.asOf ? ' · ' : ''}
          {b.asOf}
        </p>
      )}
    </div>
  ),
  timeline: (b: BlockOf<'timeline'>) => <TimelineBlock title={b.title} events={b.events} />,
  citations: (b: BlockOf<'citations'>) => <CitationsBlock title={b.title} sources={b.sources} />,
  tabs: (b: BlockOf<'tabs'>, ctx: RenderContext) => (
    <TabsBlock tabs={b.tabs as { label: string; blocks: ValidatedBlock[] }[]} renderBlocks={ctx.renderBlocks} />
  ),
  controls: (b: BlockOf<'controls'>, ctx: RenderContext) => <ControlsBlock block={b} onFollowup={ctx.onFollowup} />,
} as const;

type RegistryKey = keyof typeof REGISTRY;

function isRegistered(type: string): type is RegistryKey {
  return type in REGISTRY;
}

interface BoundaryProps {
  blockType: string;
  children: ReactNode;
}

class BlockBoundary extends React.Component<BoundaryProps, { error: string | null }> {
  constructor(props: BoundaryProps) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error: error.message || 'Block failed to render' };
  }
  componentDidCatch(error: Error) {
    console.error('[ResponseBlock]', this.props.blockType, error);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/[0.06] px-3 py-2 text-[12px] text-rose-200/90">
          <div className="flex items-center gap-1.5">
            <AlertTriangle size={13} />
            <span>
              Could not render this <code className="font-mono">{this.props.blockType}</code> block.
            </span>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function renderBlock(block: ValidatedBlock, ctx: RenderContext, index: number): ReactNode {
  if (block.type === 'unknown') {
    return (
      <BlockBoundary blockType={block.declaredType} key={index}>
        <UnknownBlockCard block={block} />
      </BlockBoundary>
    );
  }
  const renderer = REGISTRY[block.type as RegistryKey] as ((b: ValidatedBlock, c: RenderContext) => ReactNode) | undefined;
  if (!renderer || !isRegistered(block.type)) {
    return (
      <BlockBoundary blockType={block.type} key={index}>
        <UnknownBlockCard block={{ type: 'unknown', declaredType: block.type, raw: block }} />
      </BlockBoundary>
    );
  }
  return (
    <BlockBoundary blockType={block.type} key={index}>
      {renderer(block, ctx)}
    </BlockBoundary>
  );
}

export interface ResponseViewProps {
  response: ParsedResponse;
  compact?: boolean;
  className?: string;
  /** Called when a controls block submits — re-enters the chat's agent loop. */
  onFollowup?: (prompt: string) => void;
}

export function ResponseView({ response, compact = false, className, onFollowup }: ResponseViewProps) {
  const renderBlocks = (blocks: ValidatedBlock[]): ReactNode => (
    <div className="space-y-3">
      {blocks.map((block, i) => renderBlock(block, { compact, renderBlocks, onFollowup }, i))}
    </div>
  );

  if (response.blocks.length === 0) {
    return (
      <div className={cn('w-full', className)}>
        <DiagnosticsPanel diagnostics={response.diagnostics} />
      </div>
    );
  }

  return (
    <section className={cn('w-full', className)} aria-label="Structured response">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <ResponseHeader response={response} />
        <ResponseActions response={response} />
      </div>
      <div className={cn('space-y-4', compact && 'space-y-3')}>
        {response.blocks.map((b, i) => renderBlock(b, { compact, renderBlocks, onFollowup }, i))}
      </div>
      <div className="mt-2">
        <DiagnosticsPanel diagnostics={response.diagnostics} />
      </div>
    </section>
  );
}

export default ResponseView;
