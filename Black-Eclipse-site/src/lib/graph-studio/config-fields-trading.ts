// Trading config presentation. Split out of config-fields.ts to keep both files
// inside the source size budget; merged back into the ONE map there.

import type { ConfigFieldDef } from './types';

type Override = Omit<ConfigFieldDef, 'key'> & { key: string };

const opts = (...values: string[]): ConfigFieldDef['options'] =>
  values.map((value) => ({ value, label: value }));

/** Trading nodes' field presentation (the Parameters tab). */
export const TRADING_FIELD_OVERRIDES: Record<string, Override[]> = {
  'trading.broker_order': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'mandateId', label: 'Mandate (live/paper)', kind: 'text' },
    { key: 'dryRun', label: 'Dry run (preview only)', kind: 'boolean', help: 'Sends nothing and creates no approval; `ok` then means the order would be allowed.' },
    { key: 'dedupe', label: 'Send at most', kind: 'select', options: opts('none', 'key', 'day'), help: 'A scheduled graph re-running must not double-send. The claim happens before the send.' },
    { key: 'idempotencyKey', label: 'Idempotency key', kind: 'text', help: 'Required when dedupe is "key".' },
  ],
  'trading.paper_order': [
    { key: 'price', label: 'Price', kind: 'number', inline: true, min: 0 },
    { key: 'accountId', label: 'Paper account', kind: 'text', inline: true },
    { key: 'initialCash', label: 'Initial cash', kind: 'number', min: 0 },
    { key: 'commissionPct', label: 'Commission %', kind: 'number', min: 0, max: 10 },
    { key: 'slippagePct', label: 'Slippage %', kind: 'number', min: 0, max: 10 },
    { key: 'persist', label: 'Persist fill', kind: 'boolean' },
    { key: 'dedupe', label: 'Fill at most', kind: 'select', options: opts('none', 'key', 'day') },
    { key: 'idempotencyKey', label: 'Idempotency key', kind: 'text', help: 'Required when dedupe is "key".' },
  ],
  'trading.paper_valuation': [
    { key: 'accountId', label: 'Paper account', kind: 'text', inline: true },
    { key: 'initialCash', label: 'Initial cash', kind: 'number', min: 0 },
  ],
  'trading.await_fill': [
    { key: 'orderId', label: 'Order id', kind: 'text', help: 'Wire broker_order\'s orderId instead of typing one.' },
    { key: 'timeoutSeconds', label: 'Timeout (s)', kind: 'number', min: 1, max: 240 },
    { key: 'pollSeconds', label: 'Poll every (s)', kind: 'number', min: 0.05, max: 60 },
  ],
  'trading.reconcile': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.drift_check': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'limit', label: 'Rows to compare', kind: 'number', min: 1, max: 200 },
    { key: 'maxAgeSeconds', label: 'Mirror max age (s)', kind: 'number', min: 0, help: '0 disables the staleness check.' },
    { key: 'syncFirst', label: 'Sync before comparing', kind: 'boolean', help: 'Refresh the mirror through the normal sync path first. The broker stays authoritative; remaining drift is only reported.' },
  ],
  'trading.order_preview': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'mandateId', label: 'Mandate (optional)', kind: 'text', help: 'Also check the mandate scope. Verifying does not consume a use.' },
  ],
  'trading.order_intent': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'EURUSD' },
    { key: 'side', label: 'Side', kind: 'select', inline: true, options: opts('buy', 'sell') },
    { key: 'orderType', label: 'Order type', kind: 'select', inline: true, options: opts('market', 'limit', 'stop') },
    { key: 'quantity', label: 'Quantity', kind: 'number', min: 0, help: 'Wired values win over these.' },
    { key: 'price', label: 'Order price', kind: 'number', min: 0, help: 'Required for a limit or stop order.' },
    { key: 'stopLoss', label: 'Stop loss', kind: 'number', min: 0, inline: true },
    { key: 'takeProfit', label: 'Take profit', kind: 'number', min: 0, inline: true },
    { key: 'timeInForce', label: 'Time in force', kind: 'select', options: opts('gtc', 'day') },
  ],
  'trading.paper_account': [
    { key: 'accountId', label: 'Paper account', kind: 'text', inline: true },
    { key: 'initialCash', label: 'Initial cash', kind: 'number', min: 0 },
  ],
  'trading.broker_account': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_positions': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_orders': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_fills': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'limit', label: 'Max fills', kind: 'number', min: 1, max: 200 },
  ],
  'trading.order_ledger': [
    { key: 'connectionId', label: 'Broker connection (optional)', kind: 'text' },
    { key: 'limit', label: 'Max rows', kind: 'number', min: 1, max: 200 },
  ],
  'trading.broker_quote': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'XAUUSD' },
  ],
  'trading.broker_bars': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'XAUUSD' },
    { key: 'timeframe', label: 'Timeframe', kind: 'select', options: opts('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1') },
    { key: 'count', label: 'Bars', kind: 'number', min: 1, max: 500 },
  ],
  'trading.broker_close': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'symbol', label: 'Symbol (close all in it)', kind: 'text', inline: true, placeholder: 'XAUUSD' },
    { key: 'closeAll', label: 'Close all positions', kind: 'boolean' },
    { key: 'deviation', label: 'Deviation (points)', kind: 'number', min: 0, max: 1_000 },
  ],
  'trading.broker_modify': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_modify_order': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_symbol': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'XAUUSD', help: 'Works with no live tick, so it answers while the market is closed.' },
  ],
  'trading.broker_cancel': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.risk_check': [
    { key: 'equity', label: 'Equity', kind: 'number', inline: true, min: 1, help: 'Used only when no `equity`/`account` input is wired.' },
    { key: 'price', label: 'Price', kind: 'number', min: 0 },
    { key: 'maxPositionPct', label: 'Max position %', kind: 'number', min: 0, max: 100 },
    { key: 'maxLeverage', label: 'Max leverage', kind: 'number', min: 0, max: 100 },
    { key: 'requireStop', label: 'Require stop', kind: 'boolean' },
  ],
  'trading.size_by_risk': [
    { key: 'equity', label: 'Equity', kind: 'number', inline: true, min: 1, help: 'Replaced by the wired equity input.' },
    { key: 'entry', label: 'Entry price', kind: 'number', min: 0 },
    { key: 'stop', label: 'Stop price', kind: 'number', min: 0 },
    { key: 'riskPct', label: 'Risk per trade %', kind: 'number', min: 0.01, max: 100 },
    { key: 'contractSize', label: 'Contract size', kind: 'number', min: 0, help: 'A wired broker_quote supplies this and the volume limits.' },
    { key: 'volumeStep', label: 'Volume step', kind: 'number', min: 0 },
    { key: 'volumeMin', label: 'Volume min (0 = none)', kind: 'number', min: 0 },
    { key: 'volumeMax', label: 'Volume max (0 = none)', kind: 'number', min: 0 },
  ],
  'trading.bracket': [
    { key: 'side', label: 'Side', kind: 'select', inline: true, options: opts('buy', 'sell') },
    { key: 'entry', label: 'Entry price', kind: 'number', min: 0 },
    { key: 'atrMultiple', label: 'ATR multiple', kind: 'number', min: 0.01, help: 'Used when no stop distance is set.' },
    { key: 'stopDistance', label: 'Stop distance (price)', kind: 'number', min: 0, help: 'Wins over the ATR.' },
    { key: 'rewardRisk', label: 'Reward : risk', kind: 'number', min: 0, help: '0 emits no target.' },
  ],
  'trading.spread_guard': [
    { key: 'maxSpreadPoints', label: 'Max spread (points)', kind: 'number', min: 0.01 },
  ],
  'trading.session_filter': [
    { key: 'startUtc', label: 'Start (UTC)', kind: 'text', inline: true, placeholder: '09:00' },
    { key: 'endUtc', label: 'End (UTC)', kind: 'text', inline: true, placeholder: '17:00', help: 'Start == end means all day. Ignored when broker sessions are available.' },
    { key: 'weekdays', label: 'Weekdays', kind: 'text', placeholder: 'mon,tue,wed,thu,fri', help: 'Used with the UTC window only.' },
    { key: 'side', label: 'Side (for trade-mode checks)', kind: 'select', options: [
      { value: '', label: 'Any / none' }, { value: 'buy', label: 'buy' }, { value: 'sell', label: 'sell' },
    ] },
    { key: 'serverOffsetMinutes', label: 'Server offset (min)', kind: 'number', min: -1_440, max: 1_440, help: 'Broker server clock vs UTC. Used only when broker sessions exist and no quote supplies a server time.' },
    { key: 'sessionsJson', label: 'Session calendar (JSON)', kind: 'json', help: 'Used when the terminal reports no sessions. [{"day":0,"from":"09:00","to":"17:00"}], day 0 = Monday, server time.' },
  ],
  'trading.break_even': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'triggerR', label: 'Trigger (R)', kind: 'number', min: 0.01 },
    { key: 'offset', label: 'Offset (price)', kind: 'number', help: 'Lock in slightly above/below entry.' },
  ],
  'trading.trail_stop': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'distance', label: 'Trail distance (price)', kind: 'number', min: 0 },
    { key: 'minStep', label: 'Minimum move', kind: 'number', min: 0, help: 'Ignore improvements smaller than this.' },
  ],
  'trading.partial_close': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'fraction', label: 'Fraction to close', kind: 'number', min: 0, max: 1, step: 0.05 },
    { key: 'deviation', label: 'Deviation (points)', kind: 'number', min: 0, max: 1_000 },
  ],
};

/** Parameters the inspector marks with a required asterisk. */
export const TRADING_REQUIRED_FIELDS: Record<string, string[]> = {
  'trading.broker_order': ['connectionId', 'mandateId'],
  'trading.order_preview': ['connectionId'],
  'trading.broker_account': ['connectionId'],
  'trading.broker_positions': ['connectionId'],
  'trading.broker_orders': ['connectionId'],
  'trading.broker_fills': ['connectionId'],
  'trading.broker_quote': ['connectionId'],
  'trading.broker_bars': ['connectionId'],
  'trading.broker_close': ['connectionId'],
  'trading.broker_modify': ['connectionId'],
  'trading.broker_modify_order': ['connectionId'],
  'trading.broker_symbol': ['connectionId'],
  'trading.broker_cancel': ['connectionId'],
  'trading.reconcile': ['connectionId'],
  'trading.drift_check': ['connectionId'],
  'trading.break_even': ['connectionId'],
  'trading.trail_stop': ['connectionId'],
  'trading.partial_close': ['connectionId'],
};
