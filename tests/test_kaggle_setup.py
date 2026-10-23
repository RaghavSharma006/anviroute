import ast
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, mock_open, patch

import flask  # Development dependency, not required by the PC launcher.
import requests

ROOT = Path(__file__).resolve().parents[1]
MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M"


class KaggleSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "examples/kaggle/02_start_tunnel.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        embedded = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "proxy_code" for t in node.targets))
        proxy_tree = ast.parse(embedded)
        proxy_tree.body.pop()  # Do not start a real Flask server; use its test client.
        scope = {"__name__": __name__}
        with patch("builtins.open", mock_open(read_data="test-secret")), patch.dict("os.environ", {"ANVIROUTE_MODEL": MODEL}):
            exec(compile(proxy_tree, "<kaggle-proxy>", "exec"), scope)
        cls.app = scope["app"]
        cls.app.testing = True

    def setUp(self):
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer test-secret"}

    def upstream(self, data):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        response.content = json.dumps(data).encode()
        response.json.return_value = data
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_key_required_before_upstream(self):
        with patch("requests.request") as upstream:
            self.assertEqual(self.client.get("/v1/models").status_code, 401)
            self.assertEqual(self.client.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code, 401)
            upstream.assert_not_called()

    def test_administration_blocked(self):
        with patch("requests.request") as upstream:
            response = self.client.delete("/api/delete", headers=self.headers)
            self.assertEqual(response.status_code, 404)
            upstream.assert_not_called()

    def test_selected_model_only_is_discovered(self):
        data = {"data": [{"id": MODEL}, {"id": "unrelated-model"}]}
        with patch("requests.request", return_value=self.upstream(data)):
            response = self.client.get("/v1/models", headers=self.headers)
            self.assertEqual(response.get_json()["data"], [{"id": MODEL}])

    def test_completion_is_nonstreaming_and_uses_selected_model(self):
        with patch("requests.request", return_value=self.upstream({"choices": []})) as upstream:
            response = self.client.post("/v1/chat/completions", headers=self.headers,
                                        json={"model": "wrong-model", "stream": True, "messages": []})
            self.assertEqual(response.status_code, 200)
            forwarded = upstream.call_args.kwargs["json"]
            self.assertEqual(forwarded["model"], MODEL)
            self.assertFalse(forwarded["stream"])

    def test_connection_errors_do_not_echo_internal_details(self):
        with patch("requests.request", side_effect=requests.ConnectionError("sensitive internal detail")):
            response = self.client.get("/v1/models", headers=self.headers)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("sensitive", response.get_data(as_text=True))

    def test_notebook_and_readme_contain_matching_executable_cells(self):
        notebook = json.loads((ROOT / "examples/kaggle_anviroute.ipynb").read_text(encoding="utf-8"))
        code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for filename, cell in zip(("01_start_ollama.py", "02_start_tunnel.py"), code_cells):
            source = (ROOT / "examples/kaggle" / filename).read_text(encoding="utf-8").rstrip()
            self.assertEqual("".join(cell["source"]).rstrip(), source)
            self.assertIn(source, readme)
            self.assertEqual(cell["outputs"], [])
            ast.parse(source)


if __name__ == "__main__":
    unittest.main()
