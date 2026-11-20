"""Shared fixtures: a local HTTP server for the fixture pages, and a headless Runner worker."""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ.setdefault("RUNNER_HEADLESS", "true")

from app.config import Settings  # noqa: E402
from app.events import EventBus  # noqa: E402
from app.worker import Worker  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SLOW_SECONDS = 3


class FixtureHandler(BaseHTTPRequestHandler):
    other_origin = ""  # set by the fixture

    def log_message(self, *args):  # keep test output quiet
        pass

    def send_html(self, body: str, headers: dict | None = None, status: int = 200) -> None:
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/account":
            self.send_response(302)
            self.send_header("Location", "/signin.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/setcookie":
            self.send_html("<p>cookie set</p>", {"Set-Cookie": "session=letmein; Path=/; HttpOnly"})
        elif path == "/whoami":
            logged_in = "session=letmein" in (self.headers.get("Cookie") or "")
            button = "<button>Welcome back</button>" if logged_in else "<a href='/signin.html'>Please sign in</a>"
            self.send_html(f"<!doctype html><main>{button}</main>")
        elif path == "/inject.js":
            body = b"document.body.insertAdjacentHTML('beforeend', '<button id=injected>Injected</button>');"
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/slow":
            # Send the start of the page, then stall so the "load" event comes late.
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<!doctype html><html><body><button id='early'>Early button</button>" + b" " * 2048)
            self.wfile.flush()
            time.sleep(SLOW_SECONDS)
            try:
                self.wfile.write(b"<button id='late'>Late button</button></body></html>")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            file = FIXTURES / path.lstrip("/")
            if path == "/" or not file.is_file():
                self.send_html("<!doctype html><p>not found</p>", status=404)
                return
            self.send_html(file.read_text().replace("{OTHER_ORIGIN}", self.other_origin))


def _serve() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture(scope="session")
def servers():
    """Two fixture servers on different ports, i.e. two different origins."""
    main, main_url = _serve()
    other, other_url = _serve()
    FixtureHandler.other_origin = other_url
    yield main_url, other_url
    main.shutdown()
    other.shutdown()


@pytest.fixture(scope="session")
def base_url(servers):
    return servers[0]


@pytest.fixture
def worker(tmp_path):
    settings = Settings(exchange_dir=tmp_path / "exchange", headless=True, job_timeout_ms=60000, max_crops=300)
    w = Worker(settings, EventBus())
    w.start()
    yield w
    w.stop()
