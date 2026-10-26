// ── Interactive document composer ────────────────────────────────────────────
//
// Turns a model-authored `interactive` block into ONE self-contained document
// for a sandboxed iframe. Pure and framework-free so it can be unit tested.
//
// The security boundary is the iframe (`sandbox="allow-scripts"` with no
// `allow-same-origin`) PLUS this CSP. The composer only controls the wrapper:
// once the document is parsed the model's own JS runs, and the CSP keeps it
// offline. `connect-src 'none'` is what stops a widget from exfiltrating
// anything, so it must never become configurable.

const BASE_CSS = `
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{font:13px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#e6e6e6;background:transparent;-webkit-font-smoothing:antialiased;padding:12px;color-scheme:dark}
button,input,select,textarea{font:inherit;color:inherit}
`.trim();

/** The immutable policy delivered with every interactive document. */
export const INTERACTIVE_CSP = [
  "default-src 'none'",
  "script-src 'unsafe-inline'",
  "style-src 'unsafe-inline'",
  "img-src data: blob:",
  "font-src data:",
  "media-src data: blob:",
  "connect-src 'none'",
  "frame-src 'none'",
  "child-src 'none'",
  "worker-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ');

export interface ComposeInteractiveInput {
  html: string;
  css?: string;
  js?: string;
  data?: Record<string, unknown>;
  /** Random per-render value; the widget echoes it on every message so the
   *  host can reject traffic from any other frame. */
  nonce: string;
}

/** JSON safe to embed in an inline `<script>` (no premature `</script>`). */
export function jsonForScript(value: unknown): string {
  return JSON.stringify(value ?? null)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

/** Inline JS must not close the surrounding `<script>` tag early. */
function escapeScriptEnd(source: string): string {
  return source.replace(/<\/script/gi, '<\\/script');
}

interface SplitDocument {
  /** Model head content that is safe to keep (styles, meta, scripts). */
  head: string;
  /** Body markup the composer wraps. */
  body: string;
}

/**
 * Models sometimes emit a whole document instead of body markup. Keep their
 * body AND head styles/scripts (a full document usually carries its CSS in
 * `<head>`), but strip anything that could replace the policy: a model-supplied
 * CSP `<meta>` is removed (ours is authoritative) and `<title>` is dropped (the
 * card already shows a title). The composer still owns `<head>` order.
 */
export function splitInteractiveDocument(html: string): SplitDocument {
  const hasDocumentShell = /<html[\s>]|<!doctype|<head[\s>]|<body[\s>]/i.test(html);
  if (!hasDocumentShell) return { head: '', body: html };

  const headMatch = /<head\b[^>]*>([\s\S]*?)<\/head\s*>/i.exec(html);
  const bodyMatch = /<body\b[^>]*>([\s\S]*?)<\/body\s*>/i.exec(html);

  const head = (headMatch?.[1] ?? '')
    .replace(/<meta[^>]+http-equiv=["']?content-security-policy["']?[^>]*>/gi, '')
    .replace(/<title\b[^>]*>[\s\S]*?<\/title\s*>/gi, '')
    .trim();

  let body = bodyMatch?.[1] ?? html;
  if (!bodyMatch) {
    body = body
      .replace(/<!doctype[^>]*>/gi, '')
      .replace(/<head\b[^>]*>[\s\S]*?<\/head\s*>/gi, '')
      .replace(/<\/?html\b[^>]*>/gi, '')
      .replace(/<\/?body\b[^>]*>/gi, '')
      .trim();
  }

  return { head, body };
}

/** The body markup of a model-supplied document (head is handled separately). */
export function extractBodySource(html: string): string {
  return splitInteractiveDocument(html).body;
}

/**
 * The tiny runtime injected before the widget's own script:
 *   Eclipse.data()          → Promise<dataset envelope> (host-injected)
 *   Eclipse.onData(fn)      → subscribe, returns unsubscribe
 *   Eclipse.resize(height)  → ask the host to resize the frame
 * `window.ECLIPSE_DATA` holds static, user-supplied constants.
 */
function bootstrapScript(nonce: string, data: unknown): string {
  return `(function(){
var NONCE=${jsonForScript(nonce)};
var listeners=[];
var pending=null;
var resolvePending=null;
var ready=new Promise(function(resolve){resolvePending=resolve;});
function deliver(envelope){
  pending=envelope;
  if(resolvePending){resolvePending(envelope);resolvePending=null;}
  for(var i=0;i<listeners.length;i++){try{listeners[i](envelope);}catch(err){console.error(err);}}
}
function post(message){try{parent.postMessage(message,'*');}catch(err){}}
window.ECLIPSE_DATA=${jsonForScript(data)};
window.Eclipse={
  resize:function(height){post({type:'eclipse:resize',nonce:NONCE,height:height});},
  onData:function(fn){
    listeners.push(fn);
    if(pending){try{fn(pending);}catch(err){console.error(err);}}
    return function(){var i=listeners.indexOf(fn);if(i>=0)listeners.splice(i,1);};
  },
  data:function(){return pending?Promise.resolve(pending):ready;}
};
window.addEventListener('message',function(event){
  var message=event.data;
  if(!message||message.type!=='eclipse:data'||message.nonce!==NONCE)return;
  deliver(message.envelope);
});
post({type:'eclipse:ready',nonce:NONCE});
})();`;
}

/** Compose the full sandboxed document. */
export function composeInteractiveDocument(input: ComposeInteractiveInput): string {
  const { head, body } = splitInteractiveDocument(input.html);
  const css = input.css ? `\n${input.css}` : '';
  const js = input.js ? escapeScriptEnd(input.js) : '';
  const bootstrap = escapeScriptEnd(bootstrapScript(input.nonce, input.data));
  // The bootstrap is emitted BEFORE the model's head content so a script in the
  // model's own `<head>` already sees `window.Eclipse`.
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="${INTERACTIVE_CSP}">
<style>${BASE_CSS}${css}</style>
<script>${bootstrap}</script>
${head}
</head>
<body>
${body}
${js ? `<script>${js}</script>` : ''}
</body>
</html>`;
}
