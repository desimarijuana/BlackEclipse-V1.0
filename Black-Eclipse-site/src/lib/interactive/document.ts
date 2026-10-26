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

// Structural defaults only (plus a theme-aware thin scrollbar). The PALETTE
// belongs to the app: the model chooses
// any colours (light or dark) from the user's context, and nothing here forces
// a text colour, a colour-scheme or a background. `background:transparent` lets
// the chat's glass show through until the app paints its own.
const BASE_CSS = `
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;min-height:100%}
html{
  scrollbar-width:thin;
  scrollbar-color:rgba(148,163,184,.5) transparent;
  scrollbar-color:color-mix(in srgb,currentColor 32%,transparent) transparent;
}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{
  background:rgba(148,163,184,.5);
  background:color-mix(in srgb,currentColor 30%,transparent);
  border-radius:999px;border:2px solid transparent;background-clip:padding-box;
}
::-webkit-scrollbar-thumb:hover{
  background:rgba(148,163,184,.7);
  background:color-mix(in srgb,currentColor 48%,transparent);
  background-clip:padding-box;
}
::-webkit-scrollbar-corner{background:transparent}
body{
  font:13px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  background:transparent;-webkit-font-smoothing:antialiased;padding:12px;
  overscroll-behavior:contain;
}
button,input,select,textarea{font:inherit}
/* Off-screen pause: CSS animation work stops while the card is out of view. */
html[data-eclipse-visible="false"] *,
html[data-eclipse-visible="false"] *::before,
html[data-eclipse-visible="false"] *::after{animation-play-state:paused !important}
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

/** Host context the app may read; the palette stays the app's choice. */
export interface InteractiveContext {
  theme?: 'dark' | 'light';
  reducedMotion?: boolean;
  locale?: string;
}

export interface ComposeInteractiveInput {
  html: string;
  css?: string;
  js?: string;
  data?: Record<string, unknown>;
  context?: InteractiveContext;
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
 *   Eclipse.bars()          → Promise<Bar[]> (bars only; [] when unavailable)
 *   Eclipse.onData(fn)      → subscribe, returns unsubscribe
 *   Eclipse.resize(height)  → ask the host to resize the frame
 *   Eclipse.context         → { theme, reducedMotion, locale } (live)
 *   Eclipse.visible         → false while the card is off-screen
 *   Eclipse.onVisibility(fn)→ subscribe to that flag
 * `window.ECLIPSE_DATA` holds static, user-supplied constants.
 */
function bootstrapScript(nonce: string, data: unknown, context: InteractiveContext): string {
  return `(function(){
var NONCE=${jsonForScript(nonce)};
var CONTEXT=${jsonForScript(context)};
function applyContext(next){
  CONTEXT=next||{};
  window.ECLIPSE_CONTEXT=CONTEXT;
  try{if(window.Eclipse)window.Eclipse.context=CONTEXT;}catch(err){}
  try{
    if(CONTEXT.theme){document.documentElement.setAttribute('data-theme',CONTEXT.theme);}
    else{document.documentElement.removeAttribute('data-theme');}
  }catch(err){}
}
applyContext(CONTEXT);
var VISIBLE=true;
var visibilityListeners=[];
var pausedFrames=[];
var nativeRAF=typeof window.requestAnimationFrame==='function'?window.requestAnimationFrame.bind(window):null;
function notifyVisibility(){for(var i=0;i<visibilityListeners.length;i++){try{visibilityListeners[i](VISIBLE);}catch(err){console.error(err);}}}
function applyVisibility(next){
  VISIBLE=!!next;
  try{document.documentElement.setAttribute('data-eclipse-visible',VISIBLE?'true':'false');}catch(err){}
  try{if(window.Eclipse)window.Eclipse.visible=VISIBLE;}catch(err){}
  if(VISIBLE&&pausedFrames.length){
    var queued=pausedFrames.slice();pausedFrames=[];
    for(var i=0;i<queued.length;i++){try{nativeRAF?nativeRAF(queued[i]):setTimeout(queued[i],0);}catch(err){}}
  }
  notifyVisibility();
}
applyVisibility(true);
if(nativeRAF){
  window.requestAnimationFrame=function(cb){
    if(!VISIBLE){pausedFrames.push(cb);return 0;}
    return nativeRAF(cb);
  };
}
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
  context:CONTEXT,
  visible:VISIBLE,
  onVisibility:function(fn){
    visibilityListeners.push(fn);
    try{fn(VISIBLE);}catch(err){console.error(err);}
    return function(){var i=visibilityListeners.indexOf(fn);if(i>=0)visibilityListeners.splice(i,1);};
  },
  resize:function(height){post({type:'eclipse:resize',nonce:NONCE,height:height});},
  onData:function(fn){
    listeners.push(fn);
    if(pending){try{fn(pending);}catch(err){console.error(err);}}
    return function(){var i=listeners.indexOf(fn);if(i>=0)listeners.splice(i,1);};
  },
  data:function(){return pending?Promise.resolve(pending):ready;},
  bars:function(){return (pending?Promise.resolve(pending):ready).then(function(envelope){return envelope&&envelope.bars?envelope.bars:[];});}
};
window.addEventListener('message',function(event){
  var message=event.data;
  if(!message||message.nonce!==NONCE)return;
  if(message.type==='eclipse:context'){applyContext(message.context);return;}
  if(message.type==='eclipse:visibility'){applyVisibility(message.visible);return;}
  if(message.type!=='eclipse:data')return;
  deliver(message.envelope);
});
// Surface a runtime failure to the host card instead of leaving a silent blank.
window.addEventListener('error',function(event){
  post({type:'eclipse:error',nonce:NONCE,message:String((event&&event.message)||event)});
});
window.addEventListener('unhandledrejection',function(event){
  var reason=event&&event.reason;
  post({type:'eclipse:error',nonce:NONCE,message:String((reason&&reason.message)||reason||'Unhandled rejection')});
});
// Report the content height so the card can fit the app (the host clamps it).
var lastHeight=0;
var sizeQueued=false;
function reportSize(){
  sizeQueued=false;
  try{
    var h=Math.ceil((document.body&&document.body.scrollHeight)||0);
    if(h>0&&Math.abs(h-lastHeight)>4){lastHeight=h;post({type:'eclipse:resize',nonce:NONCE,height:h});}
  }catch(err){}
}
function queueSize(){if(sizeQueued)return;sizeQueued=true;setTimeout(reportSize,60);}
window.addEventListener('load',queueSize);
if(typeof ResizeObserver==='function'){
  try{var ro=new ResizeObserver(queueSize);ro.observe(document.documentElement);if(document.body)ro.observe(document.body);}catch(err){}
}
post({type:'eclipse:ready',nonce:NONCE});
setTimeout(reportSize,50);
})();`;
}

/** Compose the full sandboxed document. */
export function composeInteractiveDocument(input: ComposeInteractiveInput): string {
  const { head, body } = splitInteractiveDocument(input.html);
  const css = input.css ? `\n${input.css}` : '';
  const js = input.js ? escapeScriptEnd(input.js) : '';
  const bootstrap = escapeScriptEnd(bootstrapScript(input.nonce, input.data, input.context ?? {}));
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
