const list = await (await fetch('http://127.0.0.1:9334/json')).json();
const page = list.find((t) => t.type === 'page' && t.url.includes('3100'));
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => { ws.onopen = r; });
let id = 0;
function send(method, params) {
  const my = ++id;
  return new Promise((resolve) => {
    const h = (e) => { const m = JSON.parse(e.data); if (m.id === my) { ws.removeEventListener('message', h); resolve(m); } };
    ws.addEventListener('message', h);
    ws.send(JSON.stringify({ id: my, method, params }));
  });
}
const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true })).result?.result?.value;
console.log(await evaluate(`localStorage.setItem('be_window_glass_v1','0'), 'off'`));
await evaluate(`location.reload()`);
await new Promise((r) => setTimeout(r, 5000));
console.log('glass class:', await evaluate(`document.documentElement.classList.contains('glass-window')`));
ws.close();
