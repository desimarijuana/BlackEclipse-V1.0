"""A local, deterministic browser test application (stdlib only).

A single-threaded `http.server` bound to loopback serving the routes the browser
acceptance test drives: /login, /forms, /tables, /modal, /dialog, /iframe,
/upload, /download, /dynamic, /infinite-scroll, /network-error, /console-error,
/navigation, /popup, /auth. No external website is required, so the browser
integration tests are deterministic and offline.

Usage in a test:

    with BrowserTestApp() as app:
        url = app.url("/login")
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

PAGE_HEAD = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head><body>"""


def _page(title: str, body: str, script: str = "") -> bytes:
    return (
        PAGE_HEAD.format(title=title) + body
        + (f"<script>{script}</script>" if script else "")
        + "</body></html>"
    ).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    app: "BrowserTestApp"

    def log_message(self, *args) -> None:  # noqa: ANN002 - silence the test server
        pass

    def _send(self, body: bytes, *, status: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server contract
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        self.app.record_request("GET", self.path)

        if path == "/":
            self._send(_page("Home", '<h1>Eclipse Browser Test</h1><a href="/login">Login</a>'))
        elif path == "/login":
            body = (
                '<h1>Sign in</h1>'
                '<form action="/auth" method="get">'
                '<label for="user">Username</label>'
                '<input id="user" name="user" placeholder="Username">'
                '<label for="pass">Password</label>'
                '<input id="pass" name="pass" type="password" placeholder="Password">'
                '<button id="login-btn" type="submit">Sign in</button>'
                '</form>'
            )
            self._send(_page("Login", body))
        elif path == "/auth":
            user = (query.get("user") or [""])[0]
            self._send(_page("Dashboard", f'<h1>Welcome, {user}</h1><div id="dash">Signed in</div>'))
        elif path == "/forms":
            body = (
                '<h1>Form controls</h1>'
                '<label for="name">Full name</label><input id="name" name="name">'
                '<label for="plan">Plan</label>'
                '<select id="plan" name="plan"><option value="basic">Basic</option>'
                '<option value="pro">Pro</option></select>'
                '<label><input type="checkbox" id="tos" name="tos"> Accept terms</label>'
                '<button id="save">Save</button><div id="result" aria-live="polite"></div>'
                ''
            )
            script = (
                "document.getElementById('save').addEventListener('click',()=>{"
                "document.getElementById('result').textContent='Saved: '+"
                "document.getElementById('name').value+' / '+document.getElementById('plan').value+' / '+"
                "(document.getElementById('tos').checked?'tos':'no-tos');});"
            )
            self._send(_page("Forms", body, script))
        elif path == "/tables":
            rows = "".join(f"<tr><td>Row {i}</td><td>{i * 10}</td></tr>" for i in range(1, 6))
            self._send(_page("Table", f"<h1>Data</h1><table id='t'><tr><th>Name</th><th>Value</th></tr>{rows}</table>"))
        elif path == "/modal":
            body = (
                '<h1>Modal</h1><button id="open">Open modal</button>'
                '<div id="overlay" style="display:none" role="dialog" aria-modal="true">'
                '<div role="document"><h2>Are you sure?</h2>'
                '<button id="confirm">Confirm</button><button id="cancel">Cancel</button></div></div>'
                '<div id="state"></div>'
            )
            script = (
                "document.getElementById('open').onclick=()=>{document.getElementById('overlay').style.display='block';};"
                "document.getElementById('confirm').onclick=()=>{document.getElementById('overlay').style.display='none';document.getElementById('state').textContent='confirmed';};"
                "document.getElementById('cancel').onclick=()=>{document.getElementById('overlay').style.display='none';document.getElementById('state').textContent='cancelled';};"
            )
            self._send(_page("Modal", body, script))
        elif path == "/dialog":
            script = (
                "function fire(kind){if(kind==='confirm'){window.__r=window.confirm('Proceed?');}"
                "else if(kind==='alert'){window.alert('Notice');}else{window.__r=window.prompt('Name','');}}"
            )
            body = (
                '<h1>Dialogs</h1>'
                '<button id="alert">Alert</button>'
                '<button id="confirm">Confirm</button>'
                '<button id="prompt">Prompt</button>'
                '<button id="close-dialog">Close window</button>'
            )
            script += "document.getElementById('alert').onclick=()=>fire('alert');"
            script += "document.getElementById('confirm').onclick=()=>fire('confirm');"
            script += "document.getElementById('prompt').onclick=()=>fire('prompt');"
            script += "document.getElementById('close-dialog').onclick=()=>window.close();"
            self._send(_page("Dialogs", body, script))
        elif path == "/iframe":
            body = '<h1>Frames</h1><iframe id="frame" src="/iframe-inner" title="inner"></iframe>'
            self._send(_page("Frames", body))
        elif path == "/iframe-inner":
            self._send(_page("Inner", '<h2>Inner frame</h2><button id="inner-btn">Inner button</button><input id="inner-input">'))
        elif path == "/upload":
            body = '<h1>Upload</h1><input id="file" type="file"><button id="send">Send</button><div id="status"></div>'
            self._send(_page("Upload", body))
        elif path == "/download":
            body = '<h1>Download</h1><a id="dl" href="/download-file" download>Download report</a>'
            self._send(_page("Download", body))
        elif path == "/download-file":
            payload = b"quarter,revenue\nQ1,1000\nQ2,2000\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="report.csv"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif path == "/dynamic":
            body = '<h1>Dynamic</h1><button id="load">Load items</button><div id="list"></div>'
            script = (
                "document.getElementById('load').onclick=()=>{"
                "setTimeout(()=>{const d=document.getElementById('list');"
                "d.innerHTML='<div class=\"item\">Alpha</div><div class=\"item\">Beta</div>';},400);};"
            )
            self._send(_page("Dynamic", body, script))
        elif path == "/infinite-scroll":
            script = (
                "let n=0;function add(){const c=document.getElementById('feed');"
                "for(let i=0;i<10;i++){n++;const el=document.createElement('div');el.className='row';el.textContent='Item '+n;c.appendChild(el);}}"
                "add();window.addEventListener('scroll',()=>{if(window.innerHeight+window.scrollY>=document.body.offsetHeight-100){add();}});"
            )
            self._send(_page("Scroll", '<h1>Feed</h1><div id="feed"></div>', script))
        elif path == "/network-error":
            script = (
                "fetch('/missing-endpoint').catch(()=>{document.getElementById('s').textContent='failed';});"
            )
            self._send(_page("Network", '<h1>Network</h1><div id="s">loading</div>', script))
        elif path == "/missing-endpoint":
            self._send(b"not found", status=404, ctype="text/plain")
        elif path == "/console-error":
            script = "console.error('intentional console error');throw new Error('intentional page error');"
            self._send(_page("Console", '<h1>Console</h1>', script))
        elif path == "/navigation":
            self._send(_page("Nav", '<h1>First</h1><a id="go" href="/navigation-second">Go next</a>'))
        elif path == "/navigation-second":
            self._send(_page("Second", '<h1 id="second">Second page</h1>'))
        elif path == "/popup":
            script = "document.getElementById('pop').onclick=()=>window.open('/popup-target','_blank');"
            self._send(_page("Popup", '<h1>Popup</h1><button id="pop">Open window</button>', script))
        elif path == "/popup-target":
            self._send(_page("PopupTarget", '<h1 id="pt">Popup target</h1>'))
        elif path == "/challenge":
            self._send(_page("Verify", '<h1>Please verify you are human</h1><div class="captcha">Complete the CAPTCHA</div>'))
        elif path.startswith("/echo"):
            self._send(json.dumps({"path": path, "query": query}).encode("utf-8"), ctype="application/json")
        else:
            self._send(_page("404", "<h1>Not found</h1>"), status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.app.record_request("POST", self.path)
        if parsed.path == "/submit":
            self._send(_page("Submitted", "<h1>Submitted</h1><div id='ok'>ok</div>"))
        elif parsed.path == "/upload":
            self._send(_page("Uploaded", "<h1>Uploaded</h1>"))
        else:
            self._send(b"{}", ctype="application/json")


class BrowserTestApp:
    """A running local HTTP server for browser tests."""

    def __init__(self) -> None:
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.requests: list[tuple[str, str]] = []

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.server_address[1]

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def record_request(self, method: str, path: str) -> None:
        self.requests.append((method, path))

    def __enter__(self) -> "BrowserTestApp":
        handler = type("BoundHandler", (_Handler,), {"app": self})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


__all__ = ["BrowserTestApp"]
