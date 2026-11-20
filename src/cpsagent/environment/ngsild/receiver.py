"""A small HTTP server on the host that receives the broker's NGSI-LD notifications.

The broker runs in a container and POSTs each notification to
`http://host.docker.internal:<port>/notify` (Docker Desktop maps that name to the host; on
Linux `docker-compose.yml` maps it with `host-gateway`). The receiver only queues the
notified entities, each with the instant it arrived; the store takes them from the queue
on its own thread, so the environment's control logic never runs on the server's thread.
"""

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

Notified = tuple[int, dict[str, Any]]  # (arrival, perf_counter_ns), notified entity


class NotificationReceiver:
    def __init__(self, listen_host: str = "127.0.0.1", port: int = 0) -> None:
        """`port` 0: any free port (the subscription is created after the receiver)."""
        self.entities: queue.Queue[Notified] = queue.Queue()
        received = self.entities

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                arrived = time.perf_counter_ns()
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length))
                except ValueError:
                    self.send_response(400)
                    self.end_headers()
                    return
                for entity in body.get("data", []):
                    received.put((arrived, entity))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args: Any) -> None:  # no line per notification
                pass

        self._server = ThreadingHTTPServer((listen_host, port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="ngsi-ld-notifications", daemon=True
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()
