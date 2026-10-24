"""Deterministic loopback fixtures. No filesystem or upstream network access."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_SIZE = 64 * 1024 * 1024
ROUTES = ("/stable.bin", "/drop-once.bin", "/changed.bin", "/ignore-range.bin")


def data_at(version: int, start: int, count: int) -> bytes:
    """Generate an exact slice without allocating the entire representation."""
    pattern = hashlib.sha256(f"resume-fixture/v{version}".encode("ascii")).digest()
    offset = start % len(pattern)
    return (pattern * ((offset + count + len(pattern) - 1) // len(pattern)))[
        offset : offset + count
    ]


def digest(size: int, version: int) -> str:
    result = hashlib.sha256()
    for start in range(0, size, 65536):
        result.update(data_at(version, start, min(65536, size - start)))
    return result.hexdigest()


def parse_range(value: str | None, size: int) -> tuple[int, int] | None:
    """Inclusive bounds; None = ignored syntax; (-1,-1) = unsatisfiable."""
    if value is None or len(value) > 256:
        return None
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", value.strip(), re.IGNORECASE)
    if not match or not any(match.groups()):
        return None
    first, last = match.groups()
    if first:
        start = int(first)
        end = int(last) if last else size - 1
        if last and end < start:
            return None
        if start >= size:
            return (-1, -1)
        return start, min(end, size - 1)
    suffix = int(last)
    if suffix == 0:
        return (-1, -1)
    return max(0, size - suffix), size - 1


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 0, size: int = 65536, drop_after: int = 4096):
        if type(size) is not int or not 2 <= size <= MAX_SIZE:
            raise ValueError(f"size must be 2..{MAX_SIZE}")
        if type(drop_after) is not int or not 1 <= drop_after < size:
            raise ValueError("drop_after must be 1..size-1")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("port must be 0..65535")
        self.size = size
        self.drop_after = drop_after
        self.hashes = {v: digest(size, v) for v in (1, 2)}
        self.tags = {v: f'"{self.hashes[v]}"' for v in (1, 2)}
        self.state_lock = threading.Lock()
        self.stats = {route: {"gets": 0, "drops": 0} for route in ROUTES}
        super().__init__(("127.0.0.1", port), FixtureHandler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def manifest(self) -> dict:
        return {
            "schema_version": 1,
            "size": self.size,
            "drop_after": self.drop_after,
            "sha256": {f"v{v}": self.hashes[v] for v in (1, 2)},
            "etag": {f"v{v}": self.tags[v] for v in (1, 2)},
            "routes": list(ROUTES),
        }


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "resume-fixture/0.1.0"
    sys_version = ""
    server: FixtureServer

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        """Do not record URLs, headers or user-controlled strings."""

    def _headers(self, status: int, length: int | None, headers: dict | None = None):
        self.send_response(status)
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        if length is not None:
            self.send_header("Content-Length", str(length))
        for key, value in (headers or {}).items():
            self.send_header(key, str(value))
        self.end_headers()
        self.close_connection = True

    def _json(self, value):
        body = json.dumps(value, sort_keys=True).encode("utf-8")
        self._headers(200, len(body), {"Content-Type": "application/json"})
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self._serve()

    def do_GET(self):
        try:
            self._serve()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True

    def _serve(self):
        if self.path == "/manifest.json":
            self._json(self.server.manifest())
            return
        if self.path == "/stats.json":
            with self.server.state_lock:
                snapshot = {key: dict(value) for key, value in self.server.stats.items()}
            self._json(snapshot)
            return
        if self.path not in ROUTES:
            self._headers(404, 0)
            return

        server = self.server
        with server.state_lock:
            state = server.stats[self.path]
            version = 2 if self.path == "/changed.bin" and state["drops"] else 1
            tag = server.tags[version]
            extra = {
                "ETag": tag,
                "Accept-Ranges": "bytes",
                "Content-Type": "application/octet-stream",
            }
            condition = self.headers.get_all("If-None-Match", [])
            if condition and any(
                item.strip() == "*" or item.strip().removeprefix("W/") == tag
                for item in ",".join(condition).split(",")
            ):
                self._headers(304, None, extra)
                return
            range_headers = self.headers.get_all("Range", [])
            selected = None
            if self.command == "GET" and self.path != "/ignore-range.bin":
                # Duplicate or multipart ranges are deliberately ignored.
                if len(range_headers) == 1:
                    selected = parse_range(range_headers[0], server.size)
                if_range = self.headers.get_all("If-Range", [])
                if if_range and if_range != [tag]:
                    selected = None
            if selected == (-1, -1):
                extra["Content-Range"] = f"bytes */{server.size}"
                self._headers(416, 0, extra)
                return
            start, end = selected if selected is not None else (0, server.size - 1)
            status = 206 if selected is not None else 200
            length = end - start + 1
            drop = (
                self.command == "GET"
                and status == 200
                and self.path in ("/drop-once.bin", "/changed.bin")
                and state["drops"] == 0
            )
            if self.command == "GET":
                state["gets"] += 1
                if drop:
                    state["drops"] += 1
        if selected is not None:
            extra["Content-Range"] = f"bytes {start}-{end}/{server.size}"
        self._headers(status, length, extra)
        if self.command == "HEAD":
            return
        remaining = server.drop_after if drop else length
        for offset in range(start, start + remaining, 65536):
            self.wfile.write(data_at(version, offset, min(65536, start + remaining - offset)))
        self.wfile.flush()
        # A short body with the original Content-Length models an interrupted transfer.
        # The connection closes when this handler returns.


@contextmanager
def running_fixture(size=65536, drop_after=4096):
    server = FixtureServer(size=size, drop_after=drop_after)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
