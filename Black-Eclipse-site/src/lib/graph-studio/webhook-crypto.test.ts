import { describe, expect, it } from 'vitest';
import {
  deliveryIdOf,
  generateWebhookSecret,
  generateWebhookSlug,
  secretHint,
  signWebhook,
  verifyWebhookSignature,
  verifyWebhookToken,
} from './webhook-crypto';

const NOW = 1_800_000_000_000; // fixed epoch ms
const TS = String(Math.floor(NOW / 1000));

describe('webhook proof', () => {
  it('generates URL-safe secrets and slugs', () => {
    const secret = generateWebhookSecret();
    const slug = generateWebhookSlug();
    expect(secret).toMatch(/^[A-Za-z0-9_-]{40,64}$/);
    expect(slug).toMatch(/^[A-Za-z0-9_-]{20,32}$/);
    expect(secretHint(secret)).toBe(secret.slice(-4));
  });

  it('accepts a fresh, correct signature', () => {
    const secret = 'test-secret';
    const signature = signWebhook(secret, TS, '{"a":1}');
    expect(verifyWebhookSignature({
      secret, signature, timestamp: TS, body: '{"a":1}', nowMs: NOW,
    })).toBeNull();
  });

  it('rejects a tampered body', () => {
    const secret = 'test-secret';
    const signature = signWebhook(secret, TS, '{"a":1}');
    expect(verifyWebhookSignature({
      secret, signature, timestamp: TS, body: '{"a":2}', nowMs: NOW,
    })).toBe('signature mismatch');
  });

  it('rejects a stale timestamp outside the replay window', () => {
    const secret = 'test-secret';
    const old = String(Math.floor(NOW / 1000) - 3_600);
    const signature = signWebhook(secret, old, '');
    expect(verifyWebhookSignature({
      secret, signature, timestamp: old, body: '', nowMs: NOW,
    })).toBe('timestamp outside the replay window');
  });

  it('rejects a malformed signature', () => {
    expect(verifyWebhookSignature({
      secret: 's', signature: 'sha256=xyz', timestamp: TS, body: '', nowMs: NOW,
    })).toBe('invalid signature format');
  });

  it('verifies a token without leaking a comparison', () => {
    expect(verifyWebhookToken('abc', 'abc')).toBeNull();
    expect(verifyWebhookToken('abc', 'abd')).toBe('token mismatch');
    expect(verifyWebhookToken('abc', null)).toBe('missing token');
  });

  it('prefers an explicit delivery id and falls back to a body digest', () => {
    expect(deliveryIdOf({ headerValue: 'evt_1', timestamp: TS, body: '' })).toBe('evt_1');
    const fallback = deliveryIdOf({ headerValue: null, timestamp: TS, body: '{"a":1}' });
    expect(fallback.startsWith('body:')).toBe(true);
    expect(fallback).toBe(deliveryIdOf({ headerValue: null, timestamp: TS, body: '{"a":1}' }));
  });
});
