---
title: Learning Research Engine
status: Current
last-verified: 2026-10-12
---

# Learning Research Engine

**Who this is for:** anyone asking "how does Eclipse research the internet for
courses, videos, docs and books, and build a learning roadmap I can follow and
track?"

The Learning Research Engine is Eclipse's **education-resource discovery and
curriculum** capability. It reuses the existing Evidence-Driven Web Research
Engine (`docs/harness/web-research-engine.md`) rather than competing with it:
the same provider registry, the same SSRF-hardened bridge transport, the same
untrusted-content boundary and the same tool registry. It adds the learning
domain vocabulary, real education connectors, a deterministic curriculum engine,
durable progress, and one interactive chat block.

## What is new vs reused

| Concern | Reused | Added by this capability |
|---|---|---|
| Provider abstraction | `research/web_providers.py` (`SearchProviderRegistry`) | education connectors reached over the bridge |
| Intent / planning | `research/web_intent.py`, `web_planner.py` | `ResearchIntent.LEARNING`, learning query templates |
| Source typing / ranking | `research/web_sources.py` | `VIDEO`/`COURSE`/`REPOSITORY`/`DOCUMENTATION`/`DATASET`/`TUTORIAL`/`PODCAST` types + a `learning` rank table |
| Tool registry | `harness/tools.py` | 10 learning tools (`research/education_tools.py`) |
| Bridge transport | `src/lib/harness/data-bridge.ts` | `playlist_search`, `video_metadata`, `transcript_fetch`, `course_search`, `github_search` + a YouTube-first `video_search` |
| Persistence | `eclipse-memory.db` (migration 30) | `LearningPath`, `LearningNodeProgress`, `LearningPreference` + `LearningStore` |
| Chat rendering | `src/lib/response/` | the interactive `learning_map` block |

## The learning domain vocabulary

`SourceType` gains first-class learning types, and `youtube.com` is classified
`VIDEO` (not `SOCIAL`) so ranking can treat a coherent lecture series as
authoritative for a learning objective. `ResearchIntent.LEARNING` is triggered by
phrases like "learn", "tutorial", "course", "roadmap", "from scratch",
"prerequisite". The `learning` ranking table orders:
documentation → course → video → academic → repository → dataset → tutorial →
industry → news → podcast → blog → wiki → forum → social.

## Real connectors (no fabricated results)

- **YouTube Data API v3** (`src/lib/education-connectors.ts`,
  `youtubeSearch`/`youtubeVideoMetadata`): requires `YOUTUBE_API_KEY`. It returns
  canonical watch/playlist/channel URLs, and duration/statistics from
  `videos.list` only — never inferred from a title. Without a key the connector
  reports `not_configured` and the bridge falls back to the keyless media
  connector; it never scrapes or invents a video id.
- **GitHub REST search** (`githubSearch`): keyless (an optional `GITHUB_TOKEN`
  raises the rate limit).
- **Courses** (`courseSearch`): a source-restricted search over an explicit
  allowlist of established course providers (Coursera, edX, MIT OCW, Khan
  Academy, …); results not hosted on an allowlisted provider are dropped.
- **Transcripts** (`youtubeTranscript`): YouTube exposes no keyless official
  transcript endpoint, so this returns `UNAVAILABLE` unless a compliant provider
  is configured via `YOUTUBE_TRANSCRIPT_API_URL`. It never scrapes timedtext or
  fabricates a transcript.

Every connector returns the normalized `WebSearchResult[]` + a
`RetrievalDiagnostic`, so the Python registry treats them uniformly and falls back
to web search when one is unavailable.

## The curriculum engine (`research/learning.py`)

Deterministic and model-free. The **agent** proposes the skill decomposition
(names, objectives, prerequisites, exercises, projects, assessment criteria);
the **engine** validates and assembles it:

- `build_curriculum` attaches resources to skills by transparent relevance,
  derives the prerequisite edges, and runs `validate_curriculum`.
- `validate_curriculum` reports (never silently hides): circular dependencies,
  missing prerequisite references, skills with no resource (an explicit gap),
  milestones with no assessment/exercise, skills with no objectives and
  disconnected skills.
- `detect_cycles` / `topological_order` (Kahn's algorithm) enforce the DAG.
- `rank_resource`/`rank_resources` produce an **explainable** score from named,
  weighted components (authority, relevance, depth, accessibility, verification);
  it is an internal ordering signal, never a claim of absolute quality.

## Persistence (`eclipse-memory.db`, migration 30)

Learning paths, per-node progress and durable preferences live in
`eclipse-memory.db` — the same control database as user memory — via
`research/learning_store.py` (`LearningStore`), which rides the ONE existing
`EclipseMemoryStore` connection. `LearningPath.payload` holds the full curriculum
JSON; `LearningNodeProgress` holds per-node status/assessment. Progress is never
written to `jdds.db` (market data) or `agent-memory.db` (run traces).

## Tools (registered on the ONE registry)

`video_metadata`, `playlist_search`, `transcript_fetch`, `course_search`,
`github_search`, `resource_verify`, `resource_rank`, `learning_path_build`,
`learning_progress_get`, `learning_progress_update`. All are in
`WEB_RESEARCH_TOOLS` (`agents.py`). `learning_path_build` performs a bounded
multi-source discovery when no resources are supplied, so a single call can
produce a complete, persisted roadmap.

## Chat rendering — the `learning_map` block

`src/components/response/learning-map-block.tsx` renders the curriculum as
prerequisite-ordered stages. Each skill node carries objective/exercise/assessment
detail, clickable resource links (with type + duration + thumbnail), and a
completion toggle. When the block carries a `pathId`, the toggle POSTs to
`/api/learning/progress`, which proxies to the Python `/learning/progress` route
and the SAME durable store the agent writes through — so a completion the user
clicks and one the agent records can never disagree. An "alternatives" action
re-enters the existing agent loop (`onFollowup`). A compact text outline is the
fallback. No generated image is ever used in place of the real graph.

## HTTP surface

- Bridge capabilities (front door): `playlist_search`, `video_metadata`,
  `transcript_fetch`, `course_search`, `github_search` (plus the YouTube-first
  `video_search`).
- Python routes: `python/harness/routers/learning.py` (`/learning/paths`,
  `/learning/progress`, `/learning/preferences`), operator-gated.
- Next.js proxy: `src/app/api/learning/[[...path]]/route.ts`.

## Configuration

| Env var | Purpose | Required? |
|---|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 video/playlist/channel discovery + metadata | optional (falls back to keyless media connector) |
| `GITHUB_TOKEN` | Higher GitHub search rate limit | optional (keyless works) |
| `YOUTUBE_TRANSCRIPT_API_URL` | A compliant transcript provider | optional (transcripts are otherwise UNAVAILABLE) |

Provider keys can also be set through the settings vault; presence is checked via
`resolveProviderKey`, so no secret ever crosses into the Python runtime.

## Tests

- Python: `tests/test_learning_engine.py`, `test_learning_store.py`,
  `test_learning_tools.py`.
- TypeScript: `src/lib/education-connectors.test.ts`, plus the `learning_map`
  cases in `src/lib/response/contract-blocks.test.ts`.

## Known external dependencies

Live YouTube discovery requires `YOUTUBE_API_KEY`; live transcripts require a
compliant `YOUTUBE_TRANSCRIPT_API_URL`. Everything else (curriculum assembly,
ranking, persistence, rendering, progress) works without external credentials.
