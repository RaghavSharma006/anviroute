"""Loopback Anthropic endpoint: reassembles SSE from authenticated JSON polls."""

import base64
import hmac
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .common import BridgeError, read_body, request, send_json


class Connection:
    def __init__(self, token, url=None, registry=None):
        self.token, self.url, self.registry = token, url, registry
        self.lock = threading.Lock()
        self.updated = 0

    def resolve(self):
        # Refresh for each new generation (at most once every 15s), never mid-generation.
        with self.lock:
            if self.registry and (not self.url or time.monotonic() - self.updated > 15):
                self.url = self.registry.resolve()["url"]
                self.updated = time.monotonic()
            if not self.url:
                raise BridgeError("No remote URL configured")
            return self.url

    def info(self):
        return request(self.resolve() + "/bridge/info", self.token)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, connection, model, token):
        self.remote, self.model, self.token = connection, model, token
        super().__init__(address, LocalHandler)


class LocalHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(45)

    def log_message(self, *args):
        pass

    def authorized(self):
        value = self.headers.get("Authorization", "")
        if not value.isascii() or not hmac.compare_digest(value, "Bearer " + self.server.token):
            send_json(self, 401, {"error": "Invalid local token"})
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        if self.path != "/v1/models":
            send_json(self, 404, {"error": "Unknown route"})
            return
        model = self.server.model
        send_json(self, 200, {"data": [{"id": model, "type": "model", "display_name": model,
                                      "created_at": "2026-01-01T00:00:00Z"}],
                              "has_more": False, "first_id": model, "last_id": model})

    def do_POST(self):
        if not self.authorized():
            return
        if self.path not in ("/v1/messages", "/v1/messages/count_tokens"):
            send_json(self, 404, {"error": "Unknown route"})
            return
        started, job_id, url = False, None, None
        try:
            payload = read_body(self)
            if not isinstance(payload, dict):
                raise BridgeError("Expected JSON object")
            url = self.server.remote.resolve()
            remote_token = self.server.remote.token
            result = request(url + "/bridge/jobs", remote_token,
                             {"path": self.path, "payload": payload})
            job_id = result["id"]
            cursor = 0
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                result = request(f"{url}/bridge/jobs/{job_id}?after={cursor}", remote_token)
                if result["status"] is not None and not started:
                    self.send_response(result["status"])
                    self.send_header("Content-Type", result["content_type"])
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    started = True
                for line in result["lines"]:
                    self.wfile.write(base64.b64decode(line, validate=True))
                self.wfile.flush()
                cursor = result["next"]
                if result["done"]:
                    return
            raise BridgeError("Generation exceeded 30 minute limit")
        except (BridgeError, KeyError, ValueError, TypeError) as exc:
            if not started:
                send_json(self, 502, {"type": "error", "error": {"type": "api_error", "message": str(exc)}})
            else:
                # Closing an incomplete stream makes the failure visible to the client.
                self.close_connection = True
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        finally:
            if job_id:
                try:
                    request(f"{url}/bridge/jobs/{job_id}", self.server.remote.token, method="DELETE", timeout=5)
                except BridgeError:
                    pass
