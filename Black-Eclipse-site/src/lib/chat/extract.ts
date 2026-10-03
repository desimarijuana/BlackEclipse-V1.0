// Text extraction for documents added as agent context.
//
// The agentic runtime is deliberately read-only (every tool is `read`, and the
// tool registry hard-rejects writes), so documents reach the agent by having
// their text extracted here and injected into the run input — not by giving the
// agent filesystem access.
//
// Supported today: plain text, Markdown, CSV, JSON, and simple PDFs (text
// streams only, no OCR). Unknown/binary types are rejected rather than being
// fed to the model as mojibake.

import { inflateSync } from "node:zlib";
import { inflateRawSync } from "node:zlib";
import { SESSION_LIMITS } from "./session-types";

const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "csv", "tsv", "json", "log", "yml", "yaml",
  "xml", "html", "htm", "sql", "ini", "cfg", "toml",
]);

// Office documents are ZIP archives of XML. They are extremely common finance
// files, so they get real extraction (not "unsupported"): docx → the document
// body text, xlsx → the shared strings (the cell text a reader would see).
const OFFICE_ZIP_EXTENSIONS = new Set(["docx", "xlsx", "pptx"]);

export interface ExtractResult {
  ok: boolean;
  text?: string;
  /** Present when `ok` is false, or when the text was truncated. */
  note?: string;
}

export function extensionOf(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx === -1 ? "" : name.slice(idx + 1).toLowerCase();
}

/** True when we can turn the file into text the model can read. */
export function isTextExtractable(name: string): boolean {
  const ext = extensionOf(name);
  return TEXT_EXTENSIONS.has(ext) || ext === "pdf" || OFFICE_ZIP_EXTENSIONS.has(ext);
}

// ── Minimal ZIP reader (no dependency) ──────────────────────────────────────
// docx/xlsx/pptx are ZIP archives. We read the central directory, find the
// entries we want, and inflate their raw DEFLATE streams. No entries are
// written; nothing is extracted to disk. Bounded to avoid a zip bomb.

const MAX_ZIP_ENTRIES = 2_000;
const MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024;

interface ZipEntry {
  name: string;
  method: number;
  compressedSize: number;
  uncompressedSize: number;
  localHeaderOffset: number;
}

function readZipEntries(buf: Buffer): ZipEntry[] {
  // Find End Of Central Directory (EOCD): signature 0x06054b50, scanned from end.
  let eocd = -1;
  const minEocd = Math.max(0, buf.length - 65_557);
  for (let i = buf.length - 22; i >= minEocd; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd === -1) return [];
  const count = buf.readUInt16LE(eocd + 10);
  const cdOffset = buf.readUInt32LE(eocd + 16);
  const entries: ZipEntry[] = [];
  let p = cdOffset;
  for (let n = 0; n < Math.min(count, MAX_ZIP_ENTRIES); n++) {
    if (p + 46 > buf.length || buf.readUInt32LE(p) !== 0x02014b50) break;
    const method = buf.readUInt16LE(p + 10);
    const compressedSize = buf.readUInt32LE(p + 20);
    const uncompressedSize = buf.readUInt32LE(p + 24);
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commentLen = buf.readUInt16LE(p + 32);
    const localHeaderOffset = buf.readUInt32LE(p + 42);
    const name = buf.toString("utf8", p + 46, p + 46 + nameLen);
    entries.push({ name, method, compressedSize, uncompressedSize, localHeaderOffset });
    p += 46 + nameLen + extraLen + commentLen;
  }
  return entries;
}

function readZipEntry(buf: Buffer, entry: ZipEntry): Buffer | null {
  const lh = entry.localHeaderOffset;
  if (lh + 30 > buf.length || buf.readUInt32LE(lh) !== 0x04034b50) return null;
  const nameLen = buf.readUInt16LE(lh + 26);
  const extraLen = buf.readUInt16LE(lh + 28);
  const dataStart = lh + 30 + nameLen + extraLen;
  const data = buf.subarray(dataStart, dataStart + entry.compressedSize);
  if (entry.method === 0) return Buffer.from(data);
  if (entry.method === 8) {
    try { return inflateRawSync(data); } catch { return null; }
  }
  return null;
}

const XML_ENTITIES: Record<string, string> = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", "#39": "'", "#34": '"',
};

function decodeXml(text: string): string {
  return text
    .replace(/&#(\d+);/g, (_m, d: string) => String.fromCodePoint(parseInt(d, 10)))
    .replace(/&#x([0-9a-f]+);/gi, (_m, h: string) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&([a-z#0-9]+);/gi, (m, e: string) => XML_ENTITIES[e.toLowerCase()] ?? m);
}

/**
 * Extract text from a docx/xlsx/pptx (a ZIP of XML). docx/pptx: the `<w:t>` /
 * `<a:t>` runs become the prose. xlsx: `<t>` shared strings and inline strings
 * become the cell text. Best-effort and bounded — a scanned or exotic file just
 * yields no text.
 */
function extractOfficeText(buf: Buffer, ext: string): ExtractResult {
  const entries = readZipEntries(buf);
  if (entries.length === 0) return { ok: false, note: "Not a readable document" };
  // Reject a zip bomb before inflating anything.
  const declared = entries.reduce((sum, e) => sum + e.uncompressedSize, 0);
  if (declared > MAX_UNCOMPRESSED_BYTES) {
    return { ok: false, note: "Document too large to read" };
  }
  // Prefer the specific XML parts, in document order.
  const wanted = ext === "xlsx"
    ? ["xl/sharedStrings.xml"]
    : ["word/document.xml", "ppt/slides/slide1.xml"];
  const chunks: string[] = [];
  let total = 0;
  for (const want of wanted) {
    const entry = entries.find((e) => e.name === want);
    if (!entry) continue;
    const data = readZipEntry(buf, entry);
    if (!data) continue;
    const xml = data.toString("utf8");
    // <w:t>text</w:t> (docx), <a:t>text</a:t> (pptx), <t>text</t> (xlsx)
    const re = /<(?:w|a|m)?:?t(?:\s[^>]*)?>([\s\S]*?)<\/(?:w|a|m)?:?t>/g;
    for (const m of xml.matchAll(re)) {
      const text = decodeXml(m[1]);
      if (!text) continue;
      chunks.push(text);
      total += text.length + 1;
      if (total > SESSION_LIMITS.maxDocChars) break;
    }
    if (total > SESSION_LIMITS.maxDocChars) break;
  }
  // Preserve paragraph breaks so the prose is legible.
  const joined = chunks.join(" ").replace(/[ \t]{2,}/g, " ");
  return bound(joined);
}

/** Reject empty or absurdly long extracted text before it reaches a prompt. */
function bound(text: string): ExtractResult {
  const trimmed = text.trim();
  if (!trimmed) return { ok: false, note: "No extractable text" };
  if (trimmed.length > SESSION_LIMITS.maxDocChars) {
    return {
      ok: true,
      text: trimmed.slice(0, SESSION_LIMITS.maxDocChars),
      note: `Truncated to ${SESSION_LIMITS.maxDocChars.toLocaleString()} chars`,
    };
  }
  return { ok: true, text: trimmed };
}

/**
 * Extract the text streams from a simple PDF (uncompressed or Flate-decoded
 * `Tj`/`TJ` operators). This is intentionally minimal — enough for generated
 * reports and exports. Scanned/image PDFs yield no text and are rejected.
 */
function extractPdfText(bytes: Uint8Array): ExtractResult {
  const raw = Buffer.from(bytes).toString("latin1");
  const chunks: string[] = [];
  // Text-showing operators, e.g. (Hello) Tj  and  [(Hel) -20 (lo)] TJ
  const showRe = /\((?:\\.|[^\\()])*\)/g;
  const operatorRe = /(?:\[[^\]]*\]|\((?:\\.|[^\\()])*\))\s*T[Jj]/g;

  for (const opMatch of raw.matchAll(operatorRe)) {
    const op = opMatch[0];
    const parts: string[] = [];
    for (const litMatch of op.matchAll(showRe)) {
      const literal = litMatch[0].slice(1, -1);
      parts.push(
        literal
          .replace(/\\([nrtbf])/g, (_m, c: string) =>
            c === "n" ? "\n" : c === "r" ? "\r" : c === "t" ? "\t" : c === "b" ? "\b" : "\f"
          )
          .replace(/\\([()\\])/g, "$1")
          .replace(/\\(\d{1,3})/g, (_m, oct: string) => String.fromCharCode(parseInt(oct, 8)))
      );
    }
    if (parts.length) chunks.push(parts.join(""));
  }

  // PDFs are usually Flate-compressed; decompress the streams we can find and
  // scan those too. Best-effort — failures are ignored.
  try {
    const streamRe = /stream\r?\n([\s\S]*?)\r?\nendstream/g;
    for (const streamMatch of raw.matchAll(streamRe)) {
      const body = Buffer.from(streamMatch[1], "latin1");
      try {
        const inflated = inflateSync(body).toString("latin1");
        for (const opMatch of inflated.matchAll(operatorRe)) {
          const parts: string[] = [];
          for (const litMatch of opMatch[0].matchAll(showRe)) {
            parts.push(litMatch[0].slice(1, -1).replace(/\\([()\\])/g, "$1"));
          }
          if (parts.length) chunks.push(parts.join(""));
        }
      } catch {
        // Not a Flate stream — skip.
      }
    }
  } catch {
    // zlib unavailable — the uncompressed pass above still ran.
  }

  const text = chunks.join("\n").replace(/\n{3,}/g, "\n\n");
  return bound(text);
}

/** Extract readable text from an uploaded document. */
export function extractText(name: string, bytes: Uint8Array): ExtractResult {
  const ext = extensionOf(name);
  if (ext === "pdf") return extractPdfText(bytes);
  if (OFFICE_ZIP_EXTENSIONS.has(ext)) return extractOfficeText(Buffer.from(bytes), ext);
  if (!TEXT_EXTENSIONS.has(ext)) {
    return { ok: false, note: `Unsupported file type: .${ext || "unknown"}` };
  }
  let text = Buffer.from(bytes).toString("utf8");
  // Markdown/HTML: strip the noisiest markup so the model reads prose, not
  // tags. (A full renderer would be overkill for context injection.)
  if (ext === "html" || ext === "htm") {
    text = text
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">");
  }
  // Drop a UTF-8 BOM if present.
  text = text.replace(/^\uFEFF/, "");
  return bound(text);
}

// ── Real PDF extraction (pdfjs-dist) ────────────────────────────────────────
// A hand-rolled regex reader only works on simple PDFs with ASCII text streams.
// Real-world PDFs (reports, decks, filings) use CID/Identity-H fonts where the
// text is stored as glyph ids — those yielded NOTHING, the file was silently
// skipped, and the agent told the user "nothing is attached". pdfjs-dist decodes
// fonts properly, so it is the PDF path; the regex reader stays as the fallback
// when pdfjs cannot load (keeping the module usable in a minimal environment).

const MAX_PDF_PAGES = 200;

async function extractPdfWithLib(bytes: Uint8Array): Promise<ExtractResult | null> {
  try {
    // pdfjs copies `data` into its own buffer. A Node Buffer is a Uint8Array
    // VIEW over a shared (pooled) ArrayBuffer, so passing it directly makes
    // pdfjs read the whole pool — corrupting the document. Hand it an exact,
    // standalone copy.
    const data = new Uint8Array(bytes.byteLength);
    data.set(bytes);
    const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
    // No browser worker in a Node server route. pdfjs runs its parser as a
    // "fake worker" on the main thread, but it still needs the worker MODULE
    // path to import. The package is externalized from the Next bundle
    // (next.config serverExternalPackages), so the file resolves on disk.
    type PdfjsModule = {
      GlobalWorkerOptions: { workerSrc: string };
      getDocument: (opts: Record<string, unknown>) => { promise: Promise<any> };
    };
    const mod = pdfjs as unknown as PdfjsModule;
    try {
      const { createRequire } = await import("node:module");
      const req = createRequire(import.meta.url);
      mod.GlobalWorkerOptions.workerSrc = req.resolve("pdfjs-dist/legacy/build/pdf.worker.mjs");
    } catch {
      // Fall back to whatever the module set; the parse below may still work.
    }
    const doc = await mod.getDocument({
      data,
      // Never evaluate embedded JS; use built-in font maps for CID fonts.
      isEvalSupported: false,
      useSystemFonts: true,
      disableFontFace: true,
    }).promise;
    const parts: string[] = [];
    let total = 0;
    const pageCount = Math.min(doc.numPages, MAX_PDF_PAGES);
    for (let i = 1; i <= pageCount; i++) {
      const page = await doc.getPage(i);
      const content = await page.getTextContent();
      let line = "";
      for (const item of content.items) {
        if ("str" in item && typeof item.str === "string") line += item.str;
        if ("hasEOL" in item && (item as { hasEOL?: boolean }).hasEOL) {
          parts.push(line);
          total += line.length + 1;
          line = "";
          if (total > SESSION_LIMITS.maxDocChars) break;
        }
      }
      if (line) { parts.push(line); total += line.length + 1; }
      if (total > SESSION_LIMITS.maxDocChars) break;
    }
    await doc.destroy();
    const text = parts.join("\n").replace(/[ \t]{2,}/g, " ").replace(/\n{3,}/g, "\n\n");
    return bound(text);
  } catch {
    return null;
  }
}

/**
 * Async document extraction for the server upload/context path. Uses pdfjs for
 * PDFs (real fonts, real text) and the sync extractor for everything else. This
 * is what `loadContextDocuments` calls, so an attached report is actually read.
 */
export async function extractDocumentText(name: string, bytes: Uint8Array): Promise<ExtractResult> {
  if (extensionOf(name) === "pdf") {
    const viaLib = await extractPdfWithLib(bytes);
    if (viaLib) return viaLib;
    // pdfjs unavailable or failed — fall back to the simple reader.
    return extractPdfText(bytes);
  }
  return extractText(name, bytes);
}
