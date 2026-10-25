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

/**
 * Models sometimes emit a whole document instead of body markup. Keep the body
 * (so their markup still renders) and drop the outer shell; the composer owns
 * `<head>`, including the CSP, so a model can never replace the policy.
 */
export function extractBodySource(html: string): string {
  const body = /<body\b[^>]*>([\s\S]*?)<\/body\s*>/i.exec(html);
  if (body) return body[1];
  return html
    .replace(/<!doctype[^>]*>/gi, '')
    .replace(/<head\b[^>]*>[\s\S]*?<\/head\s*>/gi, '')
    .replace(/<\/?html\b[^>]*>/gi, '')
    .replace(/<\/?body\b[^>]*>/gi, '')
    .trim();
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
  const body = extractBodySource(input.html);
  const css = input.css ? `\n${input.css}` : '';
  const js = input.js ? escapeScriptEnd(input.js) : '';
  const bootstrap = escapeScriptEnd(bootstrapScript(input.nonce, input.data));
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="${INTERACTIVE_CSP}">
<style>${BASE_CSS}${css}</style>
</head>
<body>
<script>${bootstrap}</script>
${body}
${js ? `<script>${js}</script>` : ''}
</body>
</html>`;
}
