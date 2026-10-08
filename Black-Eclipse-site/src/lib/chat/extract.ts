// Text extraction for documents added as agent context.
//
// The agentic runtime is deliberately read-only (every tool is `read`, and the
// tool registry hard-rejects writes), so documents reach the agent by having
// their text extracted here and injected into the run input — not by giving the
// agent filesystem access.
//
// Coverage: any text file (docs, data, and source code), PDFs (real fonts via
// pdfjs), Office documents (docx/xlsx/pptx and OpenDocument odt/ods/odp, plus
// epub — all ZIP+XML), RTF, and a readable-string scan for old binary Office
// (.doc/.xls) and unknown formats. A genuinely binary file (an image, an
// archive) reports "no readable text" rather than being fed to the model as
// mojibake; it is never a flat "unsupported".

import { inflateSync } from "node:zlib";
import { inflateRawSync } from "node:zlib";
import { SESSION_LIMITS } from "./session-types";

// Every file type whose bytes are already (or trivially become) readable text.
// Code files are text too — rejecting `.py`/`.js`/`.sql` made no sense for a
// coding agent. This list is deliberately broad; the UTF-8 fallback below also
// catches anything not named here.
const TEXT_EXTENSIONS = new Set([
  // docs / data
  "txt", "text", "md", "markdown", "mdx", "rst", "csv", "tsv", "json", "jsonl",
  "ndjson", "log", "yml", "yaml", "xml", "html", "htm", "xhtml", "svg", "sql",
  "ini", "cfg", "conf", "toml", "env", "properties", "diff", "patch",
  // code
  "py", "pyi", "ipynb", "js", "mjs", "cjs", "jsx", "ts", "tsx", "mts", "cts",
  "rs", "go", "java", "kt", "kts", "scala", "c", "h", "cc", "cpp", "cxx", "hpp",
  "cs", "rb", "php", "swift", "m", "mm", "pl", "pm", "lua", "r", "jl", "dart",
  "sh", "bash", "zsh", "fish", "ps1", "bat", "cmd", "makefile", "mk", "gradle",
  "dockerfile", "tf", "hcl", "proto", "graphql", "gql", "vue", "svelte", "astro",
  "css", "scss", "sass", "less", "tex", "bib", "v", "vh", "vhd", "clj", "cljs",
  "ex", "exs", "erl", "hs", "elm", "zig", "nim", "groovy", "vb",
  // mail / markup-ish
  "eml", "mbox", "rtf", "vtt", "srt", "ics",
]);

// Office documents are ZIP archives of XML. They are extremely common finance
// files, so they get real extraction (not "unsupported"): docx → the document
// body text, xlsx → the shared strings (the cell text a reader would see).
// ODT/ODS/ODP (OpenDocument) and EPUB are the same shape with different internal
// paths — handled by `OFFICE_ZIP_PARTS` below.
const OFFICE_ZIP_EXTENSIONS = new Set(["docx", "xlsx", "pptx", "odt", "ods", "odp", "epub"]);

// The ZIP member(s) to read, per extension, in priority order.
const OFFICE_ZIP_PARTS: Record<string, string[]> = {
  docx: ["word/document.xml"],
  pptx: ["ppt/slides/slide1.xml"],
  xlsx: ["xl/sharedStrings.xml"],
  odt: ["content.xml"],
  ods: ["content.xml"],
  odp: ["content.xml"],
  epub: ["OEBPS/content.xhtml", "OEBPS/nav.xhtml", "content.xhtml"],
};

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

/**
 * True when the file has a chance of yielding text. This is now almost always
 * true: unknown/no-extension files are SNIFFED at extraction time (text is read,
 * binary is scanned for strings), so the UI should not pre-label them
 * unsupported. It only returns false for a known-binary image/archive extension
 * that the extractor will honestly report as having no readable text.
 */
export function isTextExtractable(name: string): boolean {
  const ext = extensionOf(name);
  if (!ext) return true;
  return !KNOWN_BINARY_EXTENSIONS.has(ext);
}

// Types we know are binary containers (media/archives/executables): extraction
// still runs (readable-string scan) but the flag is honest up front.
const KNOWN_BINARY_EXTENSIONS = new Set([
  "png", "jpg", "jpeg", "gif", "bmp", "webp", "ico", "tif", "tiff", "heic",
  "mp3", "wav", "flac", "ogg", "m4a", "aac", "mp4", "mov", "avi", "mkv", "webm",
  "zip", "gz", "tar", "rar", "7z", "bz2", "xz", "exe", "dll", "so", "dylib",
  "bin", "iso", "dmg", "class", "pyc", "o", "obj", "woff", "woff2", "ttf", "otf",
]);

// Old binary Office (`.doc`/`.xls`/`.ppt`) and `.pages`/`.numbers`/`.key`: not
// ZIP+XML, so a best-effort readable-string scan runs instead of refusing.
const EXTRA_ZIP_TEXT_EXTENSIONS = new Set([
  "doc", "xls", "ppt", "pages", "numbers", "key", "msg", "vsd",
  "odg", "odf", "ots", "otp",
]);

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
  if (entries.length === 0) {
    // Not a ZIP we can read (an old binary .doc/.xls, or a password-protected
    // file). Fall back to a readable-string scan rather than refusing.
    return extractReadableStrings(buf);
  }
  // Reject a zip bomb before inflating anything.
  const declared = entries.reduce((sum, e) => sum + e.uncompressedSize, 0);
  if (declared > MAX_UNCOMPRESSED_BYTES) {
    return { ok: false, note: "Document too large to read" };
  }
  // The known member(s) for this type, else every .xml/.xhtml member.
  let wanted = OFFICE_ZIP_PARTS[ext] ?? [];
  if (wanted.length === 0) {
    wanted = entries
      .filter((e) => /\.(xml|xhtml|html)$/i.test(e.name))
      .map((e) => e.name);
  }
  const chunks: string[] = [];
  let total = 0;
  for (const want of wanted) {
    const entry = entries.find((e) => e.name === want);
    if (!entry) continue;
    const data = readZipEntry(buf, entry);
    if (!data) continue;
    const xml = data.toString("utf8");
    // <w:t>text</w:t> (docx), <a:t>text</a:t> (pptx), <t>text</t> (xlsx),
    // and OpenDocument's <text:p>…</text:p> paragraphs.
    const re = /<(?:w|a|m|text)?:?(?:t|p|h)(?:\s[^>]*)?>([\s\S]*?)<\/(?:w|a|m|text)?:?(?:t|p|h)>/g;
    for (const m of xml.matchAll(re)) {
      const text = decodeXml(m[1].replace(/<[^>]+>/g, ""));
      if (!text.trim()) continue;
      chunks.push(text);
      total += text.length + 1;
      if (total > SESSION_LIMITS.maxDocChars) break;
    }
    if (total > SESSION_LIMITS.maxDocChars) break;
  }
  if (chunks.length === 0) return extractReadableStrings(buf);
  // Preserve paragraph breaks so the prose is legible.
  const joined = chunks.join(" ").replace(/[ \t]{2,}/g, " ");
  return bound(joined);
}

/**
 * A best-effort readable-text scan for a binary document we cannot structurally
 * parse (old `.doc`/`.xls`, a malformed ZIP, a scanned file). Pulls runs of
 * printable ASCII/UTF-8 so the model gets SOMETHING rather than "unsupported".
 * Honest: if nothing readable is found it says so.
 */
function extractReadableStrings(buf: Buffer): ExtractResult {
  const text = buf.toString("utf8");
  const runs = text.match(/[\x20-\x7e\u00a0-\uffff]{4,}/g) ?? [];
  const joined = runs.join(" ").replace(/\s{3,}/g, "  ");
  if (joined.trim().length < 8) {
    return { ok: false, note: "No readable text found (a scanned or binary file)" };
  }
  return bound(joined);
}

/** A UTF-8 text fallback for anything not in the known lists. */
function extractPlainText(bytes: Uint8Array): ExtractResult {
  const buf = Buffer.from(bytes);
  // A NUL byte in the first 8 KB is the standard "this is binary" signal.
  const probe = buf.subarray(0, Math.min(buf.length, 8192));
  if (probe.includes(0)) return extractReadableStrings(buf);
  const text = buf.toString("utf8").replace(/^\uFEFF/, "");
  // If decoding produced a lot of replacement chars, treat as binary.
  const bad = (text.match(/\uFFFD/g) || []).length;
  if (text.length > 0 && bad / text.length > 0.1) return extractReadableStrings(buf);
  // Reject content that is only control characters (e.g. bytes 1,2,3) — that is
  // not text, however well it decodes.
  const printable = (text.match(/[\t\n\r\x20-\x7e\u00a0-\uffff]/g) || []).length;
  if (text.length > 0 && printable / text.length < 0.8) return extractReadableStrings(buf);
  return bound(text);
}

/** Strip the lightest RTF control words so an `.rtf` reads as prose. */
function extractRtfText(bytes: Uint8Array): ExtractResult {
  let text = Buffer.from(bytes).toString("latin1");
  text = text
    .replace(/\\'([0-9a-f]{2})/gi, (_m, h: string) => String.fromCharCode(parseInt(h, 16)))
    .replace(/\\par[d]?\b/g, "\n")
    .replace(/\\[a-z]+-?\d* ?/gi, " ")
    .replace(/[{}]/g, "")
    .replace(/\\\*/g, "");
  return bound(text);
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
  if (ext === "rtf") return extractRtfText(bytes);
  // Old binary Office / unknown binary-ish containers: readable-string scan.
  if (EXTRA_ZIP_TEXT_EXTENSIONS.has(ext)) return extractReadableStrings(Buffer.from(bytes));
  if (!TEXT_EXTENSIONS.has(ext)) {
    // No extension, or an extension we do not know: sniff it. Text → read it;
    // binary → readable-string scan. Never a flat "unsupported" refusal for a
    // file whose bytes are actually text.
    return extractPlainText(bytes);
  }
  let text = Buffer.from(bytes).toString("utf8");
  // Markdown/HTML: strip the noisiest markup so the model reads prose, not
  // tags. (A full renderer would be overkill for context injection.)
  if (ext === "html" || ext === "htm" || ext === "xhtml") {
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
    type PdfTextItem = { str?: string; hasEOL?: boolean };
    type PdfPage = { getTextContent: () => Promise<{ items: PdfTextItem[] }> };
    type PdfDocument = {
      numPages: number;
      getPage: (n: number) => Promise<PdfPage>;
      destroy: () => Promise<void>;
    };
    type PdfjsModule = {
      GlobalWorkerOptions: { workerSrc: string };
      getDocument: (opts: Record<string, unknown>) => { promise: Promise<PdfDocument> };
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
