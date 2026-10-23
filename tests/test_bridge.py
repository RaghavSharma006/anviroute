import base64
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from kagglelink.cli import claude_environment, parser, start_server
from kagglelink.client import Connection, LocalServer
from kagglelink.common import BridgeError, remote_url, request
from kagglelink.host import HostServer
from kagglelink.registry import Registry

TOKEN = "a" * 40
LOCAL_TOKEN = "b" * 40
STREAM = (b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1"}}\n\n'
          b'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"tool_1","name":"Read","input":{}}}\n\n'
          b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"file_path\\":\\"README.md\\"}"}}\n\n'
          b'event: message_stop\ndata: {"type":"message_stop"}\n\n')


class FakeOllama(BaseHTTPRequestHandler):
    last_payload = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.last_payload = payload
        if self.path.endswith("count_tokens"):
            body, mime, status = b'{"input_tokens":12}', "application/json", 200
        elif payload.get("fail"):
            body, mime, status = b'{"error":"model unavailable"}', "application/json", 404
        elif payload.get("stream"):
            body, mime, status = STREAM, "text/event-stream", 200
        else:
            body, mime, status = b'{"content":[{"type":"text","text":"hello"}]}', "application/json", 200
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BridgeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        start_server(cls.ollama)
        cls.host = HostServer(("127.0.0.1", 0), TOKEN, "test-model",
                              f"http://127.0.0.1:{cls.ollama.server_port}")
        start_server(cls.host)
        cls.host_url = f"http://127.0.0.1:{cls.host.server_port}"
        cls.local = LocalServer(("127.0.0.1", 0), Connection(TOKEN, cls.host_url), "test-model", LOCAL_TOKEN)
        start_server(cls.local)
        cls.local_url = f"http://127.0.0.1:{cls.local.server_port}"

    @classmethod
    def tearDownClass(cls):
        for server in (cls.local, cls.host, cls.ollama):
            server.shutdown()
            server.server_close()

    def test_stream_and_tool_arguments_survive_round_trip(self):
        req = urllib.request.Request(self.local_url + "/v1/messages",
                                     data=json.dumps({"model": "wrong", "stream": True,
                                                      "messages": [], "tools": [{"name": "Read"}]}).encode(),
                                     headers={"Authorization": "Bearer " + LOCAL_TOKEN,
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.headers["Content-Type"], "text/event-stream")
            self.assertEqual(response.read(), STREAM)
        self.assertEqual(FakeOllama.last_payload["model"], "test-model")
        self.assertEqual(FakeOllama.last_payload["tools"], [{"name": "Read"}])

    def test_nonstream_response(self):
        result = request(self.local_url + "/v1/messages", LOCAL_TOKEN, {"messages": []})
        self.assertEqual(result["content"][0]["text"], "hello")

    def test_count_tokens(self):
        self.assertEqual(request(self.local_url + "/v1/messages/count_tokens", LOCAL_TOKEN,
                                 {"messages": []}), {"input_tokens": 12})

    def test_upstream_error_status_preserved(self):
        with self.assertRaisesRegex(BridgeError, "HTTP 404"):
            request(self.local_url + "/v1/messages", LOCAL_TOKEN, {"fail": True})

    def test_remote_rejects_missing_and_wrong_auth(self):
        for token in (None, "wrong"):
            with self.assertRaisesRegex(BridgeError, "HTTP 401"):
                request(self.host_url + "/bridge/info", token)

    def test_local_requires_own_token(self):
        with self.assertRaisesRegex(BridgeError, "HTTP 401"):
            request(self.local_url + "/v1/models", TOKEN)

    def test_admin_routes_are_not_exposed(self):
        with self.assertRaisesRegex(BridgeError, "HTTP 400"):
            request(self.host_url + "/bridge/jobs", TOKEN,
                    {"path": "/api/delete", "payload": {"model": "test-model"}})

    def test_cursor_validation_and_cleanup(self):
        job = request(self.host_url + "/bridge/jobs", TOKEN,
                      {"path": "/v1/messages", "payload": {}})["id"]
        url = self.host_url + "/bridge/jobs/" + job
        with self.assertRaisesRegex(BridgeError, "HTTP 400"):
            request(url + "?after=-1", TOKEN)
        self.assertTrue(request(url, TOKEN, method="DELETE")["ok"])
        with self.assertRaisesRegex(BridgeError, "HTTP 404"):
            request(url, TOKEN)

    def test_invalid_json_rejected(self):
        req = urllib.request.Request(self.host_url + "/bridge/jobs", data=b"broken",
                                     headers={"Authorization": "Bearer " + TOKEN})
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        self.assertEqual(exc.exception.code, 400)
        exc.exception.close()


class ConfigurationTests(unittest.TestCase):
    def test_discovery_refreshes_new_requests_without_switching_an_existing_url(self):
        class FakeRegistry:
            calls = 0

            def resolve(self):
                self.calls += 1
                return {"url": f"https://session-{self.calls}.trycloudflare.com"}

        registry = FakeRegistry()
        remote = Connection(TOKEN, registry=registry)
        with patch("kagglelink.client.time.monotonic", return_value=100):
            pinned_url = remote.resolve()
            self.assertEqual(remote.resolve(), pinned_url)
            self.assertEqual(registry.calls, 1)
        with patch("kagglelink.client.time.monotonic", return_value=116):
            self.assertNotEqual(remote.resolve(), pinned_url)
            self.assertEqual(registry.calls, 2)
        self.assertEqual(pinned_url, "https://session-1.trycloudflare.com")

    def test_public_registry_refused(self):
        with patch.dict("os.environ", {"KAGGLELINK_GITHUB_TOKEN": "fake"}):
            registry = Registry("owner/discovery")
            with patch.object(registry, "api", return_value={"private": False}):
                with self.assertRaisesRegex(BridgeError, "PRIVATE"):
                    registry.publish("https://test.trycloudflare.com", "model", "session")

    def test_registry_never_publishes_shared_token(self):
        with patch.dict("os.environ", {"KAGGLELINK_GITHUB_TOKEN": "github-secret", "KAGGLELINK_TOKEN": TOKEN}):
            registry = Registry("owner/discovery")
            with patch.object(registry, "api", side_effect=[{"private": True}, None, {}]) as api:
                registry.publish("https://test.trycloudflare.com", "model", "session")
                body = json.loads(base64.b64decode(api.call_args.args[1]["content"]))
                self.assertEqual(set(body), {"schema", "url", "model", "session", "updated_at"})
                self.assertNotIn(TOKEN, json.dumps(body))

    def test_child_environment_hides_registry_credentials(self):
        env = claude_environment("http://127.0.0.1:17654", "model", LOCAL_TOKEN,
                                 {"KAGGLELINK_GITHUB_TOKEN": "secret", "KAGGLELINK_TOKEN": TOKEN,
                                  "CLAUDE_CODE_USE_VERTEX": "1", "CLAUDE_CODE_OAUTH_TOKEN": "oauth"})
        self.assertNotIn("KAGGLELINK_GITHUB_TOKEN", env)
        self.assertNotIn("KAGGLELINK_TOKEN", env)
        self.assertNotIn("CLAUDE_CODE_USE_VERTEX", env)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], LOCAL_TOKEN)
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "model")

    def test_url_validation(self):
        for url in ("http://insecure.example", "https://user:secret@example.com", "https://example.com/v1",
                    "https://example.com?token=secret"):
            with self.assertRaises(BridgeError):
                remote_url(url)

    def test_cli_passes_claude_args(self):
        args = parser().parse_args(["launch", "--repo", "owner/discovery", "--", "-p", "hello world"])
        self.assertEqual(args.claude_args, ["--", "-p", "hello world"])


if __name__ == "__main__":
    unittest.main()
