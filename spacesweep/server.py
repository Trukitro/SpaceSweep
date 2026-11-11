"""Browser mode: serve the same UI on 127.0.0.1 when no native window is wanted
(or WebView2 is missing). The API is exposed as POST /api/<method>.

Because this API can delete files, every call must carry a per-run secret
token (injected into the page), and the Host header must be local. A web page
from another origin can neither read the token nor send the custom header
without a CORS preflight, which this server never approves.
"""

import json
import mimetypes
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UI_DIR = None


def _handler(api, token, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(403, {"error": "bad host"})
            rel = self.path.split("?", 1)[0].lstrip("/") or "index.html"
            full = os.path.normpath(os.path.join(UI_DIR, rel))
            if not full.startswith(os.path.normpath(UI_DIR) + os.sep) or not os.path.isfile(full):
                return self._send(404, {"error": "not found"})
            with open(full, "rb") as fh:
                data = fh.read()
            if rel == "index.html":
                data = data.replace(b"__SS_TOKEN__", token.encode())
            self._send(200, data, mimetypes.guess_type(full)[0] or "application/octet-stream")

        def do_POST(self):
            if self.headers.get("Host") not in allowed_hosts or not secrets.compare_digest(
                    self.headers.get("X-SS-Token", ""), token):
                return self._send(403, {"error": "forbidden"})
            name = self.path.split("?", 1)[0].removeprefix("/api/")
            method = getattr(api, name, None)
            if name.startswith("_") or not callable(method):
                return self._send(404, {"error": f"unknown method {name}"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                args = json.loads(self.rfile.read(length) or b"[]")
                return self._send(200, {"ok": True, "result": method(*args)})
            except Exception as exc:
                return self._send(200, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return Handler


def serve(api, ui_dir, port=0, open_browser=True):
    global UI_DIR
    UI_DIR = ui_dir
    token = secrets.token_urlsafe(24)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = _handler(api, token, port)
    url = f"http://127.0.0.1:{port}/"
    print(f"SpaceSweep running at {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
