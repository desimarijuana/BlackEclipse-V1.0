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
import { SESSION_LIMITS } from "./session-types";

const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "csv", "tsv", "json", "log", "yml", "yaml",
  "xml", "html", "htm", "sql", "ini", "cfg", "toml",
]);

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
  return TEXT_EXTENSIONS.has(extensionOf(name)) || extensionOf(name) === "pdf";
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
