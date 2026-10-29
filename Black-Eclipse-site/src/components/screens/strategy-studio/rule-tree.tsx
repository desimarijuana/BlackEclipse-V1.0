'use client';

// ── Recursive rule editor ───────────────────────────────────────────────────
// The builder's rule editor. Groups can contain groups; every edit goes through
// the pure tree functions in `spec-edit.ts`, so the JSON stays authoritative and
// an unknown expression is still shown read-only instead of being rewritten.
//
// Nesting is capped (MAX_DEPTH) because an unbounded form is unusable; deeper
// specs remain editable in JSON.

import React from 'react';
import {
  OPERATORS,
  addTreeNode,
  availableRefs,
  readTree,
  removeTreeNode,
  setTreeCombine,
  updateTreeNode,
  type FlatCondition,
  type GroupPath,
  type TreeNodeView,
} from '@/lib/strategy-studio/spec-edit';
import { AlertTriangle, Plus, X } from '@/lib/icons';
import { cn } from '@/lib/utils';

const INPUT =
  'glass-card-subtle rounded-lg px-2 py-1 font-mono text-[10px] text-foreground outline-none disabled:opacity-50';
const LABEL = 'text-[10px] uppercase tracking-wide text-muted-foreground';
const MAX_DEPTH = 3;

export function RuleTreeEditor({
  title,
  spec,
  groupPath,
  disabled,
  onChange,
}: {
  title: string;
  spec: Record<string, unknown>;
  groupPath: GroupPath;
  disabled: boolean;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const tree = readTree(spec, groupPath);
  const refs = availableRefs(spec);

  return (
    <section className="rounded-xl border border-white/10 p-2">
      <div className="mb-1 flex items-center gap-2">
        <p className={LABEL}>{title}</p>
        {tree.children.length > 1 ? (
          <label className="ml-auto flex items-center gap-1 text-[9px] text-muted-foreground">
            match
            <select
              value={tree.combine}
              disabled={disabled}
              onChange={(event) =>
                onChange(setTreeCombine(spec, groupPath, [], event.target.value as 'all' | 'any'))
              }
              className={cn(INPUT, 'py-0.5')}
            >
              <option value="all">all</option>
              <option value="any">any</option>
            </select>
          </label>
        ) : null}
      </div>

      {tree.missing ? (
        <p className="text-[10px] text-muted-foreground">
          This group does not exist yet; adding a condition creates it.
        </p>
      ) : null}

      <div className="space-y-1.5">
        {tree.children.map((node) => (
          <NodeEditor
            key={node.path.join('.')}
            node={node}
            spec={spec}
            groupPath={groupPath}
            refs={refs}
            depth={0}
            disabled={disabled}
            onChange={onChange}
          />
        ))}
        {!tree.children.length && !tree.missing ? (
          <p className="text-[10px] text-muted-foreground">No conditions yet.</p>
        ) : null}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(addTreeNode(spec, groupPath, [], 'condition'))}
          className="glass-button flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] disabled:opacity-50"
        >
          <Plus className="h-2.5 w-2.5" /> Add condition
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(addTreeNode(spec, groupPath, [], 'group'))}
          className="glass-button flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] disabled:opacity-50"
        >
          <Plus className="h-2.5 w-2.5" /> Add group
        </button>
      </div>
    </section>
  );
}

function NodeEditor({
  node,
  spec,
  groupPath,
  refs,
  depth,
  disabled,
  onChange,
}: {
  node: TreeNodeView;
  spec: Record<string, unknown>;
  groupPath: GroupPath;
  refs: string[];
  depth: number;
  disabled: boolean;
  onChange: (next: Record<string, unknown>) => void;
}) {
  if (node.group) {
    const group = node.group;
    const canNest = depth < MAX_DEPTH;
    return (
      <div className="rounded-lg border border-white/10 bg-black/10 p-1.5">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="font-mono text-[9px] text-muted-foreground">
            group {node.path.map((part) => part + 1).join('.')}
          </span>
          {group.children.length > 1 ? (
            <label className="flex items-center gap-1 text-[9px] text-muted-foreground">
              match
              <select
                value={group.combine}
                disabled={disabled}
                onChange={(event) =>
                  onChange(
                    setTreeCombine(spec, groupPath, node.path, event.target.value as 'all' | 'any'),
                  )
                }
                className={cn(INPUT, 'py-0.5')}
              >
                <option value="all">all</option>
                <option value="any">any</option>
              </select>
            </label>
          ) : null}
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange(removeTreeNode(spec, groupPath, node.path))}
            aria-label="Remove group"
            className="ml-auto rounded p-1 text-muted-foreground hover:text-rose-400 disabled:opacity-50"
          >
            <X className="h-3 w-3" />
          </button>
        </div>

        <div className="space-y-1">
          {group.children.map((child) => (
            <NodeEditor
              key={child.path.join('.')}
              node={child}
              spec={spec}
              groupPath={groupPath}
              refs={refs}
              depth={depth + 1}
              disabled={disabled}
              onChange={onChange}
            />
          ))}
          {!group.children.length ? (
            <p className="text-[9px] text-muted-foreground">Empty group — add a condition or remove it.</p>
          ) : null}
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange(addTreeNode(spec, groupPath, node.path, 'condition'))}
            className="glass-button rounded-md px-1.5 py-0.5 text-[9px] disabled:opacity-50"
          >
            + condition
          </button>
          {canNest ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(addTreeNode(spec, groupPath, node.path, 'group'))}
              className="glass-button rounded-md px-1.5 py-0.5 text-[9px] disabled:opacity-50"
            >
              + group
            </button>
          ) : null}
          {!canNest ? (
            <span className="text-[9px] text-amber-200/80">deeper nesting is JSON-only</span>
          ) : null}
        </div>
      </div>
    );
  }

  const condition = node.condition;
  if (!condition) return null;
  if (condition.advanced) {
    return (
      <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-200">
        <AlertTriangle className="mr-1 inline h-3 w-3" />
        advanced condition {node.path.map((part) => part + 1).join('.')} — edit in JSON
      </div>
    );
  }

  return (
    <ConditionRow
      condition={condition}
      refs={refs}
      disabled={disabled}
      onChange={(patch) => onChange(updateTreeNode(spec, groupPath, node.path, patch))}
      onRemove={() => onChange(removeTreeNode(spec, groupPath, node.path))}
    />
  );
}

function ConditionRow({
  condition,
  refs,
  disabled,
  onChange,
  onRemove,
}: {
  condition: FlatCondition;
  refs: string[];
  disabled: boolean;
  onChange: (patch: Partial<FlatCondition>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      <select
        value={condition.leftRef ?? refs[0]}
        disabled={disabled}
        onChange={(event) => onChange({ leftRef: event.target.value })}
        className={cn(INPUT, 'min-w-[82px]')}
        aria-label="left operand"
      >
        {refs.map((ref) => (
          <option key={ref} value={ref}>{ref}</option>
        ))}
      </select>
      <select
        value={condition.op}
        disabled={disabled}
        onChange={(event) => onChange({ op: event.target.value })}
        className={cn(INPUT, 'w-24')}
        aria-label="operator"
      >
        {OPERATORS.map((op) => (
          <option key={op} value={op}>{op}</option>
        ))}
      </select>
      <select
        value={condition.rightKind}
        disabled={disabled}
        onChange={(event) => onChange({ rightKind: event.target.value as 'ref' | 'value' })}
        className={cn(INPUT, 'w-16')}
        aria-label="right operand kind"
      >
        <option value="ref">ref</option>
        <option value="value">value</option>
      </select>
      {condition.rightKind === 'ref' ? (
        <select
          value={condition.rightRef ?? refs[0]}
          disabled={disabled}
          onChange={(event) => onChange({ rightRef: event.target.value })}
          className={cn(INPUT, 'min-w-[82px]')}
          aria-label="right reference"
        >
          {refs.map((ref) => (
            <option key={ref} value={ref}>{ref}</option>
          ))}
        </select>
      ) : (
        <input
          type="number"
          step="0.1"
          value={condition.rightValue}
          disabled={disabled}
          onChange={(event) => onChange({ rightValue: Number(event.target.value) })}
          className={cn(INPUT, 'w-20 text-right')}
          aria-label="right value"
        />
      )}
      <button
        type="button"
        disabled={disabled}
        onClick={onRemove}
        aria-label="Remove condition"
        className="rounded p-1 text-muted-foreground hover:text-rose-400 disabled:opacity-50"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
