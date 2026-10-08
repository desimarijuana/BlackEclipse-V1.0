import { describe, expect, it } from 'vitest';
import { coerceDocumentRun, primaryDocument } from './document-view';

describe('document-view', () => {
  it('returns null for an absent or empty blob', () => {
    expect(coerceDocumentRun(null)).toBeNull();
    expect(coerceDocumentRun(undefined)).toBeNull();
    expect(coerceDocumentRun({})).toBeNull();
    expect(coerceDocumentRun({ status: 'collected', documents: [], failures: [] })).toBeNull();
  });

  it('coerces a collected run blob with a document', () => {
    const run = coerceDocumentRun({
      type: 'documents',
      status: 'collected',
      count: 1,
      documents: [
        {
          documentId: 'doc_abc',
          kind: 'pdf',
          state: 'PARTIALLY_READY',
          title: 'Annual Report',
          pageCount: 184,
          capabilities: { text: 'PASS', tables: 'PASS', images: 'PASS', ocr: 'UNAVAILABLE' },
          currentContext: { section: 'Revenue', page: 47 },
          entities: [{ type: 'financial_metric', value: 'Revenue', confidence: 0.8 }],
          evidenceCount: 3,
        },
      ],
    });
    expect(run).not.toBeNull();
    expect(run?.count).toBe(1);
    const primary = primaryDocument(run);
    expect(primary?.documentId).toBe('doc_abc');
    expect(primary?.capabilities?.ocr).toBe('UNAVAILABLE');
    expect(primary?.currentContext?.section).toBe('Revenue');
    expect(primary?.entities?.[0].value).toBe('Revenue');
  });

  it('keeps failures and yields a null primary when no document succeeded', () => {
    const run = coerceDocumentRun({
      status: 'collected',
      count: 0,
      documents: [],
      failures: [{ kind: 'docx', error: { errorClass: 'MACRO_ENABLED' } }],
    });
    expect(run).not.toBeNull();
    expect(primaryDocument(run)).toBeNull();
  });

  it('drops a document with no id rather than fabricating one', () => {
    const run = coerceDocumentRun({ status: 'collected', count: 1, documents: [{ kind: 'pdf' }] });
    expect(run).toBeNull();
  });
});
