// ── Semantic icon allowlist for visual blocks (client-only) ──────────────────
//
// The producer supplies an icon *key* (e.g. "trend-up"), never a component name,
// import path or SVG. This registry is the single place that maps a key to a
// real icon from the app's one icon surface (`@/lib/icons`). An unknown key
// degrades to a neutral default, so a bad key can never break a block — and no
// key can reach arbitrary code.
//
// CLIENT-ONLY: this module imports the React icon set. The vocabulary itself —
// keys, aliases, canonicalization — lives in `./icon-vocabulary`, which server
// code (the `response_contract` bridge) imports instead. Importing THIS module
// from a server route pulls `@phosphor-icons/react` into the react-server bundle
// and crashes it (`react.createContext is not a function`).

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
import { isResponseIconKey, type ResponseIconKey } from './icon-vocabulary';

export { RESPONSE_ICON_KEYS, canonicalIconKey, isResponseIconKey, type ResponseIconKey } from './icon-vocabulary';

/**
 * The allowlisted semantic key → component map. `satisfies` pins it to the
 * vocabulary EXACTLY: a key added to `./icon-vocabulary` without a component
 * (or a stale entry here) fails typecheck.
 */
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
} as const satisfies Record<ResponseIconKey, LucideIcon>;

/** The neutral fallback when a key is absent or unknown. */
export const DEFAULT_RESPONSE_ICON: LucideIcon = CircleDot;

/**
 * Resolve a semantic key to an icon component. Unknown/missing keys return the
 * neutral default rather than throwing — a visual block must never fail because
 * its icon was spelled wrong.
 */
export function resolveResponseIcon(key: string | undefined): LucideIcon {
  if (isResponseIconKey(key)) return RESPONSE_ICONS[key];
  return DEFAULT_RESPONSE_ICON;
}
