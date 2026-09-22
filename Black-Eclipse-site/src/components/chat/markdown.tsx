import { Fragment, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { BlockNode, InlineNode, parseMarkdown, tableToTsv } from '@/lib/chat/markdown';
import { CopyButton } from './copy-button';

interface MarkdownProps {
  content: string;
  className?: string;
  /** Tighter spacing + smaller type for the floating ChatDock. */
  compact?: boolean;
}


function renderInline(nodes: InlineNode[]): ReactNode[] {
  return nodes.map((node, i) => {
    switch (node.type) {
      case 'text':
        return <Fragment key={i}>{node.value}</Fragment>;
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
      case 'link':
        return (
          <a
            key={i}
            href={node.href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:opacity-80"
          >
            {renderInline(node.children)}
          </a>
        );
    }
  });
}

/**
 * Renders the assistant Markdown subset as real elements. Deliberately styled
 * with the frosted-glass tokens and generous vertical rhythm so full-width
 * agent replies read like a document rather than a bubble.
 */
export function Markdown({ content, className, compact = false }: MarkdownProps) {
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
        <Block key={i} block={block} compact={compact} />
      ))}
    </div>
  );
}

function Block({ block, compact }: { block: BlockNode; compact: boolean }) {
  switch (block.type) {
    case 'paragraph':
      return <p className="whitespace-pre-wrap">{renderInline(block.children)}</p>;

    case 'heading': {
      const Tag = (`h${block.level}`) as 'h1';
      const size =
        block.level === 1
          ? 'text-xl md:text-2xl font-semibold mt-1'
          : block.level === 2
            ? 'text-lg md:text-xl font-semibold mt-1'
            : 'text-base md:text-[17px] font-semibold';
      return (
        <Tag className={cn('tracking-tight text-foreground', compact ? 'text-[14px]' : size)}>
          {renderInline(block.children)}
        </Tag>
      );
    }

    case 'code':
      return (
        <div className="group/code relative">
          <pre className="glass-card-subtle overflow-x-auto rounded-xl border border-white/10 dark:border-white/5 p-3 text-[0.85em] scrollbar-hide">
            <code className="font-mono">{block.value}</code>
          </pre>
          <CopyButton
            value={block.value}
            label={block.language ? `${block.language} code` : 'code'}
            className="absolute right-1.5 top-1.5 bg-background/60 opacity-0 backdrop-blur transition-opacity group-hover/code:opacity-100 focus:opacity-100"
          />
        </div>
      );

    case 'blockquote':
      return (
        <blockquote className="border-l-2 border-primary/40 pl-3 text-muted-foreground">
          {block.children.map((child, i) => (
            <Block key={i} block={child} compact={compact} />
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
                {/* No fill, no container chrome: the table should read as part of
                    the reply. Just a hairline under a larger, quieter header. */}
                <tr>
                  {block.header.map((cell, ci) => (
                    <th
                      key={ci}
                      className="whitespace-nowrap border-b border-white/15 px-3 pb-2 pt-3 text-[1.05em] font-medium tracking-tight text-foreground dark:border-white/15"
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
                    {row.map((cell, ci) => (
                      <td
                        key={ci}
                        className="whitespace-nowrap px-3 py-2.5 align-top text-foreground/80"
                        style={{ textAlign: block.align[ci] ?? undefined }}
                      >
                        {renderInline(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-1 flex justify-end opacity-0 transition-opacity group-hover/table:opacity-100 focus-within:opacity-100">
            <CopyButton value={tableToTsv(block.header, block.rows)} label="table data" />
          </div>
        </div>
      );

    case 'list': {
      const List = block.ordered ? 'ol' : 'ul';
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
