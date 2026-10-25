// ── Deterministic Markdown projection ─────────────────────────────────────────
// A total, pure function from a response to readable Markdown. Every registered
// block type is projected — prose kept, tables as GFM, charts as their data
// table, controls as their current values, figures resolved or UNAVAILABLE — so a
// surface that cannot render blocks (export, PDF, bots, a copy button) never
// silently loses a block. It is derived from the block data, never authored by
// the model, so it cannot drift from the rendered answer.
//
// It runs the finalize chokepoint first, so a rejected (`unknown`) block is
// already degraded to readable content before projection.

import { finalizeParsed } from './finalize';
import { decodeResponseFence, splitResponseSegments } from './parse';
import { resolveSimulationInputs, resolveSimulationOutputs } from './simulation';
import type { ParsedResponse, TableCell, ValidatedBlock } from './contract';

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

/** A figure value: a number/string renders as-is; a `$ref` object is UNAVAILABLE. */
function figureText(value: unknown): string {
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'string') return value;
  if (isRecord(value)) return 'UNAVAILABLE';
  return '';
}

function cellText(cell: TableCell | undefined): string {
  if (cell == null) return '';
  if (typeof cell === 'boolean') return cell ? 'yes' : 'no';
  return String(cell);
}

function mdTable(head: string[], body: string[][]): string {
  const escape = (s: string) => s.replace(/\|/g, '\\|').replace(/\n/g, ' ');
  const header = `| ${head.map(escape).join(' | ')} |`;
  const delim = `| ${head.map(() => '---').join(' | ')} |`;
  const rows = body.map((row) => `| ${row.map(escape).join(' | ')} |`);
  return [header, delim, ...rows].join('\n');
}

function heading(text: string, level = 3): string {
  return `${'#'.repeat(Math.min(6, Math.max(1, level)))} ${text}`;
}

/** A GFM data table for a chart: one column per category, one row per series. */
function chartToMarkdown(block: Extract<ValidatedBlock, { type: 'chart' }>): string {
  const categories = block.categories ?? [];
  if (!block.series.length) return '_Chart with no series._';
  const head = ['Series', ...categories.map((c, i) => String(c ?? i + 1))];
  const body = block.series.map((s) => [s.name, ...s.data.map((v) => String(v))]);
  // A series with no categories still projects as a single-column table.
  if (!categories.length) {
    return mdTable(['Series', 'Values'], block.series.map((s) => [s.name, s.data.join(', ')]));
  }
  return mdTable(head, body);
}

function nodesEdges(nodes: { id: string; label: string }[], edges: { from: string; to: string }[]): string {
  const labels = new Map(nodes.map((n) => [n.id, n.label]));
  const edgeLines = edges.map((e) => `- ${labels.get(e.from) ?? e.from} → ${labels.get(e.to) ?? e.to}`);
  return edgeLines.length ? edgeLines.join('\n') : '_No edges._';
}

function blockToMarkdown(block: ValidatedBlock): string {
  switch (block.type) {
    case 'markdown':
      return block.markdown;
    case 'heading':
      return heading(block.text, block.level);
    case 'callout':
      return `${block.title ? `**${block.title}**\n\n` : ''}> ${block.markdown.replace(/\n/g, '\n> ')}`;
    case 'key_value':
      return [block.title ? heading(block.title) : '', mdTable(['Field', 'Value'], block.items.map((i) => [i.label, String(i.value)]))]
        .filter(Boolean)
        .join('\n\n');
    case 'details':
      return `**${block.summary}**\n\n${block.markdown}`;
    case 'metric_grid':
      return [
        block.title ? heading(block.title) : '',
        mdTable(
          ['Metric', 'Value', 'Delta'],
          block.metrics.map((m) => [
            m.label,
            m.unavailable ? 'UNAVAILABLE' : `${m.prefix ?? ''}${figureText(m.value)}${m.unit ?? ''}`,
            m.delta != null ? String(m.delta) : '',
          ]),
        ),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'data_table':
      return [
        block.title ? heading(block.title) : '',
        mdTable(block.columns.map((c) => c.label), block.rows.map((row) => block.columns.map((c) => cellText(row[c.key])))),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'chart':
      return [block.title ? heading(block.title) : '', chartToMarkdown(block)].filter(Boolean).join('\n\n');
    case 'diagram':
      return [
        block.title ? heading(block.title) : '',
        `_${block.diagramType} diagram_`,
        block.nodes.map((n) => `- ${n.label}`).join('\n'),
        nodesEdges(block.nodes, block.edges),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'node_graph':
      return [
        block.title ? heading(block.title) : '',
        block.nodes.map((n) => `- ${n.label}${n.group ? ` (${n.group})` : ''}${n.detail ? `: ${n.detail}` : ''}`).join('\n'),
        nodesEdges(block.nodes, block.edges),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'timeline':
      return [
        block.title ? heading(block.title) : '',
        mdTable(['Time', 'Event', 'Detail'], block.events.map((e) => [e.time, e.title, e.description ?? ''])),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'citations':
      return [
        block.title ? heading(block.title) : '### Sources',
        block.sources
          .map((s, i) => `${i + 1}. ${s.title}${s.url ? ` — ${s.url}` : ''}`)
          .join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'tabs':
      return block.tabs
        .map((tab) => `${heading(tab.label, 4)}\n\n${blocksToMarkdown(tab.blocks as ValidatedBlock[])}`)
        .join('\n\n');
    case 'financial_chart':
      return `${block.title ? `${heading(block.title)}\n\n` : ''}_Interactive price chart for ${block.symbol}${block.timeframe ? ` (${block.timeframe})` : ''} — open in the app._`;
    case 'mermaid':
      return `${block.title ? `${heading(block.title)}\n\n` : ''}\`\`\`mermaid\n${block.diagram}\n\`\`\``;
    case 'controls':
      return [
        block.title ? heading(block.title) : 'Interactive controls:',
        block.controls.map((c) => `- ${c.label}`).join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'stepper':
      return [
        block.title ? heading(block.title) : '',
        block.steps.map((s, i) => `${i + 1}. ${s.title}${s.description ? ` — ${s.description}` : ''} (${s.status})`).join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'infographic':
      return [
        block.title ? heading(block.title) : '',
        mdTable(
          ['Card', 'Value', 'Detail'],
          block.cards.map((c) => [c.label, c.unavailable ? 'UNAVAILABLE' : `${String(c.value ?? '')}${c.unit ?? ''}`, c.description ?? '']),
        ),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'workflow':
      return [
        block.title ? heading(block.title) : '',
        block.stages.map((s, i) => `${i + 1}. ${s.title}${s.description ? ` — ${s.description}` : ''}`).join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'flow':
      return [
        block.title ? heading(block.title) : '',
        block.steps
          .map(
            (s, i) =>
              `${i + 1}. ${s.label}${s.description ? ` — ${s.description}` : ''}` +
              (s.paths && s.paths.length ? `\n${s.paths.map((p) => `   - ${p.label}`).join('\n')}` : ''),
          )
          .join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'report':
      return [
        block.title ? heading(block.title, 2) : '',
        block.summary ?? '',
        block.sections
          .map((section) =>
            [
              section.heading ? heading(section.heading) : '',
              section.markdown ?? '',
              section.blocks && section.blocks.length ? blocksToMarkdown(section.blocks as ValidatedBlock[]) : '',
            ]
              .filter(Boolean)
              .join('\n\n'),
          )
          .join('\n\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'action_group':
      return [
        block.title ? heading(block.title) : '**Proposed next steps**',
        block.actions.map((a) => `- ${a.label}${a.description ? ` — ${a.description}` : ''}`).join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'artifact':
      return [
        block.title ? heading(block.title) : '**Artifacts**',
        block.artifacts.map((a) => `- ${a.name}${a.category ? ` (${a.category})` : ''}`).join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'gallery':
      return [block.title ? heading(block.title) : '', block.images.map((img) => `- ${img.alt ?? img.title ?? img.url} — ${img.url}`).join('\n')]
        .filter(Boolean)
        .join('\n\n');
    case 'learning_map':
      return [
        block.title ? heading(block.title) : '',
        block.nodes.map((n) => `- ${n.label}`).join('\n'),
        block.resources.length ? `\n**Resources**\n${block.resources.map((r) => `- ${r.title}${r.url ? ` — ${r.url}` : ''}`).join('\n')}` : '',
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'stat_hero':
      return [
        block.title ? heading(block.title) : '',
        mdTable(
          ['Statistic', 'Value', 'Delta'],
          block.stats.map((s) => [
            s.label,
            s.unavailable ? 'UNAVAILABLE' : `${s.prefix ?? ''}${figureText(s.value)}${s.unit ?? ''}`,
            s.delta != null ? String(s.delta) : '',
          ]),
        ),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'gauge':
      return [
        block.title ? heading(block.title) : '',
        mdTable(['Gauge', 'Value', 'Max'], block.gauges.map((g) => [g.label, String(g.value), `${g.max}${g.unit ? ` ${g.unit}` : ''}`])),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'comparison_grid':
      return [
        block.title ? heading(block.title) : '',
        mdTable(['Attribute', ...block.columns.map((c) => c.label)], block.rows.map((r) => [r.label, ...block.columns.map((_, i) => cellText(r.values[i] ?? null))])),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'ranked_list':
      return [
        block.title ? heading(block.title) : '',
        block.items
          .map((item, i) => `${i + 1}. ${item.label} — ${item.display ?? `${item.value}${item.unit ? ` ${item.unit}` : ''}`}`)
          .join('\n'),
      ]
        .filter(Boolean)
        .join('\n\n');
    case 'badge_row':
      return [block.title ? heading(block.title) : '', block.badges.map((b) => b.label).join(' · ')].filter(Boolean).join('\n\n');
    case 'carousel':
      return block.slides
        .map((slide, i) => `${heading(slide.title ?? slide.label ?? `Slide ${i + 1}`, 4)}\n\n${blocksToMarkdown(slide.blocks as ValidatedBlock[])}`)
        .join('\n\n');
    case 'simulation': {
      // Expand the preset so the projection shows the real default inputs/outputs.
      const inputs = resolveSimulationInputs(block).map((input) => `${input.label}: ${input.value}`);
      const outputs = resolveSimulationOutputs(block).map((output) => output.label);
      return [
        block.title ? heading(block.title) : '**Interactive calculator**',
        inputs.length ? `Inputs — ${inputs.join(', ')}` : '',
        outputs.length ? `Outputs — ${outputs.join(', ')} (computed interactively in the app)` : '',
        block.disclaimer ?? '',
      ]
        .filter(Boolean)
        .join('\n\n');
    }
    case 'layout':
      return blocksToMarkdown(block.blocks as ValidatedBlock[]);
    case 'divider':
      return block.label ? `---\n\n_${block.label}_` : '---';
    case 'anatomy': {
      const parts = block.parts.map((p) => `- ${p.label ?? p.id} (${p.kind})`).join('\n');
      const stages = block.stages
        .map((s, i) => `${i + 1}. ${s.label}${s.note ? ` — ${s.note}` : ''}${s.readout ? ` (${s.readout})` : ''}`)
        .join('\n');
      return [
        block.title ? heading(block.title) : '**Isometric figure**',
        block.description ?? '',
        parts,
        stages ? `Stages:\n${stages}` : '',
        block.caption ?? '',
      ]
        .filter(Boolean)
        .join('\n\n');
    }
    case 'inputs':
      return [
        block.title ? heading(block.title) : '**Interactive inputs**',
        'Edit these values in the app; any bound figures update instantly.',
      ].join('\n\n');
    case 'model3d': {
      const parts = block.parts
        .map((p) => `- ${p.label ?? p.id} (${p.recipe ?? p.kind})${p.lit ? ' — highlighted' : ''}`)
        .join('\n');
      const stages = block.stages
        .map((s, i) => `${i + 1}. ${s.label}${s.note ? ` — ${s.note}` : ''}${s.readout ? ` (${s.readout})` : ''}`)
        .join('\n');
      return [
        block.title ? heading(block.title) : '**3D model**',
        block.description ?? '',
        parts,
        stages ? `Stages:\n${stages}` : '',
        block.caption ?? '',
        '_Orbit and download the model as GLB in the app._',
      ]
        .filter(Boolean)
        .join('\n\n');
    }
    case 'interactive': {
      const dataset = block.dataset
        ? `Live data: ${block.dataset.symbol.toUpperCase()} · ${block.dataset.range ?? '6mo'} · ${block.dataset.interval ?? '1d'}`
        : '';
      return [
        block.title ? heading(block.title) : '**Interactive app**',
        block.description ?? '',
        dataset,
        '_Interactive — open the app to use it._',
        block.caption ?? '',
      ]
        .filter(Boolean)
        .join('\n\n');
    }
    case 'unknown':
      return '';
    default:
      return '';
  }
}

function blocksToMarkdown(blocks: ValidatedBlock[]): string {
  return blocks
    .map((block) => blockToMarkdown(block))
    .filter((text) => text.trim().length > 0)
    .join('\n\n');
}

/**
 * Project a response to readable Markdown. Total: any input yields a string.
 * The finalize chokepoint runs first, so no rejected block or error note leaks.
 */
export function toMarkdownProjection(response: ParsedResponse): string {
  const safe = finalizeParsed(response).response;
  const parts: string[] = [];
  if (safe.title) parts.push(`# ${safe.title}`);
  if (safe.summary) parts.push(safe.summary);
  const body = blocksToMarkdown(safe.blocks);
  if (body) parts.push(body);
  return parts.join('\n\n').trim();
}

/**
 * Project a full assistant message: prose is kept, each `eclipse-response` fence
 * is replaced by its Markdown projection (a malformed fence is preserved verbatim
 * so nothing is lost). This is what the copy button writes, so a copied answer is
 * readable text rather than raw JSON.
 */
export function projectContentMarkdown(content: string): string {
  return splitResponseSegments(content)
    .map((segment) => {
      if (segment.kind === 'markdown') return segment.text;
      const decoded = decodeResponseFence(segment.source, true);
      if (decoded.status === 'ok') return toMarkdownProjection(decoded.response);
      return `\`\`\`eclipse-response\n${segment.source}\n\`\`\``;
    })
    .join('\n\n')
    .trim();
}
