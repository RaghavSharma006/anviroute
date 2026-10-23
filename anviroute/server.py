"""Authenticated local API; complete JSON upstream, Anthropic SSE locally."""

import hmac
import socket
import sys
import time
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .common import BridgeError, read_body, send_json

from .api import UpstreamError, events


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        # Windows otherwise permits two HTTPServer instances to share a port.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, port, api, token):
        self.api, self.model, self.token = api, api.model, token
        self.last_error = None
        super().__init__(("127.0.0.1", port), Handler)

    def report_error(self, status, message):
        self.last_error = message
        print(f"\n[AnviRoute] HTTP {status}: {message}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    def route_path(self):
        return urlsplit(self.path).path

    def request_api(self):
        return self.server.api

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
        if self.route_path() != "/v1/models":
            send_json(self, 404, {"error": "Unknown route"})
            return
        api = self.request_api()
        if api is None:
            send_json(self, 503, {'error': 'Saved model is unavailable'})
            return
        model = api.model
        send_json(self, 200, {"data": [{"id": model, "type": "model", "display_name": model,
                                      "created_at": "2026-01-01T00:00:00Z"}],
                              "has_more": False, "first_id": model, "last_id": model})

    def do_POST(self):
        if not self.authorized():
            return
        path = self.route_path()
        if path not in ("/v1/messages", "/v1/messages/count_tokens"):
            send_json(self, 404, {"error": "Unknown route"})
            return
        try:
            api = self.request_api()
            if api is None:
                raise BridgeError('Saved model was removed. Open AnviRoute and add it again.')
            payload = read_body(self)
            if not isinstance(payload, dict):
                raise BridgeError("Expected a JSON object")
            if path.endswith("/count_tokens"):
                send_json(self, 200, api.count_tokens(payload))
                return
            started = time.monotonic()
            result = api.complete(payload)
            if hasattr(self.server, 'record'):
                elapsed = round(time.monotonic() - started, 2)
                usage = result.get('usage', {})
                self.server.record('adapter', f'Response in {elapsed}s; input {usage.get("input_tokens", 0)}, output {usage.get("output_tokens", 0)} tokens; {len(payload.get("tools", []))} tools', status=200)
                self.request_diagnostic(True, 'Inference completed', seconds=elapsed, input_tokens=usage.get('input_tokens', 0), output_tokens=usage.get('output_tokens', 0))
            if not payload.get("stream"):
                send_json(self, 200, result)
                return
            # Build before sending headers so invalid response blocks yield a clean error.
            frames = list(events(result))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            for frame in frames:
                self.wfile.write(frame)
                self.wfile.flush()
        except (BridgeError, KeyError, TypeError, ValueError) as exc:
            status = exc.status if isinstance(exc, UpstreamError) else 502
            error_type = "authentication_error" if status in (401, 403) else "api_error"
            message = str(exc) if isinstance(exc, BridgeError) else "Invalid message or upstream response"
            self.server.report_error(status, message)
            self.request_diagnostic(False, message)
            send_json(self, status, {"type": "error", "error": {"type": error_type,
                                                                "message": message}})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True

    def request_diagnostic(self, ok, message, **metrics):
        if hasattr(self.server, 'diagnostic'):
            path = urlsplit(self.path).path
            identifier = path.split('/', 3)[2] if path.startswith('/p/') else self.server.active
            self.server.diagnostic(identifier, ok, message, **metrics)
