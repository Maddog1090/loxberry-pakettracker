"""Lokaler HTTP-Testserver: beantwortet Requests der Reihe nach aus einer Warteschlange."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class _Handler(BaseHTTPRequestHandler):
    server: "FakeServer"

    def _handle(self):
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append({"method": self.command, "path": url.path, "query": parse_qs(url.query),
                                     "headers": self.headers, "body": body})
        status, payload, headers, delay = self.server.responses.pop(0) if self.server.responses else (500, b"", {}, 0)
        if delay:
            time.sleep(delay)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except OSError:
            pass

    do_GET = do_POST = _handle

    def log_message(self, *args):
        pass


class FakeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests: list = []
        self.responses: list = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def respond(self, *items):
        """items: (status, body[, headers[, delay]]) – body als dict/list (JSON) oder bytes."""
        self.requests = []
        self.responses = []
        for item in items:
            status, body, headers, delay = (list(item) + [{}, 0])[:4]
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.responses.append((status, body, headers, delay))


_server = None


def server() -> FakeServer:
    global _server
    if _server is None:
        _server = FakeServer()
    return _server
