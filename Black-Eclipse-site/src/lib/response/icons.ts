// ── Semantic icon allowlist for visual blocks ─────────────────────────────────
//
// The producer supplies an icon *key* (e.g. "trend-up"), never a component name,
// import path or SVG. This registry is the single place that maps a key to a
// real icon from the app's one icon surface (`@/lib/icons`). An unknown key
// degrades to a neutral default, so a bad key can never break a block — and no
// key can reach arbitrary code.

import {
  Activity,
  AlertTriangle,
  BarChart2,
  Bot,
  Brain,
  BrainCircuit,
  Briefcase,
  CalendarDays,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleDot,
  Coins,
  Cpu,
  Database,
  DollarSign,
  FileText,
  FlaskConical,
  Gauge,
  GitBranch,
  Globe,
  History,
  Info,
  Landmark,
  Layers,
  ListChecks,
  Network,
  Percent,
  PieChart,
  Pin,
  Radio,
  Rocket,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  Timer,
  TrendingDown,
  TrendingUp,
  Wallet,
  Waypoints,
  Zap,
  type LucideIcon,
} from '@/lib/icons';

/** The allowlisted semantic icon vocabulary. Keys are lower-kebab-case. */
export const RESPONSE_ICONS = {
  'trend-up': TrendingUp,
  'trend-down': TrendingDown,
  chart: BarChart2,
  allocation: PieChart,
  activity: Activity,
  target: Target,
  gauge: Gauge,
  risk: ShieldCheck,
  wallet: Wallet,
  coins: Coins,
  dollar: DollarSign,
  percent: Percent,
  research: FlaskConical,
  brain: Brain,
  database: Database,
  globe: Globe,
  calendar: CalendarDays,
  clock: Timer,
  history: History,
  document: FileText,
  check: CheckCircle2,
  warning: AlertTriangle,
  info: Info,
  sparkles: Sparkles,
  zap: Zap,
  search: Search,
  layers: Layers,
  network: Network,
  workflow: Waypoints,
  'brain-circuit': BrainCircuit,
  'combined-chart': ChartNoAxesCombined,
  radio: Radio,
  cpu: Cpu,
  server: Server,
  gears: Settings,
  briefcase: Briefcase,
  market: Landmark,
  agent: Bot,
  'version-control': GitBranch,
  list: ListChecks,
  rocket: Rocket,
  pin: Pin,
} as const satisfies Record<string, LucideIcon>;

export type ResponseIconKey = keyof typeof RESPONSE_ICONS;

const ICON_KEYS = new Set<string>(Object.keys(RESPONSE_ICONS));

/** The neutral fallback when a key is absent or unknown. */
export const DEFAULT_RESPONSE_ICON: LucideIcon = CircleDot;

/** True when `key` is an allowlisted semantic icon key. */
export function isResponseIconKey(key: string | undefined): key is ResponseIconKey {
  return typeof key === 'string' && ICON_KEYS.has(key);
}

/**
 * Resolve a semantic key to an icon component. Unknown/missing keys return the
 * neutral default rather than throwing — a visual block must never fail because
 * its icon was spelled wrong.
 */
export function resolveResponseIcon(key: string | undefined): LucideIcon {
  if (isResponseIconKey(key)) return RESPONSE_ICONS[key];
  return DEFAULT_RESPONSE_ICON;
}
