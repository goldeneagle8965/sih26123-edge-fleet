"""Spectator dashboard. Does not assign tasks, paths, or right-of-way."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from simulation.engine import FleetSim

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "frontend" / "static"
RESULTS = ROOT / "results" / "metrics.json"


class Dashboard:
    def __init__(self, sim: FleetSim) -> None:
        self.sim = sim
        self.lock = threading.Lock()
        self.httpd: ThreadingHTTPServer | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            snap = self.sim.snapshot()
        snap["measured"] = _load_measured()
        return snap

    def handle_action(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            action = body.get("action")
            if action == "pause":
                self.sim.paused = True
            elif action == "resume":
                self.sim.paused = False
            elif action == "reset":
                self.sim.reset()
            elif action == "block_aisle":
                cell = self.sim.block_aisle()
                return {"ok": True, "cell": list(cell)}
            elif action == "toggle":
                x, y = int(body["x"]), int(body["y"])
                on = self.sim.toggle_block(x, y)
                return {"ok": True, "blocked": on, "cell": [x, y]}
            elif action == "policy":
                pol = str(body.get("policy", "ubpa"))
                if pol in ("ubpa", "stop_wait"):
                    self.sim.policy = pol
                    self.sim.reset()
            elif action == "radio":
                radio = self.sim.set_radio(
                    drop_prob=body.get("drop_prob"),
                    delay=body.get("delay"),
                )
                return {"ok": True, **radio}
        return {"ok": True}


def _load_measured() -> dict[str, Any] | None:
    if not RESULTS.exists():
        return None
    try:
        return json.loads(RESULTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def make_handler(dash: Dashboard):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                fp = STATIC / "index.html"
                self._send(200, fp.read_bytes(), "text/html; charset=utf-8")
                return
            if path == "/state":
                payload = json.dumps(dash.snapshot()).encode("utf-8")
                self._send(200, payload, "application/json")
                return
            if path.startswith("/static/"):
                rel = path[len("/static/") :]
                fp = (STATIC / rel).resolve()
                if STATIC.resolve() not in fp.parents and fp != STATIC.resolve():
                    self._send(403, b"forbidden", "text/plain")
                    return
                if not fp.exists():
                    self._send(404, b"missing", "text/plain")
                    return
                ctype = "text/plain"
                if fp.suffix == ".css":
                    ctype = "text/css"
                elif fp.suffix == ".js":
                    ctype = "application/javascript"
                self._send(200, fp.read_bytes(), ctype)
                return
            self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, b'{"ok":false}', "application/json")
                return
            out = json.dumps(dash.handle_action(body)).encode("utf-8")
            self._send(200, out, "application/json")

    return Handler


def serve(dash: Dashboard, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(dash))
    dash.httpd = httpd
    return httpd
