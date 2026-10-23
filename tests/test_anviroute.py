import json
from pathlib import Path
import tempfile
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from anviroute.api import API, anthropic_response, normalize_url, openai_payload
from anviroute.cli import main
from anviroute.server import Server
from anviroute.runtime import start_server
from anviroute.common import BridgeError
from helpers import request


class FakeAPI(BaseHTTPRequestHandler):
    last_payload = None

    def log_message(self, *args):
        pass

    def send(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self):
        if self.headers.get("Authorization") != "Bearer upstream-secret":
            self.send(401, {"error": "Invalid key"})
            return False
        return True

    def do_GET(self):
        if self.authenticated():
            self.send(200, {"data": [{"id": "test-coder"}, {"id": "other-model"}]})

    def do_POST(self):
        if not self.authenticated():
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeAPI.last_payload = payload
        if self.path == "/v1/messages":
            self.send(200, {"id": "native", "type": "message", "role": "assistant", "model": "test-coder",
                            "content": [{"type": "text", "text": "native hello"}], "stop_reason": "end_turn",
                            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 2}})
            return
        if payload.get("messages", [{}])[-1].get("content") == "error":
            self.send(429, {"error": "Rate limited"})
            return
        self.send(200, {"id": "completion-1", "choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": "Creating the file.", "tool_calls": [{"id": "tool-1", "type": "function",
            "function": {"name": "Write", "arguments": json.dumps({"file_path": "hello.txt", "content": "Hello ☀"})}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}})


class AnviRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
        start_server(cls.upstream)
        cls.url = f"http://127.0.0.1:{cls.upstream.server_port}"
        cls.api = API(cls.url, "upstream-secret", "test-coder")
        cls.local = Server(0, cls.api, "local-secret")
        start_server(cls.local)
        cls.local_url = f"http://127.0.0.1:{cls.local.server_port}"

    @classmethod
    def tearDownClass(cls):
        for server in (cls.local, cls.upstream):
            server.shutdown()
            server.server_close()

    def test_round_trip_tool_stream_and_complete_json_upstream(self):
        payload = {"model": "claude-alias", "max_tokens": 256, "stream": True,
                   "messages": [{"role": "user", "content": "Create hello.txt"}],
                   "tools": [{"name": "Write", "input_schema": {"type": "object"}}]}
        req = urllib.request.Request(self.local_url + "/v1/messages", data=json.dumps(payload).encode(),
                                     headers={"Authorization": "Bearer local-secret", "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.headers["Content-Type"], "text/event-stream")
            lines = response.read().decode().splitlines()
        frames = [json.loads(line[6:]) for line in lines if line.startswith("data: ")]
        self.assertEqual(frames[0]["type"], "message_start")
        self.assertEqual(frames[-1]["type"], "message_stop")
        tool_json = "".join(frame["delta"]["partial_json"] for frame in frames
                            if frame["type"] == "content_block_delta" and frame["delta"]["type"] == "input_json_delta")
        self.assertEqual(json.loads(tool_json), {"file_path": "hello.txt", "content": "Hello ☀"})
        self.assertEqual(FakeAPI.last_payload["model"], "test-coder")
        self.assertFalse(FakeAPI.last_payload["stream"])
        self.assertEqual(FakeAPI.last_payload["tools"][0]["function"]["name"], "Write")

    def test_tool_results_replay(self):
        payload = {"messages": [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "call1", "name": "Read", "input": {"file": "x"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call1", "content": "File contents"},
                                          {"type": "text", "text": "Continue"}]}]}
        messages = openai_payload(payload, "model")["messages"]
        self.assertEqual(messages[0]["tool_calls"][0]["id"], "call1")
        self.assertEqual(messages[1], {"role": "tool", "tool_call_id": "call1", "content": "File contents"})
        self.assertEqual(messages[2]["content"], "Continue")

    def test_native_anthropic_mode(self):
        api = API(self.url, "upstream-secret", "test-coder", "anthropic")
        result = api.complete({"stream": True, "messages": []})
        self.assertEqual(result["content"][0]["text"], "native hello")
        self.assertFalse(FakeAPI.last_payload["stream"])

    def test_wrong_upstream_key_is_not_echoed(self):
        api = API(self.url, "private-wrong-key", "test-coder")
        with self.assertRaises(BridgeError) as exc:
            api.complete({"messages": []})
        self.assertIn("401", str(exc.exception))
        self.assertNotIn("private-wrong-key", str(exc.exception))

    def test_upstream_rate_limit_preserved(self):
        with self.assertRaisesRegex(BridgeError, "HTTP 429"):
            request(self.local_url + "/v1/messages", "local-secret",
                    {"messages": [{"role": "user", "content": "error"}]})

    def test_local_auth_rejects_upstream_key(self):
        with self.assertRaisesRegex(BridgeError, "HTTP 401"):
            request(self.local_url + "/v1/models", "upstream-secret")

    def test_unknown_admin_route_rejected(self):
        with self.assertRaisesRegex(BridgeError, "HTTP 404"):
            request(self.local_url + "/api/delete", "local-secret", {"name": "model"})

    def test_count_tokens_heuristic(self):
        result = request(self.local_url + "/v1/messages/count_tokens", "local-secret", {"messages": []})
        self.assertGreater(result["input_tokens"], 0)

    def test_claude_beta_query_routes_to_messages(self):
        result = request(self.local_url + "/v1/messages?beta=true", "local-secret",
                         {"messages": [{"role": "user", "content": "Hello"}]})
        self.assertEqual(result["stop_reason"], "tool_use")
        count = request(self.local_url + "/v1/messages/count_tokens?beta=true", "local-secret", {"messages": []})
        self.assertGreater(count["input_tokens"], 0)

    def test_mid_conversation_system_messages_are_preserved(self):
        payload = {"messages": [{"role": "user", "content": "Hello"},
                                 {"role": "system", "content": [{"type": "text", "text": "Reminder"}]}]}
        self.assertEqual(openai_payload(payload, "model")["messages"][-1],
                         {"role": "system", "content": "Reminder"})

    def test_inference_preflight(self):
        self.assertEqual(self.api.check()["stop_reason"], "tool_use")
        self.assertEqual(FakeAPI.last_payload["max_tokens"], 1)

    def test_preflight_switches_only_on_unsupported_api_route(self):
        from anviroute.api import UpstreamError
        api = API(self.url, "upstream-secret", "test-coder")
        with patch.object(api, "complete", side_effect=[UpstreamError(404, "route missing"), {"content": []}]):
            api.check()
        self.assertEqual(api.format, "anthropic")
        api.format = "openai"
        with patch.object(api, "complete", side_effect=UpstreamError(401, "bad key")) as complete:
            with self.assertRaises(UpstreamError):
                api.check()
            self.assertEqual(complete.call_count, 1)
        self.assertEqual(api.format, "openai")

    def test_malformed_tool_json_is_error(self):
        with self.assertRaisesRegex(BridgeError, "malformed tool"):
            anthropic_response({"choices": [{"message": {"tool_calls": [{"id": "a", "function": {
                "name": "Read", "arguments": "not json"}}]}}]}, "model")

    def test_unsupported_blocks_fail_explicitly(self):
        with self.assertRaisesRegex(BridgeError, "Unsupported content"):
            openai_payload({"messages": [{"role": "user", "content": [{"type": "document"}]}]}, "model")

    def test_url_normalization(self):
        self.assertEqual(normalize_url("https://api.example.com/"), "https://api.example.com/v1")
        self.assertEqual(normalize_url("https://api.example.com/v1/chat/completions"), "https://api.example.com/v1")
        for url in ("http://public.example.com", "https://secret@api.example.com", "https://api.example.com?key=secret"):
            with self.assertRaises(BridgeError):
                normalize_url(url)


if __name__ == "__main__":
    unittest.main()
