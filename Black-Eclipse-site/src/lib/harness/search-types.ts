// Unified Retrieval / Search Intelligence — shared client types.
// Mirrors the Python result contract in `python/harness/search/contracts.py`.

export interface SearchCitation {
  label: string;
  documentId: string;
  chunkId: string;
  sourceType: string;
  sourceId: string;
  uri: string | null;
  section: string | null;
  page: number | null;
  publishedAt: string | null;
  retrievedAt: string | null;
  quote: string;
}

export interface SearchProvenance {
  sourceType: string;
  sourceId: string;
  documentId: string;
  chunkId: string;
  section: string | null;
  page: number | null;
  uri: string | null;
  publisher: string | null;
  authority: number;
  trust: string;
  method: string;
}

export interface SearchHit {
  id: string;
  content: string;
  score: number;
  vectorScore: number | null;
  keywordScore: number | null;
  rerankScore: number | null;
  kind: string;
  entity: { type: string; id: string; name: string } | null;
  timestamps: { publishedAt: string | null; retrievedAt: string | null; effectiveAt: string | null };
  provenance: SearchProvenance;
  citation: SearchCitation;
  metadata: Record<string, unknown>;
  neighbors: Record<string, unknown> | null;
}

export interface SearchStats {
  candidates: number;
  vectorCandidates: number;
  keywordCandidates: number;
  returned: number;
  deduped: number;
  elapsedMs: number;
  embeddingMs: number;
  rerankMs: number;
  cacheHits: number;
  semanticAvailable: boolean;
  reranked: boolean;
  expanded: boolean;
  fallback: string | null;
}

export interface SearchResult {
  type: "search_result";
  query: string;
  normalizedQuery: string;
  expandedQuery: string | null;
  mode: string;
  method: string;
  hits: SearchHit[];
  warnings: string[];
  stats: SearchStats;
  queryId: string;
}

export interface SearchQueryBody {
  query: string;
  mode?: "semantic" | "keyword" | "hybrid";
  top_k?: number;
  namespace?: string;
  namespaces?: string[];
  source_types?: string[];
  entity_type?: string;
  entity_id?: string;
  workspace_id?: string;
  owner_id?: string;
  as_of?: string;
  published_from?: string;
  published_to?: string;
  rerank?: boolean;
  neighbor?: boolean;
  expansion?: string;
  min_score?: number;
  route?: boolean;
  unrestricted?: boolean;
}

export interface SearchDocumentRow {
  documentId: string;
  sourceType: string;
  sourceId: string;
  namespace: string;
  title: string;
  state: string;
  visibility: string;
  chunkCount: number;
  publishedAt: string | null;
  updatedAt: string;
  indexedAt: string | null;
  metadata: Record<string, unknown>;
}

export interface EmbeddingSuggestion {
  provider: string;
  model: string;
  dimensions: number;
  label: string;
  credentialsReady: boolean;
  local: boolean;
}

export interface EmbeddingResolution {
  state:
    | 'active'
    | 'no_provider'
    | 'unsupported_provider'
    | 'missing_model'
    | 'missing_credentials'
    | 'unreachable'
    | 'unavailable';
  source: 'explicit' | 'env' | 'run' | 'none';
  available: boolean;
  reason: string;
  hint: string;
  provider: string;
  model: string;
  dimensions: number;
  distanceMetric: string;
  suggestions: EmbeddingSuggestion[];
}

export interface SearchAdminStats {
  available?: boolean;
  embedding: {
    available: boolean;
    reason: string;
    provider: string;
    model: string;
    version: string;
    dimensions: number;
    distanceMetric: string;
    cache: { entries: number; hits: number; misses: number };
    lastStats: Record<string, number>;
    resolution: EmbeddingResolution;
    savedConfig: Record<string, unknown>;
  };
  index: {
    path: string;
    schemaVersion: number;
    annBackend: boolean;
    documents: number;
    chunks: number;
    vectors: number;
    cacheEntries: number;
    jobs: Record<string, number>;
    states: Record<string, number>;
    vectorModels: Array<{ modelKey: string; provider: string; model: string; version: string; dims: number; n: number }>;
  };
  search: { recentQueries: number; avgLatencyMs: number; embeddingFailures: number };
  config: { defaultMode: string; defaultTopK: number; chunkStrategy: string; rerankEnabled: boolean };
}

export interface SearchEventRow {
  id: number;
  kind: string;
  queryId: string | null;
  runId: string | null;
  namespace: string | null;
  mode: string | null;
  latencyMs: number | null;
  candidates: number | null;
  results: number | null;
  cacheHit: number;
  provider: string | null;
  model: string | null;
  createdAt: string;
}
