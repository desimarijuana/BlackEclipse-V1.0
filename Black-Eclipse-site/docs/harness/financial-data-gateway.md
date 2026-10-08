---
title: Financial Data Gateway
status: Current
last-verified: 2026-10-07
---

# Financial Data Gateway

**Who this is for:** anyone adding a financial data provider, routing a financial
request, or debugging "which source answered, and why?".

The Financial Data Gateway is the **provider-agnostic layer agents call**. An
agent asks for an *objective + data type + instrument*; the gateway selects,
fetches, normalizes, validates, reconciles and preserves provenance. The agent
never names Yahoo, FMP, SEC, Binance or CoinGecko.

This is NOT a second data plane. It is the existing **Financial Retrieval Layer**
(`python/harness/retrieval/`) plus three additions that make provider management
first-class:

| Concern | Where |
|---|---|
| Request/result/evidence contracts | `retrieval/contract.py` |
| Routing & authority | `retrieval/authority.py`, `retrieval/planner.py`, `retrieval/health.py` |
| Sources (JDdS / live / SEC / web / crypto) | `retrieval/structured.py`, `retrieval/web.py`, `retrieval/crypto.py` |
| Normalization | `retrieval/normalize.py` |
| Conflict detection | `retrieval/conflicts.py` |
| Freshness / point-in-time | `retrieval/policies.py`, `finance_facts/freshness.py`, `finance_facts/point_in_time.py` |
| Cache + dedup + durable replay | `retrieval/cache.py`, `retrieval/layer.py` |
| Retry / fallback | `retrieval/retry.py` |
| **Provider capability registry** | `retrieval/registry.py` |
| **Centralized rate limits / quota** | `retrieval/ratelimit.py` |
| **Crypto source** | `retrieval/crypto.py` + TS `crypto_market_data` |
| Agent tools | `retrieval_tools.py` |
| Provider-introspection route | `routers/financial.py` (`GET /financial/providers`) |
| Settings console | `src/components/screens/financial-data-console.tsx` |

## The flow

```
agent tool (retrieval_tools.py)
  → FinancialRetrievalLayer.retrieve()
      → planner (authority table → ordered candidates; crypto-aware)
      → health reorder (fail-open; never adds/removes a source)
      → durable replay (identical request → stored result)
      → cache + in-flight dedup
      → per-source rate-limit acquire (ratelimit.RateLimitManager)
      → fetch (single-best or parallel arbitration)
      → normalize → validate (dataset + per-observation)
      → conflict detect → provenance → FinancialRetrievalResult
```

## Provider registry (`retrieval/registry.py`)

One declarative `ProviderDescriptor` per provider: `capabilities`, `datasets`,
`credential_ref` (env-var NAME only), `rate_limit`, `usage` (license /
attribution / redistribution / storage), and `implemented`. A descriptor with
`implemented=False` is a **catalogued but not-yet-runnable** provider — the
dependency is named in `notes`, never faked.

`build_default_registry()` mirrors the sources the layer constructs. The service
and the `financial_providers` tool read the same registry (a default is built
lazily when a test has no service), so introspection and routing never disagree.

### Adding a provider

1. **Implement a `RetrievalSource`** (`retrieval/sources.py`): `name`, `tier`,
   `dataTypes`, `available(request)`, `async retrieve(request) -> SourceOutcome`.
   Never raise; return an `UNAVAILABLE` outcome with a categorized `diagnostics`
   entry. Register it in `FinancialRetrievalLayer.__init__`.
2. **Add ONE registry row** in `registry.py` with its capabilities, credential
   reference and usage policy.
3. **Add a data-type row** in `authority.AUTHORITY` if the provider serves a new
   capability (so `decide_source` considers it).
4. **If it needs a new transport capability**, add it to `DataCapability` in
   `src/lib/harness/types.ts`, dispatch it in `data-bridge.ts`, whitelist it in
   `src/app/api/harness/data/route.ts`, and map it in `health-key.ts`. Reuse the
   SSRF-hardened `safeGet` — never add a second HTTP client.
5. **Expose an agent tool** only if the agent must call it directly; otherwise
   the generic retrieval tools already reach it. A tool must call the LAYER, not
   the provider.

## Rate limits (`retrieval/ratelimit.py`)

An in-process `RateLimitManager` enforces a per-provider sliding-window
requests/minute, a concurrency ceiling, and a 429 cooldown (with `Retry-After`).
The layer acquires before every provider call; a denied acquire is an honest,
categorized `rate_limited` outcome and the provider is **never called**. A layer
built without a manager keeps the previous behavior — pacing is additive.

Pacing is an optimization, never a gate on data honesty: a provider with no
declared limit only gets a concurrency cap; no requests/minute is invented.

## Crypto (`retrieval/crypto.py`)

Crypto is not an equity: a bare `BTC` is ambiguous across quote currencies and a
crypto ticker can collide with an equity ticker. `is_crypto()` (in
`structured.py`) is the ONE classifier; the dedicated `CryptoSource` owns crypto
requests and the vault/live provider refuses them. The TS `crypto_market_data`
capability resolves the pair via the SHARED `classifyIdentifier` and fetches
through the existing crypto connector, returning base/quote so identity rides
every object.

## Evidence & calculations

Every observation carries value + unit + currency + timestamps + period +
instrument identity + source reference. Cross-source disagreement is preserved
(`retrieval/conflicts.py`, surfaced as `conflicts`). Deterministic calculations
live in `finance_facts/` and `research/calculations.py`; a derived value is never
presented as a provider-reported fact.

## Security

- A credential **value** never crosses into Python. The registry holds only the
  env-var name; `GET /financial/providers` reports presence only, and the front
  door merges the vault presence server-side.
- Custom/external requests reuse the existing SSRF-hardened transport.
- All routes are operator-gated (`require_operator`).

## Data usage / licensing

Each descriptor records `usage` (license, attribution, redistribution, storage).
This is an operator statement about a provider's terms, not a legal conclusion.
A provider absent from the registry is not routable.

## Tests

- `python/tests/test_provider_gateway.py` — registry, rate limits + layer
  integration, crypto source + routing, and the gateway agent tools.
- `python/tests/test_retrieval*.py` — the underlying layer (contract, planner,
  scenarios, health, conflicts, cache, validation).
- `src/lib/harness/data-bridge-gateway.test.ts` — the `crypto_market_data` and
  `provider_key_status` bridge capabilities.
