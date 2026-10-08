// ─────────────────────────────────────────────────────────────────────────────
// Document run view — the right-sidebar read model for document intelligence.
//
// The Python runtime collects every `document_*` tool result into a bounded run
// blob (`DocumentCollector.to_blob()`), carried on the run record and
// `client.final`. This module is a small, defensive coercion of that blob into a
// typed view the UI renders. Nothing here talks to the network and nothing is
// fabricated: an absent/odd shape yields null (no panel) rather than an empty
// panel pretending a document was understood.
// ─────────────────────────────────────────────────────────────────────────────

import type { DocumentRunDocument, DocumentRunInfo } from './types';

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function document(raw: unknown): DocumentRunDocument | null {
  if (!isRecord(raw)) return null;
  const documentId = typeof raw.documentId === 'string' ? raw.documentId : '';
  if (!documentId) return null;
  const capabilities = isRecord(raw.capabilities)
    ? (Object.fromEntries(
        Object.entries(raw.capabilities).map(([k, v]) => [k, String(v)]),
      ) as Record<string, string>)
    : undefined;
  const pages = Array.isArray(raw.pages)
    ? (raw.pages.filter(isRecord).map((p) => ({
        ...(typeof p.index === 'number' ? { index: p.index } : {}),
        ...(typeof p.label === 'string' ? { label: p.label } : {}),
        ...(typeof p.textMethod === 'string' ? { textMethod: p.textMethod } : {}),
      })) as DocumentRunDocument['pages'])
    : undefined;
  const entities = Array.isArray(raw.entities)
    ? (raw.entities.filter(isRecord).map((e) => ({
        ...(typeof e.type === 'string' ? { type: e.type } : {}),
        ...(typeof e.value === 'string' ? { value: e.value } : {}),
        ...(typeof e.confidence === 'number' ? { confidence: e.confidence } : {}),
      })) as DocumentRunDocument['entities'])
    : undefined;
  const currentContext = isRecord(raw.currentContext)
    ? {
        ...(typeof raw.currentContext.section === 'string' ? { section: raw.currentContext.section } : {}),
        ...(typeof raw.currentContext.page === 'number' ? { page: raw.currentContext.page } : {}),
        ...(Array.isArray(raw.currentContext.path) ? { path: raw.currentContext.path as string[] } : {}),
      }
    : null;
  return {
    documentId,
    ...(typeof raw.kind === 'string' ? { kind: raw.kind } : {}),
    ...(typeof raw.version === 'number' ? { version: raw.version } : {}),
    ...(typeof raw.title === 'string' ? { title: raw.title } : {}),
    ...(typeof raw.fileName === 'string' ? { fileName: raw.fileName } : {}),
    ...(typeof raw.state === 'string' ? { state: raw.state } : {}),
    ...(capabilities ? { capabilities } : {}),
    ...(typeof raw.pageCount === 'number' ? { pageCount: raw.pageCount } : {}),
    ...(typeof raw.sheetCount === 'number' ? { sheetCount: raw.sheetCount } : {}),
    ...(typeof raw.confidence === 'number' ? { confidence: raw.confidence } : {}),
    ...(typeof raw.textMethod === 'string' ? { textMethod: raw.textMethod } : {}),
    ...(typeof raw.chunkCount === 'number' ? { chunkCount: raw.chunkCount } : {}),
    ...(typeof raw.tableCount === 'number' ? { tableCount: raw.tableCount } : {}),
    ...(typeof raw.imageCount === 'number' ? { imageCount: raw.imageCount } : {}),
    ...(typeof raw.entityCount === 'number' ? { entityCount: raw.entityCount } : {}),
    ...(typeof raw.evidenceCount === 'number' ? { evidenceCount: raw.evidenceCount } : {}),
    currentContext,
    ...(pages ? { pages } : {}),
    ...(entities ? { entities } : {}),
    ...(Array.isArray(raw.warnings) ? { warnings: raw.warnings as string[] } : {}),
  };
}

/** Coerce a run's raw document blob into a typed view, or null when absent. */
export function coerceDocumentRun(raw: unknown): DocumentRunInfo | null {
  if (!isRecord(raw)) return null;
  const documents = Array.isArray(raw.documents)
    ? (raw.documents.map(document).filter(Boolean) as DocumentRunDocument[])
    : [];
  const failures = Array.isArray(raw.failures) ? raw.failures : [];
  if (documents.length === 0 && failures.length === 0) return null;
  return {
    ...(typeof raw.type === 'string' ? { type: raw.type } : {}),
    status: typeof raw.status === 'string' ? raw.status : 'collected',
    count: typeof raw.count === 'number' ? raw.count : documents.length,
    documents,
    failures: (failures as DocumentRunInfo['failures']) ?? null,
  };
}

/** The single most recent document the panel focuses on. */
export function primaryDocument(run: DocumentRunInfo | null): DocumentRunDocument | null {
  if (!run || run.documents.length === 0) return null;
  return run.documents[run.documents.length - 1];
}
