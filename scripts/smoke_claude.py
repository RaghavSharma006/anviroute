"""Optional real Claude Code smoke test using only a local simulated model server."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from anviroute.api import API
from anviroute.runtime import claude_environment, start_server
from anviroute.service import Router

MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M"


class FakeModel(BaseHTTPRequestHandler):
    requests_received = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({'data': [{'id': MODEL}]}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert data['model'] == MODEL and data['stream'] is False
        FakeModel.requests_received += 1
        response = {'id': 'local-smoke', 'choices': [{'index': 0, 'finish_reason': 'stop',
                    'message': {'role': 'assistant', 'content': 'AnviRoute local smoke passed.'}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 6}}
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    executable = shutil.which('claude')
    if not executable:
        raise SystemExit('Install Claude Code to run this optional smoke test.')
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), FakeModel)
    start_server(upstream)
    profile_folder = tempfile.TemporaryDirectory(prefix='AnviRoute-Router-Smoke-')
    local = Router(0, profile_folder.name)
    local.control('save', {'name': 'smoke', 'url': f'http://127.0.0.1:{upstream.server_port}', 'key': 'fake-key', 'model': MODEL})
    local.control('check', {})
    start_server(local)
    try:
        with tempfile.TemporaryDirectory(prefix='AnviRoute-Claude-Smoke-') as folder:
            env = claude_environment(f'http://127.0.0.1:{local.server_port}', MODEL, local.token)
            env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
            settings = Path(folder) / 'settings.json'
            settings.write_text(json.dumps({'env': {'ANTHROPIC_BASE_URL': env['ANTHROPIC_BASE_URL'],
                                                    'ANTHROPIC_AUTH_TOKEN': local.token,
                                                    'ANTHROPIC_API_KEY': ''}}))
            result = subprocess.run([executable, '--safe-mode', '--settings', str(settings),
                                     '--strict-mcp-config', '--model', MODEL, '--no-session-persistence',
                                     '--system-prompt', 'Reply to the greeting.', '--tools', 'Read', '-p', 'Hello'],
                                    cwd=folder, env=env, capture_output=True, text=True, timeout=60)
            if result.returncode or 'AnviRoute local smoke passed.' not in result.stdout:
                print(result.stdout)
                print(result.stderr, file=sys.stderr)
                raise SystemExit('Real Claude Code compatibility smoke failed.')
        assert FakeModel.requests_received > 0
        print('PASS: actual Claude Code → beta Messages route → AnviRoute → simulated OpenAI model.')
        print('This verifies client compatibility, not real Kaggle inference.')
    finally:
        local.shutdown()
        local.server_close()
        profile_folder.cleanup()
        upstream.shutdown()
        upstream.server_close()


if __name__ == '__main__':
    main()
