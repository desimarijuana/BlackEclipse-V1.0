'use client';

import { Fragment, ReactNode } from 'react';
import { ExternalLink } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  BlockNode,
  InlineNode,
  collectLinks,
  extractHost,
  inlineText,
  isNegativeValue,
  isNumericText,
  isSourceHeading,
  isUnavailableText,
  parseMarkdown,
  tableToTsv,
} from '@/lib/chat/markdown';
import { CopyButton } from './copy-button';
import { RESPONSE_FENCE_LANGUAGE } from '@/lib/response/fence-check';
import { ResponseFenceLazy as ResponseFence } from '@/components/response/response-fence-lazy';
import { MermaidBlock } from '@/components/response/mermaid-block';

// A ```mermaid fence is a diagram, not code. `mermaid-block` lazy-imports the
// heavy `mermaid` package inside its own effect (so the library is still only
// fetched when a diagram appears); importing the small wrapper statically avoids
// a redundant chunk-load failure path around it.

interface MarkdownProps {
  content: string;
  className?: string;
  /** Tighter spacing + smaller type for the floating ChatDock. */
  compact?: boolean;
  /**
   * True while the assistant turn is still streaming. Lets an in-progress
   * `eclipse-response` fence show a composing placeholder rather than an error.
   */
  streaming?: boolean;
  /** Called when a response `controls` block submits — re-enters the agent loop. */
  onFollowup?: (prompt: string) => void;
}


export function renderInline(nodes: InlineNode[]): ReactNode[] {
  return nodes.map((node, i) => {
    switch (node.type) {
      case 'text': {
        // An explicit "unavailable" marker reads as a muted chip, never as a
        // value — the same honesty rule as the market-data layer.
        if (isUnavailableText(node.value)) {
          return (
            <span
              key={i}
              className="rounded border border-border/50 bg-accent/20 px-1.5 py-0.5 text-[0.8em] font-medium uppercase tracking-wide text-muted-foreground/80"
              title="Data not available from the source"
            >
              {node.value.trim()}
            </span>
          );
        }
        return <Fragment key={i}>{node.value}</Fragment>;
      }
      case 'strong':
        return (
          <strong key={i} className="font-semibold text-foreground">
            {renderInline(node.children)}
          </strong>
        );
      case 'em':
        return <em key={i}>{renderInline(node.children)}</em>;
      case 'del':
        return (
          <del key={i} className="opacity-70">
            {renderInline(node.children)}
          </del>
        );
      case 'code':
        return (
          <code
            key={i}
            className="rounded-md border border-white/10 dark:border-white/5 bg-accent/40 px-1.5 py-0.5 font-mono text-[0.85em] text-foreground/90"
          >
            {node.value}
          </code>
        );
      case 'link': {
        const host = extractHost(node.href);
        return (
          <a
            key={i}
            href={node.href}
            target="_blank"
            rel="noopener noreferrer"
            title={host ? `${node.href}` : node.href}
            className="group/link inline-flex items-baseline gap-0.5 text-primary underline underline-offset-2 hover:opacity-80"
          >
            {renderInline(node.children)}
            {host && (
              <ExternalLink
                size="0.8em"
                className="translate-y-px opacity-0 transition-opacity group-hover/link:opacity-70"
              />
            )}
          </a>
        );
      }
    }
  });
}

/**
 * Renders the assistant Markdown subset as real elements. Deliberately styled
 * with the frosted-glass tokens and generous vertical rhythm so full-width
 * agent replies read like a document rather than a bubble.
 */
export function Markdown({ content, className, compact = false, streaming = false, onFollowup }: MarkdownProps) {
  const blocks = parseMarkdown(content);

  return (
    <div
      className={cn(
        'text-foreground leading-relaxed break-words',
        compact ? 'space-y-2 text-[13px]' : 'space-y-3 text-[14px] md:text-[15px]',
        className,
      )}
    >
      {blocks.map((block, i) => (
        <Block key={i} block={block} compact={compact} streaming={streaming} onFollowup={onFollowup} />
      ))}
    </div>
  );
}

function Block({
  block,
  compact,
  streaming,
  onFollowup,
}: {
  block: BlockNode;
  compact: boolean;
  streaming: boolean;
  onFollowup?: (prompt: string) => void;
}) {
  switch (block.type) {
    case 'paragraph':
      return <p className="whitespace-pre-wrap">{renderInline(block.children)}</p>;

    case 'heading': {
      const Tag = (`h${block.level}`) as 'h1';
      // A heading that introduces sources/references reads as a quiet section
      // label rather than another loud title competing with the prose.
      const sourceSection = isSourceHeading(inlineText(block.children));
      const size =
        block.level === 1
          ? 'text-xl md:text-2xl font-semibold mt-1'
          : block.level === 2
            ? 'text-lg md:text-xl font-semibold mt-1'
            : 'text-base md:text-[17px] font-semibold';
      return (
        <Tag
          className={cn(
            'tracking-tight text-foreground',
            sourceSection
              ? 'text-[0.8em] font-medium uppercase tracking-wider text-muted-foreground/70'
              : compact ? 'text-[14px]' : size,
          )}
        >
          {renderInline(block.children)}
        </Tag>
      );
    }

    case 'code':
      // An `eclipse-response` fence is not code — it is the structured response
      // engine's entry point. Everything else is a normal code block.
      if (block.language === RESPONSE_FENCE_LANGUAGE) {
        return <ResponseFence source={block.value} streaming={streaming} compact={compact} onFollowup={onFollowup} />;
      }
      // A ```mermaid fence is a diagram, not code. Render it once the turn has
      // settled; while streaming, leave the fence as text so a half-written
      // definition never flashes a parse error.
      if (block.language === 'mermaid' && !streaming && block.value.trim()) {
        return <MermaidBlock diagram={block.value} />;
      }
      return (
        <div className="group/code relative">
          <pre className="glass-card-subtle overflow-x-auto rounded-xl border border-white/10 dark:border-white/5 p-3 text-[0.85em] scrollbar-hide">
            {block.language === 'diff' ? (
              <code className="font-mono block">
                {block.value.split('\n').map((line, i) => (
                  <span
                    key={i}
                    className={cn(
                      'block',
                      line.startsWith('+') && !line.startsWith('+++') && 'bg-emerald-500/10 text-emerald-300',
                      line.startsWith('-') && !line.startsWith('---') && 'bg-rose-500/10 text-rose-300',
                      (line.startsWith('@@') ) && 'text-sky-300/80',
                    )}
                  >
                    {line || ' '}
                  </span>
                ))}
              </code>
            ) : (
              <code className="font-mono">{block.value}</code>
            )}
          </pre>
          <CopyButton
            value={block.value}
            label={block.language ? `${block.language} code` : 'code'}
            className="hover-reveal absolute right-1.5 top-1.5 bg-background/60 opacity-0 backdrop-blur transition-opacity group-hover/code:opacity-100 focus:opacity-100"
          />
        </div>
      );

    case 'blockquote':
      return (
        <blockquote className="border-l-2 border-primary/40 pl-3 text-muted-foreground">
          {block.children.map((child, i) => (
            <Block key={i} block={child} compact={compact} streaming={streaming} onFollowup={onFollowup} />
          ))}
        </blockquote>
      );

    case 'hr':
      return <hr className="border-white/10 dark:border-white/5" />;

    case 'table':
      return (
        <div className="group/table my-1 w-full">
          <div className="w-full overflow-x-auto scrollbar-hide">
            <table className="w-full border-collapse text-left">
              <thead>
                {/* A quiet tinted header strip + hairline: the table still reads
                    as part of the reply, but the header row is legible and
                    clearly distinguished from the body. */}
                <tr>
                  {block.header.map((cell, ci) => (
                    <th
                      key={ci}
                      className="border-b border-white/15 bg-black/[0.03] px-3 pb-2 pt-3 text-[1.05em] font-semibold tracking-tight text-foreground dark:border-white/15 dark:bg-white/[0.04]"
                      style={{ textAlign: block.align[ci] ?? undefined }}
                    >
                      {renderInline(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, ri) => (
                  <tr key={ri} className="border-b border-white/[0.06] last:border-0">
                    {row.map((cell, ci) => {
                      const text = inlineText(cell);
                      // Right-align a column that is genuinely numeric, unless
                      // the author set an explicit alignment.
                      const numeric = block.align[ci] == null && isNumericText(text);
                      const negative = numeric && isNegativeValue(text);
                      return (
                        <td
                          key={ci}
                          className={cn(
                            'px-3 py-2.5 align-top break-words',
                            negative ? 'text-rose-400/90' : 'text-foreground/80',
                            numeric && 'tabular-nums',
                          )}
                          style={{ textAlign: block.align[ci] ?? (numeric ? 'right' : undefined) }}
                        >
                          {renderInline(cell)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="hover-reveal mt-1 flex justify-end opacity-0 transition-opacity group-hover/table:opacity-100 focus-within:opacity-100">
            <CopyButton value={tableToTsv(block.header, block.rows)} label="table data" />
          </div>
        </div>
      );

    case 'list': {
      const List = block.ordered ? 'ol' : 'ul';
      // A list whose items are (almost) just links is a source/reference list:
      // render it with the host shown, so a bare URL never floats unlabelled.
      const allLinks = block.items.map(collectLinks);
      const isSourceList =
        block.items.length > 0 &&
        allLinks.every((links, i) => links.length > 0 && inlineText(block.items[i]).trim() === links.map((l) => l.label).join(''));
      if (isSourceList) {
        return (
          <List className="space-y-1.5 pl-0 list-none">
            {block.items.map((item, i) => {
              const links = allLinks[i];
              return (
                <li key={i} className="flex flex-col gap-0.5 border-l-2 border-border/40 pl-3">
                  {links.map((l, li) => {
                    const host = extractHost(l.href);
                    return (
                      <a
                        key={li}
                        href={l.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group/src inline-flex items-baseline gap-1 text-primary underline underline-offset-2 hover:opacity-80"
                      >
                        <span className="truncate">{l.label || host || l.href}</span>
                        {host && l.label && (
                          <span className="shrink-0 text-[0.8em] text-muted-foreground/60">{host}</span>
                        )}
                        <ExternalLink size="0.75em" className="shrink-0 opacity-0 transition-opacity group-hover/src:opacity-70" />
                      </a>
                    );
                  })}
                </li>
              );
            })}
          </List>
        );
      }
      return (
        <List
          className={cn(
            'space-y-1 pl-5',
            block.ordered ? 'list-decimal' : 'list-disc',
          )}
        >
          {block.items.map((item, i) => (
            <li key={i} className="pl-0.5">
              {renderInline(item)}
            </li>
          ))}
        </List>
      );
    }
  }
}
