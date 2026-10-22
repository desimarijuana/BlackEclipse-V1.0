"use client";

// ── A formula, typeset ──────────────────────────────────────────────────────
//
// The chat's Markdown used to render a formula as raw text (`$x^2$` came out
// as literal characters). This renders it properly with KaTeX.
//
// The library is loaded ON DEMAND (`import("katex")`), so the chat's initial
// bundle does not carry it - it arrives with the first formula. Its stylesheet
// is global (`src/app/katex.css`), not a component import, so the app's own
// build owns it. Until it
// loads, the formula shows as its own source, which is honest and readable;
// a formula that KaTeX cannot parse shows the same way, never a crash.

import { useEffect, useState } from "react";

export function MathFormula({
  value,
  display = false,
}: {
  value: string;
  display?: boolean;
}) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("katex")
      .then((mod) => {
        if (cancelled) return;
        const katex = mod.default ?? mod;
        try {
          // `throwOnError: false` renders an unparsable formula as its own
          // source in red - a broken formula is visible, not fatal.
          setHtml(katex.renderToString(value, { throwOnError: false, displayMode: display }));
        } catch {
          setHtml(null);
        }
      })
      .catch(() => {
        // The library could not load: the source stays visible.
      });
    return () => {
      cancelled = true;
    };
  }, [value, display]);

  if (html === null) {
    return (
      <code
        className={
          display
            ? "block whitespace-pre-wrap rounded-md border border-border/40 bg-accent/20 px-2 py-1 font-mono text-[0.9em]"
            : "rounded border border-border/40 bg-accent/20 px-1 font-mono text-[0.9em]"
        }
      >
        {value}
      </code>
    );
  }

  return (
    <span
      className={display ? "math-block my-1 overflow-x-auto" : "math-inline"}
      // KaTeX escapes its input; `trust` is off, so no HTML is injected.
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default MathFormula;
