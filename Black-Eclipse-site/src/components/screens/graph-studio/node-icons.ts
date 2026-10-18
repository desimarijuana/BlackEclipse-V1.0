'use client';

// Maps a NodeDefinition's `icon` key (a plain string in the registry) to a
// rendered icon. Keeping the registry data-only means the registry is safe to
// import anywhere; this is the ONE place a key becomes a component.

import {
  Activity, Bot, Check, Clock, FileCode2, GitBranch, Globe, ChartLine,
  Play, Sigma, Sliders, type LucideIcon,
} from '@/lib/icons';
import type { NodeCategory } from '@/lib/graph-studio/types';

const ICONS: Record<string, LucideIcon> = {
  play: Play,
  clock: Clock,
  variable: Sliders,
  braces: FileCode2,
  text: FileCode2,
  sigma: Sigma,
  branch: GitBranch,
  merge: GitBranch,
  globe: Globe,
  chart: ChartLine,
  activity: Activity,
  bot: Bot,
  check: Check,
};

const CATEGORY_FALLBACK: Record<NodeCategory, LucideIcon> = {
  trigger: Play,
  data: FileCode2,
  transform: Sigma,
  logic: GitBranch,
  integration: Globe,
  finance: ChartLine,
  quant: Activity,
  agent: Bot,
  output: Check,
};

export function nodeIcon(icon: string | undefined, category: NodeCategory): LucideIcon {
  return (icon && ICONS[icon]) || CATEGORY_FALLBACK[category] || Sliders;
}
