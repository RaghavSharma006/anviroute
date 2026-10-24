"""Persistent local routing service and Claude Code launcher."""

import argparse
import json
import os
import shutil
import subprocess
import sys

from .runtime import claude_environment
from .common import BridgeError

from . import __version__
from .service import Router, data_dir, write_private
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import webbrowser
import threading


def serve(args):
    # Reopening the frontend should reuse the running router.
    try:
        connection, state = local_service()
        if connection['url'] == f'http://127.0.0.1:{args.port}':
            if not args.no_browser:
                webbrowser.open(connection['url'])
            print('AnviRoute: ' + connection['url'], flush=True)
            return 0
    except BridgeError:
        pass
    server = Router(args.port)
    if args.modelname:
        try:
            server.activate_name(args.modelname)
        except BridgeError:
            server.server_close()
            raise
    descriptor = data_dir() / 'service.json'
    write_private(descriptor, {'url': server.address, 'token': server.token})
    print(f'AnviRoute: {server.address}\nSave your model in the browser. Keep this terminal open.\nSecond terminal: anviroute run claude --modename NAME', flush=True)
    if server.api:
        start_server_thread = threading.Thread(target=server.check_background, daemon=True)
        start_server_thread.start()
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


def local_service():
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
        raise BridgeError('Open the frontend first: anviroute') from None
    if state.get('product') != 'AnviRoute':
        raise BridgeError('The local service is not AnviRoute')
    return connection, state


def run(args):
    executable = shutil.which('claude')
    if not executable:
        raise BridgeError('Claude Code is not on PATH')
    connection, state = local_service()
    base = connection['url']
    if args.modename:
        req = Request(base + '/control/prepare', data=json.dumps({'name': args.modename}).encode(),
                      headers={'Authorization': 'Bearer ' + connection['token'], 'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=125) as response:
                selected = json.load(response)
        except HTTPError as exc:
            try:
                detail = json.load(exc).get('error', 'Connection check failed')
            except (ValueError, OSError):
                detail = 'Connection check failed'
            finally:
                exc.close()
            raise BridgeError(f'{detail}. Diagnostics: {base}') from None
        except OSError:
            raise BridgeError(f'Cannot connect to saved model {args.modename!r}. Open {base} and update its Kaggle URL/key.') from None
        base += selected['path']
        state.update(model=selected['model'], ready=selected['ready'], context_tokens=selected.get('context_tokens', 0))
    if state.get('product') != 'AnviRoute' or not state.get('ready'):
        raise BridgeError('Open AnviRoute and save your model with its current URL/key.')
    env = claude_environment(base, state['model'], connection['token'])
    if state.get('context_tokens'):
        env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'] = str(state['context_tokens'])
    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    print(f"Claude -> {base} -> {state['model']}\nDiagnostics: {connection['url']}", flush=True)
    return subprocess.call([executable, '--model', state['model'], *args.claude_args], env=env)


def parser():
    root = argparse.ArgumentParser(description="AnviRoute · local routing desk")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    service = commands.add_parser('start', help='Start the persistent proxy and dashboard')
    service.add_argument('--port', type=int, default=20128)
    service.add_argument('--no-browser', action='store_true')
    service.add_argument('--modelname', help='Saved profile name to activate and check at startup')
    command = commands.add_parser("run", help="Connect Claude Code to the running AnviRoute service")
    command.add_argument("client", choices=["claude"])
    command.add_argument('--modename', '--modelname', help='Saved model name from the frontend')
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
        if not 0 <= getattr(args, 'port', 20128) <= 65535:
            raise BridgeError("Port must be 0–65535")
        return serve(args) if args.command == 'start' else run(args)
    except KeyboardInterrupt:
        print("\nAnviRoute stopped.", file=sys.stderr)
        return 130
    except (BridgeError, OSError) as exc:
        print(f"AnviRoute: {exc}", file=sys.stderr)
        return 1
