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

import React, { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { AlertTriangle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { ParsedResponse, ValidatedBlock } from '@/lib/response/contract';
import { degradeUnknownBlock, finalizeParsed, reportResponseDegrade } from '@/lib/response/finalize';
import { resolveResponseFigures } from '@/lib/response/refs';
import { computeEnvelopeValues, initialEnvelopeValues } from '@/lib/response/state';
import { InputsStateProvider, useResponseRuntime, type InputsState } from './figure-context';
import { InputsBlock } from './inputs-block';
import {
  CalloutBlock,
  CitationsBlock,
  DetailsBlock,
  HeadingBlock,
  KeyValueBlock,
  MarkdownBlock,
  MetricGridBlock,
  NoticeCard,
  ResponseHeader,
  TabsBlock,
  TimelineBlock,
} from './blocks';
import { DataTableBlock } from './data-table-block';
import { DiagramBlock } from './diagram-block';
import { ControlsBlock } from './controls-block';
import { NodeGraphBlock } from './node-graph-block';
import { LearningMapBlock } from './learning-map-block';
import { MermaidBlock } from './mermaid-block';
import { FlowBlock } from './flow-block';
import { SimulationBlock } from './simulation-block';
import { AnatomyBlock } from './anatomy-block';
import { Model3dBlock } from './model3d-block';
import { InteractiveBlock } from './interactive-block';
import { DividerBlock, LayoutBlock } from './layout-block';
import { ActionGroupBlock, ArtifactBlock, InfographicBlock, ReportBlock, StepperBlock, WorkflowBlock } from './rich-blocks';
import { GalleryBlockView } from './gallery-block';
import {
  BadgeRowBlock,
  CarouselBlock,
  ComparisonGridBlock,
  GaugeBlock,
  RankedListBlock,
  StatHeroBlock,
} from './visual-blocks';
import { ResponseActions } from './response-actions';

// A chart block can be drawn by EITHER engine: the interactive ECharts chart
// (default; ~1MB, fetched only when a chart block actually renders) or the
// Python chart engine's drawn picture (ADR-050). The user picks; the toggle
// lives on the chart.
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
  flow: (b: BlockOf<'flow'>) => <FlowBlock block={b} />,
  report: (b: BlockOf<'report'>, ctx: RenderContext) => <ReportBlock block={b} renderBlocks={ctx.renderBlocks} />,
  node_graph: (b: BlockOf<'node_graph'>) => <NodeGraphBlock block={b} />,
  learning_map: (b: BlockOf<'learning_map'>, ctx: RenderContext) => (
    <LearningMapBlock block={b} onFollowup={ctx.onFollowup} />
  ),
  action_group: (b: BlockOf<'action_group'>, ctx: RenderContext) => <ActionGroupBlock block={b} onFollowup={ctx.onFollowup} />,
  artifact: (b: BlockOf<'artifact'>) => <ArtifactBlock block={b} />,
  gallery: (b: BlockOf<'gallery'>, ctx: RenderContext) => <GalleryBlockView block={b} compact={ctx.compact} />,
  stat_hero: (b: BlockOf<'stat_hero'>) => <StatHeroBlock block={b} />,
  gauge: (b: BlockOf<'gauge'>) => <GaugeBlock block={b} />,
  comparison_grid: (b: BlockOf<'comparison_grid'>) => <ComparisonGridBlock block={b} />,
  ranked_list: (b: BlockOf<'ranked_list'>) => <RankedListBlock block={b} />,
  badge_row: (b: BlockOf<'badge_row'>) => <BadgeRowBlock block={b} />,
  carousel: (b: BlockOf<'carousel'>, ctx: RenderContext) => <CarouselBlock block={b} renderBlocks={ctx.renderBlocks} />,
  simulation: (b: BlockOf<'simulation'>, ctx: RenderContext) => <SimulationBlock block={b} onFollowup={ctx.onFollowup} />,
  anatomy: (b: BlockOf<'anatomy'>) => <AnatomyBlock block={b} />,
  model3d: (b: BlockOf<'model3d'>) => <Model3dBlock block={b} />,
  interactive: (b: BlockOf<'interactive'>, ctx: RenderContext) => (
    <InteractiveBlock block={b} onFollowup={ctx.onFollowup} />
  ),
  layout: (b: BlockOf<'layout'>, ctx: RenderContext) => <LayoutBlock block={b} renderBlocks={ctx.renderBlocks} />,
  divider: (b: BlockOf<'divider'>) => <DividerBlock block={b} />,
  inputs: (b: BlockOf<'inputs'>) => <InputsBlock block={b} />,
} as const;

type RegistryKey = keyof typeof REGISTRY;

/** Every block type with a registered renderer — the CI parity check asserts this
 *  equals the contract's block types, so a validated-but-unrenderable block type
 *  cannot ship. */
export const REGISTERED_BLOCK_TYPES = Object.keys(REGISTRY) as RegistryKey[];

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
        <NoticeCard tone="danger" icon={AlertTriangle} dense>
          <p className="text-[12px] text-foreground/80">
            Could not render this{' '}
            <code className="font-mono text-[11px] text-rose-200">{this.props.blockType}</code> block.
          </p>
        </NoticeCard>
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

/**
 * A stable key for a block: its producer `id` when present, else `index:type`.
 * Stable keys matter while streaming — a block keeps its identity (and local
 * React state, e.g. a slider position) as later blocks arrive.
 */
function blockKey(block: ValidatedBlock, index: number): string {
  const id = (block as { id?: unknown }).id;
  return typeof id === 'string' && id ? id : `${index}:${block.type}`;
}

function renderBlock(block: ValidatedBlock, ctx: RenderContext, index: number): ReactNode {
  // Defensive backstop: finalization already replaces rejected blocks, so this is
  // unreachable in practice — but if an unknown block ever reaches here it is
  // shown as readable content, never an error card.
  if (block.type === 'unknown') {
    return <MarkdownBlock key={index} markdown={degradeUnknownBlock(block.raw).markdown} compact={ctx.compact} />;
  }
  const renderer = REGISTRY[block.type as RegistryKey] as ((b: ValidatedBlock, c: RenderContext) => ReactNode) | undefined;
  if (!renderer || !isRegistered(block.type)) {
    return <MarkdownBlock key={index} markdown={degradeUnknownBlock(block).markdown} compact={ctx.compact} />;
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
  /** Hide the export/save action chips (Canvas has its own header actions). */
  showActions?: boolean;
}

export function ResponseView({ response, compact = false, className, onFollowup, showActions = true }: ResponseViewProps) {
  // Figure resolution + envelope-state persistence come from the surrounding chat
  // (built from the turn's own data). Without one, a `$ref` figure renders
  // UNAVAILABLE (never the raw reference) and edits are not persisted.
  const { figureResolver, stateKey } = useResponseRuntime();
  // THE CHOKEPOINT: every response rendered here is finalized first, so a
  // rejected block becomes readable content and no error diagnostic survives to
  // reach the UI. Failures are measured (telemetry), never shown as an error.
  const finalized = useMemo(() => {
    const result = finalizeParsed(response);
    reportResponseDegrade(result.degraded);
    return result.response;
  }, [response]);

  // Envelope shared state: the user's overrides, persisted per `stateKey` so an
  // answer reopens with the same slider positions (latest-wins).
  const stateVars = finalized.state;
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  useEffect(() => {
    if (!stateKey || typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(`eclipse-response-state:${stateKey}`);
      setOverrides(raw ? (JSON.parse(raw) as Record<string, number>) : {});
    } catch {
      setOverrides({});
    }
  }, [stateKey]);

  const effectiveValues = useMemo(
    () => ({ ...initialEnvelopeValues(stateVars), ...overrides }),
    [stateVars, overrides],
  );
  const computedValues = useMemo(
    () => computeEnvelopeValues(stateVars, finalized.computed, effectiveValues),
    [stateVars, finalized.computed, effectiveValues],
  );
  const setValue = useCallback(
    (id: string, value: number) => {
      setOverrides((prev) => {
        const next = { ...prev, [id]: value };
        if (stateKey && typeof window !== 'undefined') {
          try {
            window.localStorage.setItem(`eclipse-response-state:${stateKey}`, JSON.stringify(next));
          } catch {
            /* storage unavailable — the edit still applies this session */
          }
        }
        return next;
      });
    },
    [stateKey],
  );
  const inputsState = useMemo<InputsState>(
    () => ({ vars: stateVars, values: effectiveValues, setValue }),
    [stateVars, effectiveValues, setValue],
  );

  // Resolve `$ref` (from the turn) and `$computed` (from envelope state) figures.
  const finalizedResolved = useMemo(
    () => resolveResponseFigures(finalized, figureResolver, computedValues),
    [finalized, figureResolver, computedValues],
  );

  const renderBlocks = (blocks: ValidatedBlock[]): ReactNode => (
    <>
      {blocks.map((block, i) => (
        <div key={blockKey(block, i)} className={blockGapClass(block.type, i > 0 ? blocks[i - 1].type : null, compact)}>
          {/* One-shot entrance motion (reduced-motion safe): a newly streamed
              block fades/rises once. The gap wrapper keeps its exact class so
              the layout-cohesion invariant is unchanged. */}
          <div className="response-block-enter">
            {renderBlock(block, { compact, renderBlocks, onFollowup }, i)}
          </div>
        </div>
      ))}
    </>
  );

  if (finalizedResolved.blocks.length === 0) {
    // Nothing renderable and nothing wrong: say so quietly instead of an empty
    // region (the first note carries the honest reason when there is one).
    return (
      <div className={cn('w-full text-[12px] text-muted-foreground/80', className)}>
        {finalizedResolved.diagnostics[0]?.message ?? 'No structured content was produced.'}
      </div>
    );
  }

  return (
    <InputsStateProvider value={inputsState}>
      <section className={cn('w-full', className)} aria-label="Structured response">
        {/* Breathing room around the export/action row: it used to sit flush
            against the content above and below, which read as one crowded
            block. */}
        <div className="mb-3 mt-1 flex flex-wrap items-start justify-between gap-x-2 gap-y-1.5">
          <ResponseHeader response={finalizedResolved} />
          {showActions ? <ResponseActions response={finalizedResolved} /> : null}
        </div>
        <div>{renderBlocks(finalizedResolved.blocks)}</div>
      </section>
    </InputsStateProvider>
  );
}

export default ResponseView;
