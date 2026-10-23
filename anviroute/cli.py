"""One-command launcher: enter URL and API key, then use Claude Code."""

import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

from .runtime import claude_environment, start_server
from .common import BridgeError

from . import __version__
from .api import API, UpstreamError, normalize_url
from .server import Server
from .service import Router, data_dir, write_private
from urllib.request import Request, urlopen
import webbrowser


def config_path():
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".config"))
    return root / "AnviRoute" / "config.json"


def load_config():
    try:
        value = json.loads(config_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(url, model, api_format):
    # Only convenience defaults. API credentials are intentionally not persisted.
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"url": url, "model": model, "api_format": api_format}, output)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prompt(label, default=""):
    suffix = f" [{default}]" if default else ""
    return input(label + suffix + ": ").strip() or default


def choose_model(api, requested, previous):
    models = []
    timeout = api.timeout
    api.timeout = min(timeout, 15)
    try:
        response = api.call("/models")
        models = [m["id"] for m in response.get("data", []) if isinstance(m, dict) and isinstance(m.get("id"), str)]
    except UpstreamError as exc:
        if exc.status in (401, 403):
            raise
    except (BridgeError, AttributeError, TypeError):
        pass
    finally:
        api.timeout = timeout
    if requested:
        return requested
    if previous in models:
        return previous
    if models:
        return models[0]
    raise BridgeError("The endpoint did not list any models. Check the API URL, API key, and that your model is loaded.")


def run_direct(args):
    executable = shutil.which("claude")
    if not executable:
        raise BridgeError("Claude Code is not on PATH. Install Claude Code and reopen your terminal.")
    config = load_config()
    print("\n  AnviRoute\n  Paste your API. Use Claude Code.\n", flush=True)
    api_format = args.api_format or config.get("api_format", "openai")
    if api_format not in ("openai", "anthropic"):
        api_format = "openai"
    first_attempt = True
    while True:
        try:
            url = normalize_url((args.url if first_attempt else None) or prompt("API URL", config.get("url", "")))
            key = "" if args.no_key else (os.environ.get("ANVIROUTE_API_KEY") if first_attempt else None)
            if key is None:
                key = getpass.getpass("API key (hidden; Enter if none): ").strip()
            api = API(url, key, args.model or "", api_format, args.timeout)
            api.model = choose_model(api, args.model, config.get("model", ""))
            print("Checking connection and model inference…", flush=True)
            api.check()
            print(f"Connection OK · model found · {api.format} inference OK", flush=True)
            break
        except BridgeError as exc:
            if not sys.stdin.isatty():
                raise
            print(f"\n[AnviRoute] Connection check failed: {exc}", file=sys.stderr, flush=True)
            if prompt("Update connection and retry? Y/n", "y").lower().startswith("n"):
                raise
            first_attempt = False
    local_token = secrets.token_urlsafe(32)
    server = Server(args.port, api, local_token)
    start_server(server)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        try:
            save_config(url, api.model, api.format)
        except OSError:
            print("Could not save defaults; continuing for this session.")
        print(f"\n  Model: {api.model}\n  Local API: {base}\n  Starting Claude Code in this terminal…\n", flush=True)
        env = claude_environment(base, api.model, local_token)
        env.pop("ANVIROUTE_API_KEY", None)
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        return subprocess.call([executable, "--model", api.model, *args.claude_args], env=env)
    finally:
        server.shutdown()
        server.server_close()
        if server.last_error:
            print(f"\n[AnviRoute] Last connection error: {server.last_error}", file=sys.stderr)


def serve(args):
    server = Router(args.port)
    descriptor = data_dir() / 'service.json'
    write_private(descriptor, {'url': server.address, 'token': server.token})
    print(f'AnviRoute service: {server.address}\nConfigure APIs in the dashboard. Keep this terminal open.\nSecond terminal: anviroute.cmd run claude', flush=True)
    if not args.no_browser:
        webbrowser.open(server.address)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            current = json.loads(descriptor.read_text())
            if current.get('token') == server.token:
                descriptor.unlink()
        except (OSError, ValueError):
            pass


def run(args):
    if args.direct:
        return run_direct(args)
    executable = shutil.which('claude')
    if not executable:
        raise BridgeError('Claude Code is not on PATH')
    try:
        connection = json.loads((data_dir() / 'service.json').read_text())
        base = connection['url']
        # Only attach to our local service, never a URL modified to an external host.
        if not base.startswith('http://127.0.0.1:') or not base.removeprefix('http://127.0.0.1:').isdigit():
            raise ValueError()
        req = Request(base + '/control/status', headers={'Authorization': 'Bearer ' + connection['token']})
        with urlopen(req, timeout=5) as response:
            state = json.load(response)
    except (OSError, ValueError, KeyError):
        raise BridgeError('AnviRoute service is not running. In the first terminal run: anviroute.cmd start') from None
    if state.get('product') != 'AnviRoute' or not state.get('ready'):
        raise BridgeError(f'Open {base}, add/activate an API, and click Check API and model first')
    env = claude_environment(base, state['model'], connection['token'])
    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    print(f"Claude → {base} → {state['model']}\nDiagnostics: {base}", flush=True)
    return subprocess.call([executable, '--model', state['model'], *args.claude_args], env=env)


def parser():
    root = argparse.ArgumentParser(description="AnviRoute · paste your API, launch Claude Code")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    service = commands.add_parser('start', help='Start the persistent proxy and dashboard')
    service.add_argument('--port', type=int, default=20128)
    service.add_argument('--no-browser', action='store_true')
    command = commands.add_parser("run", help="Enter connection details and launch a coding tool")
    command.add_argument("client", choices=["claude"])
    command.add_argument('--direct', action='store_true', help=argparse.SUPPRESS)
    command.add_argument("--model", help=argparse.SUPPRESS)
    command.add_argument("--url", help="API root or /v1 URL (otherwise asked interactively)")
    command.add_argument("--api-format", choices=["openai", "anthropic"], help="Default: OpenAI-compatible")
    command.add_argument("--no-key", action="store_true", help="Endpoint requires no API key")
    command.add_argument("--port", type=int, default=20128, help="Local API port (default: 20128)")
    command.add_argument("--timeout", type=int, default=110, help="Upstream request timeout in seconds")
    return root


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        separator = argv.index("--")
        argv, extra = argv[:separator], argv[separator + 1:]
    args = parser().parse_args(argv or ["start"])
    args.claude_args = extra
    try:
        if not 0 <= args.port <= 65535 or getattr(args, 'timeout', 110) <= 0:
            raise BridgeError("Port must be 0–65535 and timeout must be positive")
        return serve(args) if args.command == 'start' else run(args)
    except KeyboardInterrupt:
        print("\nAnviRoute stopped.", file=sys.stderr)
        return 130
    except EOFError:
        print("AnviRoute: open an interactive terminal, or provide --url and ANVIROUTE_API_KEY / --no-key.", file=sys.stderr)
        return 1
    except (BridgeError, OSError) as exc:
        print(f"AnviRoute: {exc}", file=sys.stderr)
        return 1
