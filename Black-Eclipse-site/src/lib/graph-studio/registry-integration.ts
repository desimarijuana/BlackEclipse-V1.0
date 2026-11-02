// ── Integration node contracts ───────────────────────────────────────────────
// The outbound HTTP family. Every executor lives in the Python runtime
// (`graph_runtime/http_client.py` + `nodes.py`); this file is the editor
// contract and is mirrored node-for-node by `registry.manifest.json`.
//
// 1.0.0 stays registered for saved graphs. 1.1.0 is additive: query params,
// body modes, retries, redirect policy, response headers and richer outputs.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const INTEGRATION_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'integration.http',
    version: '1.1.0',
    category: 'integration',
    label: 'HTTP request',
    description:
      'Calls an external HTTP endpoint with query, body modes, retries and bounded responses.',
    icon: 'globe',
    inputs: [
      port({ id: 'url', name: 'URL', type: 'string', optional: true }),
      port({ id: 'body', name: 'Body', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'status', name: 'Status', type: 'number' }),
      port({ id: 'body', name: 'Body', type: 'any' }),
      port({ id: 'headers', name: 'Headers', type: 'object' }),
      port({ id: 'ok', name: 'OK', type: 'boolean' }),
      port({ id: 'contentType', name: 'Content type', type: 'string' }),
      port({ id: 'durationMs', name: 'Duration', type: 'number' }),
      port({ id: 'truncated', name: 'Truncated', type: 'boolean' }),
    ],
    configSchema: z.object({
      url: z.string().max(2_000).default(''),
      method: z
        .enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])
        .default('GET'),
      queryJson: z.string().max(8_000).default(''),
      bodyJson: z.string().max(20_000).default(''),
      bodyMode: z.enum(['json', 'text', 'form']).default('json'),
      headersJson: z.string().max(10_000).default(''),
      credentialEnvJson: z.string().max(10_000).default(''),
      responseType: z.enum(['auto', 'json', 'text']).default('auto'),
      maxResponseBytes: z.number().int().min(1_000).max(10_000_000).default(1_000_000),
      onOversize: z.enum(['error', 'truncate']).default('error'),
      followRedirects: z.boolean().default(false),
      maxRedirects: z.number().int().min(0).max(5).default(3),
      failOnHttpError: z.boolean().default(true),
      retries: z.number().int().min(0).max(3).default(0),
      retryBackoffMs: z.number().int().min(100).max(10_000).default(500),
      retryUnsafe: z.boolean().default(false),
      timeoutMs: z.number().int().min(1_000).max(60_000).default(10_000),
    }),
    defaultConfig: () => ({
      url: '',
      method: 'GET',
      queryJson: '',
      bodyJson: '',
      bodyMode: 'json',
      headersJson: '',
      credentialEnvJson: '',
      responseType: 'auto',
      maxResponseBytes: 1_000_000,
      onOversize: 'error',
      followRedirects: false,
      maxRedirects: 3,
      failOnHttpError: true,
      retries: 0,
      retryBackoffMs: 500,
      retryUnsafe: false,
      timeoutMs: 10_000,
    }),
    capabilities: ['network.egress'],
    sideEffects: 'network',
    allowedModes: ALL_MODES,
    docs: 'SSRF-checked on the initial URL and every redirect hop. Redirects are opt-in and may not downgrade to HTTP. Retries apply to idempotent methods unless retryUnsafe is on. Credentials are header -> ENV VAR references; values are never stored. Requires an operator run with network access explicitly granted.',
  },
  {
    type: 'integration.webhook_send',
    version: '1.0.0',
    category: 'integration',
    label: 'Send webhook',
    description: 'POSTs a JSON payload with an HMAC-SHA256 webhook signature.',
    icon: 'globe',
    inputs: [
      port({ id: 'url', name: 'URL', type: 'string', optional: true }),
      port({ id: 'body', name: 'Body', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'status', name: 'Status', type: 'number' }),
      port({ id: 'ok', name: 'OK', type: 'boolean' }),
      port({ id: 'body', name: 'Body', type: 'any' }),
      port({ id: 'durationMs', name: 'Duration', type: 'number' }),
    ],
    configSchema: z.object({
      url: z.string().max(2_000).default(''),
      bodyJson: z.string().max(20_000).default(''),
      secretEnv: z.string().max(128).default(''),
      headersJson: z.string().max(10_000).default(''),
      deliveryId: z.string().max(200).default(''),
      failOnHttpError: z.boolean().default(true),
      retries: z.number().int().min(0).max(3).default(0),
      retryBackoffMs: z.number().int().min(100).max(10_000).default(500),
      maxResponseBytes: z.number().int().min(1_000).max(10_000_000).default(1_000_000),
      timeoutMs: z.number().int().min(1_000).max(60_000).default(10_000),
    }),
    defaultConfig: () => ({
      url: '',
      bodyJson: '',
      secretEnv: '',
      headersJson: '',
      deliveryId: '',
      failOnHttpError: true,
      retries: 0,
      retryBackoffMs: 500,
      maxResponseBytes: 1_000_000,
      timeoutMs: 10_000,
    }),
    capabilities: ['network.egress'],
    sideEffects: 'network',
    allowedModes: ALL_MODES,
    docs: 'Sends X-Eclipse-Signature (sha256 over "<timestamp>.<body>"), X-Eclipse-Timestamp and X-Eclipse-Delivery. The signing secret is an ENV VAR name, resolved at run time and never stored. Requires an operator run with network access explicitly granted.',
  },
];
