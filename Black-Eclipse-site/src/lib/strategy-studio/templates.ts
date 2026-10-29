// ── Strategy templates ──────────────────────────────────────────────────────
// A starting point, not a recommendation. Each template is a complete, valid
// Eclipse quant spec: a user can load it, change the symbol/window, and run it
// immediately. The copy says plainly that a template is an example, not advice.

export interface StrategyTemplate {
  id: string;
  name: string;
  tagline: string;
  spec: Record<string, unknown>;
}

const EXECUTION = {
  commission: { type: 'percentage', value: 0.1 },
  slippage: { type: 'percentage', value: 0.05 },
  spread: { type: 'bps', value: 5 },
  fill_at: 'next_open',
};

function spec(input: {
  id: string;
  name: string;
  description: string;
  symbols?: string[];
  timeframe?: string;
  indicators: Array<Record<string, unknown>>;
  entry: Array<Record<string, unknown>>;
  exit: Array<Record<string, unknown>>;
  stop?: number;
  target?: number;
  sizing?: Record<string, unknown>;
}): Record<string, unknown> {
  return {
    strategy: { id: input.id, name: input.name, version: '1.0.0', description: input.description },
    universe: { symbols: input.symbols ?? ['BTC-USD'], asset_classes: ['crypto'] },
    timeframes: { primary: input.timeframe ?? '1d', confirmation: [] },
    indicators: input.indicators,
    rules: {
      entry: { long: { type: 'group', combine: 'all', conditions: input.entry } },
      exit: {
        long: { type: 'group', combine: 'all', conditions: input.exit },
        stop_loss: { type: 'atr', value: input.stop ?? 2.0 },
        take_profit: { type: 'risk_reward', value: input.target ?? 3.0 },
      },
    },
    position_sizing: input.sizing ?? { type: 'percent_equity', value: 50 },
    risk: { max_position_pct: 100, max_open_positions: 1, allow_long: true, allow_short: false },
    execution: EXECUTION,
    metadata: { template: true },
  };
}

export const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  {
    id: 'ema_trend',
    name: 'EMA trend',
    tagline: 'Fast/slow EMA cross with an ATR stop. The classic trend follower.',
    spec: spec({
      id: 'ema_trend',
      name: 'EMA trend (20/50)',
      description: 'Long when the 20 EMA crosses above the 50 EMA; exit on the reverse cross, 2 ATR stop, 3R target.',
      indicators: [
        { id: 'ema_fast', type: 'ema', params: { period: 20 } },
        { id: 'ema_slow', type: 'ema', params: { period: 50 } },
        { id: 'atr', type: 'atr', params: { period: 14 } },
      ],
      entry: [{ type: 'condition', left: { ref: 'ema_fast' }, op: 'cross_above', right: { ref: 'ema_slow' } }],
      exit: [{ type: 'condition', left: { ref: 'ema_fast' }, op: 'cross_below', right: { ref: 'ema_slow' } }],
      stop: 2,
      target: 3,
    }),
  },
  {
    id: 'rsi_reversion',
    name: 'RSI reversion',
    tagline: 'Buy oversold pullbacks, but only above the long moving average.',
    spec: spec({
      id: 'rsi_reversion',
      name: 'RSI reversion in an uptrend',
      description: 'Long when RSI(14) is below 30 while price is above the 200 SMA; exit when RSI recovers above 55.',
      indicators: [
        { id: 'rsi', type: 'rsi', params: { period: 14 } },
        { id: 'sma_trend', type: 'sma', params: { period: 200 } },
        { id: 'atr', type: 'atr', params: { period: 14 } },
      ],
      entry: [
        { type: 'condition', left: { ref: 'rsi' }, op: '<', right: { value: 30 } },
        { type: 'condition', left: { ref: 'close' }, op: '>', right: { ref: 'sma_trend' } },
      ],
      exit: [{ type: 'condition', left: { ref: 'rsi' }, op: '>', right: { value: 55 } }],
      stop: 2.5,
      target: 2,
      sizing: { type: 'percent_equity', value: 50 },
    }),
  },
  {
    id: 'breakout',
    name: 'Breakout',
    tagline: 'Buy a new 20-bar high, exit on a 10-bar low. ATR stop.',
    spec: spec({
      id: 'breakout',
      name: 'Donchian-style breakout',
      description: 'Long when close makes a new 20-bar high; exit on a new 10-bar low, 2 ATR stop, 4R target.',
      indicators: [
        { id: 'high_20', type: 'highest', params: { period: 20 } },
        { id: 'low_10', type: 'lowest', params: { period: 10 } },
        { id: 'atr', type: 'atr', params: { period: 14 } },
      ],
      entry: [{ type: 'condition', left: { ref: 'close' }, op: '>', right: { ref: 'high_20' } }],
      exit: [{ type: 'condition', left: { ref: 'close' }, op: '<', right: { ref: 'low_10' } }],
      stop: 2,
      target: 4,
    }),
  },
  {
    id: 'momentum',
    name: 'Momentum',
    tagline: 'Ride positive 20-bar momentum while above the 100 SMA.',
    spec: spec({
      id: 'momentum',
      name: 'Momentum with a trend filter',
      description: 'Long when 20-bar rate of change is positive and price is above the 100 SMA; exit when momentum turns negative.',
      indicators: [
        { id: 'roc', type: 'roc', params: { period: 20 } },
        { id: 'sma_trend', type: 'sma', params: { period: 100 } },
        { id: 'atr', type: 'atr', params: { period: 14 } },
      ],
      entry: [
        { type: 'condition', left: { ref: 'roc' }, op: '>', right: { value: 0 } },
        { type: 'condition', left: { ref: 'close' }, op: '>', right: { ref: 'sma_trend' } },
      ],
      exit: [{ type: 'condition', left: { ref: 'roc' }, op: '<', right: { value: 0 } }],
      stop: 2,
      target: 3,
    }),
  },
  {
    id: 'dip_in_uptrend',
    name: 'Dip in uptrend',
    tagline: 'Buy short-term weakness while the medium trend is up.',
    spec: spec({
      id: 'dip_in_uptrend',
      name: 'Dip buying in an uptrend',
      description: 'Long when price closes below the 10 SMA while the 10 SMA is above the 50 SMA; exit on a close back above the 10 SMA.',
      indicators: [
        { id: 'sma_fast', type: 'sma', params: { period: 10 } },
        { id: 'sma_slow', type: 'sma', params: { period: 50 } },
        { id: 'atr', type: 'atr', params: { period: 14 } },
      ],
      entry: [
        { type: 'condition', left: { ref: 'close' }, op: '<', right: { ref: 'sma_fast' } },
        { type: 'condition', left: { ref: 'sma_fast' }, op: '>', right: { ref: 'sma_slow' } },
      ],
      exit: [{ type: 'condition', left: { ref: 'close' }, op: '>', right: { ref: 'sma_fast' } }],
      stop: 2,
      target: 2,
    }),
  },
  {
    id: 'risk_sized_trend',
    name: 'Risk-sized trend',
    tagline: 'A slow trend filter sized by fixed risk per trade, not by equity.',
    spec: spec({
      id: 'risk_sized_trend',
      name: 'Risk-sized slow trend',
      description: 'Long when the 50 EMA is above the 200 EMA and price is above the 50 EMA; 1% risk per trade with a 3 ATR stop.',
      indicators: [
        { id: 'ema_fast', type: 'ema', params: { period: 50 } },
        { id: 'ema_slow', type: 'ema', params: { period: 200 } },
        { id: 'atr', type: 'atr', params: { period: 20 } },
      ],
      entry: [
        { type: 'condition', left: { ref: 'ema_fast' }, op: '>', right: { ref: 'ema_slow' } },
        { type: 'condition', left: { ref: 'close' }, op: '>', right: { ref: 'ema_fast' } },
      ],
      exit: [{ type: 'condition', left: { ref: 'close' }, op: '<', right: { ref: 'ema_fast' } }],
      stop: 3,
      target: 3,
      sizing: { type: 'percent_risk', value: 1 },
    }),
  },
];

export function getTemplate(id: string): StrategyTemplate | undefined {
  return STRATEGY_TEMPLATES.find((template) => template.id === id);
}
