"""Small, dependency-free HTTP and configuration helpers."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

MAX_BODY = 16 * 1024 * 1024


class BridgeError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, token=None, data=None, method=None, timeout=30):
    headers = {"Accept": "application/json", "User-Agent": "KaggleLink/0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise BridgeError(f"HTTP {code}: check credentials, session, and configuration") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise BridgeError("Connection failed: check that Kaggle and the tunnel are running") from None


def remote_url(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise BridgeError("Remote URL must be an HTTPS root URL without credentials, query, or path")
    return value.rstrip("/")


def read_body(handler):
    if handler.headers.get("Transfer-Encoding"):
        raise BridgeError("Chunked request bodies are not supported")
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        raise BridgeError("Invalid content length") from None
    if not 0 <= length <= MAX_BODY:
        raise BridgeError("Request too large (maximum 16 MiB)")
    body = handler.rfile.read(length)
    if len(body) != length:
        raise BridgeError("Incomplete request body")
    try:
        return json.loads(body)
    except ValueError:
        raise BridgeError("Expected a JSON body") from None


def send_json(handler, status, data):
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def token_from_env(name):
    token = os.environ.get(name, "")
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise BridgeError(f"Set {name} to a random token of at least 32 ASCII characters (no whitespace)")
    return token
