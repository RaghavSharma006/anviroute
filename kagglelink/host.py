"""Authenticated job transport: no SSE crosses the Quick Tunnel."""

import base64
import hmac
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .common import BridgeError, MAX_BODY, read_body, send_json

MAX_JOBS = 8
JOB_TTL = 1800
POLL_BYTES = 512 * 1024


class Job:
    def __init__(self):
        self.condition = threading.Condition()
        self.created = time.monotonic()
        self.lines = []
        self.size = 0
        self.status = None
        self.content_type = None
        self.done = False
        self.cancelled = False

    def append(self, data):
        with self.condition:
            if self.cancelled or self.size + len(data) > MAX_BODY:
                raise BridgeError("Response limit exceeded or request cancelled")
            self.lines.append(base64.b64encode(data).decode())
            self.size += len(data)
            self.condition.notify_all()


class HostServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, token, model, ollama="http://127.0.0.1:11434"):
        parsed = urllib.parse.urlsplit(ollama)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise BridgeError("Ollama must be a loopback HTTP root URL")
        self.token, self.model, self.ollama = token, model, ollama.rstrip("/")
        self.session = secrets.token_urlsafe(16)
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        super().__init__(address, HostHandler)

    def generate(self, job, path, payload):
        try:
            req = urllib.request.Request(self.ollama + path, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            try:
                response = urllib.request.urlopen(req, timeout=300)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                with job.condition:
                    job.status = response.status
                    job.content_type = response.headers.get("Content-Type", "application/json")
                    job.condition.notify_all()
                if "text/event-stream" in job.content_type:
                    while True:
                        line = response.readline(MAX_BODY + 1)
                        if not line:
                            break
                        job.append(line)
                else:
                    job.append(response.read(MAX_BODY + 1))
        except Exception:
            # Never echo upstream URLs, payloads, or credentials into errors.
            with job.condition:
                if job.status is None:
                    job.status, job.content_type = 502, "application/json"
                    error = json.dumps({"type": "error", "error": {
                        "type": "api_error", "message": "Ollama request failed; check the Kaggle host"}}).encode()
                elif "text/event-stream" in job.content_type:
                    error = b'event: error\ndata: {"type":"error","error":{"type":"api_error","message":"Upstream interrupted or response limit exceeded"}}\n\n'
                else:
                    job.status = 502
                    job.lines.clear()
                    error = b'{"error":"Upstream interrupted or response limit exceeded"}'
                job.lines.append(base64.b64encode(error).decode())
        finally:
            with job.condition:
                job.done = True
                job.condition.notify_all()


class HostHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(45)

    def log_message(self, *args):
        pass

    def authorized(self):
        value = self.headers.get("Authorization", "")
        if not value.isascii() or not hmac.compare_digest(value, "Bearer " + self.server.token):
            send_json(self, 401, {"error": "Invalid bridge token"})
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/bridge/info":
            send_json(self, 200, {"schema": 1, "model": self.server.model,
                                  "session": self.server.session, "transport": "json-poll"})
            return
        job_id = parsed.path.removeprefix("/bridge/jobs/")
        with self.server.jobs_lock:
            job = self.server.jobs.get(job_id)
        if not parsed.path.startswith("/bridge/jobs/") or job is None:
            send_json(self, 404, {"error": "Unknown job or route"})
            return
        try:
            after = int(urllib.parse.parse_qs(parsed.query).get("after", ["0"])[0])
            with job.condition:
                if not 0 <= after <= len(job.lines):
                    raise ValueError()
                if after == len(job.lines) and not job.done:
                    job.condition.wait(timeout=8)
                lines, size = [], 0
                for line in job.lines[after:]:
                    if lines and size + len(line) > POLL_BYTES:
                        break
                    lines.append(line)
                    size += len(line)
                end = after + len(lines)
                result = {"status": job.status, "content_type": job.content_type,
                          "lines": lines, "next": end, "done": job.done and end == len(job.lines)}
            send_json(self, 200, result)
        except ValueError:
            send_json(self, 400, {"error": "Invalid cursor"})

    def do_POST(self):
        if not self.authorized():
            return
        if self.path != "/bridge/jobs":
            send_json(self, 404, {"error": "Unknown route"})
            return
        try:
            data = read_body(self)
            path, payload = data["path"], data["payload"]
            if path not in ("/v1/messages", "/v1/messages/count_tokens") or not isinstance(payload, dict):
                raise ValueError()
            # A session exposes exactly the selected model, never arbitrary Ollama admin APIs.
            payload["model"] = self.server.model
        except (BridgeError, KeyError, TypeError, ValueError):
            send_json(self, 400, {"error": "Expected a supported Messages API path and JSON payload"})
            return
        with self.server.jobs_lock:
            now = time.monotonic()
            for key, existing in list(self.server.jobs.items()):
                if now - existing.created > JOB_TTL:
                    existing.cancelled = True
                    del self.server.jobs[key]
            if len(self.server.jobs) >= MAX_JOBS:
                send_json(self, 429, {"error": "Too many jobs; finish or cancel an existing request"})
                return
            job_id = secrets.token_urlsafe(24)
            job = self.server.jobs[job_id] = Job()
        threading.Thread(target=self.server.generate, args=(job, path, payload), daemon=True).start()
        send_json(self, 202, {"id": job_id})

    def do_DELETE(self):
        if not self.authorized():
            return
        job_id = self.path.removeprefix("/bridge/jobs/")
        with self.server.jobs_lock:
            job = self.server.jobs.pop(job_id, None)
        if job:
            job.cancelled = True
        send_json(self, 200, {"ok": True})
