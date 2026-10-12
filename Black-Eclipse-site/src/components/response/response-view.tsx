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
import { NodeGraphBlock } from './node-graph-block';
import { MermaidBlock } from './mermaid-block';
import { ActionGroupBlock, ArtifactBlock, InfographicBlock, ReportBlock, StepperBlock, WorkflowBlock } from './rich-blocks';
import { ResponseActions } from './response-actions';

// ECharts is ~1MB; only fetched when a chart block actually renders.
const ResponseChart = dynamic(() => import('./response-chart'), {
  ssr: false,
  loading: () => <BlockSkeleton height={260} />,
});

// `mermaid-block` lazy-imports the heavy `mermaid` package inside its own effect,
// so the component itself is tiny and is imported statically. Wrapping it in its
// own `next/dynamic` added a redundant chunk-load failure path that surfaced a
// scary render error (via `BlockBoundary`) instead of the block's inline
// "Diagram could not be rendered" card.

const ResponseFinancialChart = dynamic(() => import('./financial-chart'), {
  ssr: false,
  loading: () => <BlockSkeleton height={440} />,
});

function BlockSkeleton({ height }: { height: number }) {
  return (
    <div className="glass-card-subtle flex items-center justify-center rounded-xl" style={{ height }}>
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
  stepper: (b: BlockOf<'stepper'>) => <StepperBlock block={b} />,
  infographic: (b: BlockOf<'infographic'>) => <InfographicBlock block={b} />,
  workflow: (b: BlockOf<'workflow'>, ctx: RenderContext) => <WorkflowBlock block={b} onFollowup={ctx.onFollowup} />,
  report: (b: BlockOf<'report'>, ctx: RenderContext) => <ReportBlock block={b} renderBlocks={ctx.renderBlocks} />,
  node_graph: (b: BlockOf<'node_graph'>) => <NodeGraphBlock block={b} />,
  action_group: (b: BlockOf<'action_group'>, ctx: RenderContext) => <ActionGroupBlock block={b} onFollowup={ctx.onFollowup} />,
  artifact: (b: BlockOf<'artifact'>) => <ArtifactBlock block={b} />,
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

// Blocks that read as flowing prose. Two adjacent prose blocks get a tight
// rhythm so a heading + paragraph + callout reads as one document; a visual
// "surface" block (chart, table, metric grid, diagram, …) keeps a clear gap so
// it reads as its own figure. Without this every sibling block got the same
// 16px gap and an answer of five blocks looked like five detached cards.
const PROSE_BLOCK_TYPES = new Set<ValidatedBlock['type']>([
  'markdown',
  'heading',
  'callout',
  'details',
  'key_value',
  'citations',
  'timeline',
]);

function blockGapClass(
  type: ValidatedBlock['type'],
  prev: ValidatedBlock['type'] | null,
  compact: boolean,
): string {
  if (prev === null) return 'mt-0';
  const bothProse = PROSE_BLOCK_TYPES.has(type) && PROSE_BLOCK_TYPES.has(prev);
  if (bothProse) return compact ? 'mt-2' : 'mt-2.5';
  return compact ? 'mt-3' : 'mt-4';
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
    <>
      {blocks.map((block, i) => (
        <div key={i} className={blockGapClass(block.type, i > 0 ? blocks[i - 1].type : null, compact)}>
          {renderBlock(block, { compact, renderBlocks, onFollowup }, i)}
        </div>
      ))}
    </>
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
      <div>
        {renderBlocks(response.blocks)}
      </div>
      <div className="mt-2">
        <DiagnosticsPanel diagnostics={response.diagnostics} />
      </div>
    </section>
  );
}

export default ResponseView;
