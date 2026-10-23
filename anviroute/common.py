"""Shared runtime helpers; standard library only."""

import json
import urllib.request

MAX_BODY = 16 * 1024 * 1024


class BridgeError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
