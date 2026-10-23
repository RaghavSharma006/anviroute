"""Authenticated local API; complete JSON upstream, Anthropic SSE locally."""

from http.server import ThreadingHTTPServer

from kagglelink.client import LocalHandler
from kagglelink.common import BridgeError, read_body, send_json

from .api import UpstreamError, events


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, api, token):
        self.api, self.model, self.token = api, api.model, token
        super().__init__(("127.0.0.1", port), Handler)


class Handler(LocalHandler):
    def do_POST(self):
        if not self.authorized():
            return
        if self.path not in ("/v1/messages", "/v1/messages/count_tokens"):
            send_json(self, 404, {"error": "Unknown route"})
            return
        try:
            payload = read_body(self)
            if not isinstance(payload, dict):
                raise BridgeError("Expected a JSON object")
            if self.path.endswith("/count_tokens"):
                send_json(self, 200, self.server.api.count_tokens(payload))
                return
            result = self.server.api.complete(payload)
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
            send_json(self, status, {"type": "error", "error": {"type": error_type,
                                                                "message": str(exc) if isinstance(exc, BridgeError)
                                                                else "Invalid message or upstream response"}})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
