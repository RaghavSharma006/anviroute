"""Persistent loopback router, dashboard, and multi-provider control plane."""

from collections import deque
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from urllib.parse import urlsplit

from . import __version__
from .api import API
from .common import BridgeError, read_body, send_json
from .dashboard import HTML
from .server import Handler, Server
from .vault import seal, unlock


def data_dir():
    # User-profile storage is shared with ordinary shells (MSIX virtualizes AppData).
    folder = Path(os.environ['ANVIROUTE_HOME']) if os.environ.get('ANVIROUTE_HOME') else Path.home()/'.anviroute'
    folder.mkdir(parents=True, exist_ok=True)
    previous = Path(os.environ.get('LOCALAPPDATA', Path.home()/'.config'))/'AnviRoute'/'providers.json'
    target = folder/'providers.json'
    if not target.exists() and previous.exists():
        write_private(target, json.loads(previous.read_text(encoding='utf-8')))
    return folder


def write_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Router(Server):
    def __init__(self, port=20128, folder=None):
        self.folder = Path(folder) if folder else data_dir()
        self.profiles = {}
        self.active = None
        self.events = deque(maxlen=500)
        self.client_seen = None
        self.upstream = 'Not checked'
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.api = None
        self.model = ''
        self.checked = False
        self.ready_profiles = {}
        self.diagnostics = {}
        self.last_error = None
        try:
            saved = json.loads((self.folder/'providers.json').read_text())
            for p in saved['providers']:
                try:
                    key = unlock(p.get('encrypted_key'))
                except BridgeError:
                    key = ''
                self.profiles[p['id']] = {**p, 'key': key, 'context_tokens': p.get('context_tokens') or 32768}
            self.active = saved.get('active')
        except (OSError, ValueError, KeyError, TypeError, BridgeError):
            pass
        self.folder.mkdir(parents=True, exist_ok=True)
        self.log_handler = RotatingFileHandler(self.folder/'events.jsonl', maxBytes=262144, backupCount=2, encoding='utf-8')
        self.log_handler.setFormatter(logging.Formatter('%(message)s'))
        try:
            for line in (self.folder/'events.jsonl').read_text(encoding='utf-8').splitlines()[-500:]:
                self.events.append(json.loads(line))
        except (OSError, ValueError):
            pass
        if self.active in self.profiles:
            try:
                self.activate(self.active)
            except BridgeError as exc:
                self.record('adapter', 'Saved connection needs editing: ' + str(exc), False)
                self.upstream = str(exc)
        # Initialize directly; no provider is required to start the dashboard.
        from http.server import ThreadingHTTPServer
        ThreadingHTTPServer.__init__(self, ('127.0.0.1', port), DashboardHandler)
        self.address = f'http://127.0.0.1:{self.server_port}'
        self.record('adapter', 'Service started', True)

    def persist(self):
        write_private(self.folder/'providers.json', {'active': self.active, 'providers': [
            {k: v for k, v in p.items() if k != 'key'} for p in list(self.profiles.values())]})

    def server_close(self):
        super().server_close()
        self.log_handler.close()

    def record(self, stage, message, ok=True, status=None):
        with self.lock:
            for secret in [self.token, *(p.get('key') for p in self.profiles.values())]:
                if secret:
                    message = message.replace(secret, '[redacted]')
            event = {'time': datetime.now().astimezone().isoformat(timespec='seconds'), 'stage': stage,
                     'message': message[:1000], 'ok': ok, 'status': status, 'profile': self.profiles.get(self.active, {}).get('name', '')}
            self.events.append(event)
            self.log_handler.emit(logging.LogRecord('anviroute', logging.INFO, '', 0, json.dumps(event), (), None))

    def report_error(self, status, message):
        super().report_error(status, message)
        stage = 'upstream' if message.startswith('Upstream') or 'connection' in message.lower() else 'adapter'
        self.record(stage, message, False, status)
        self.upstream = message if stage == 'upstream' else self.upstream

    def activate(self, identifier):
        if identifier not in self.profiles:
            raise BridgeError('Choose an existing API connection')
        p = self.profiles[identifier]
        self.api = API(p['url'], p['key'], p.get('model', ''), p['format'])
        self.model, self.active = self.api.model, identifier
        self.checked = False
        self.upstream = 'Not checked'
        self.persist()

    def activate_name(self, name):
        with self.lock:
            match = next((p['id'] for p in self.profiles.values() if p['name'].casefold() == name.casefold() or p['id'] == name), None)
            self.activate(match)

    def check_background(self):
        try:
            self.control('check', {})
        except BridgeError as exc:
            self.upstream = str(exc)
            self.diagnostic(self.active, False, str(exc))
            self.record('upstream', str(exc), False, getattr(exc, 'status', None))

    def status(self):
        with self.lock:
            return {'product': 'AnviRoute', 'version': __version__, 'address': self.address,
                    'active': self.active, 'model': self.model, 'ready': bool(self.api and self.model and self.checked),
                    'context_tokens': self.profiles.get(self.active, {}).get('context_tokens', 0),
                    'providers': [{**{k: v for k, v in p.items() if k not in ('key', 'encrypted_key')}, 'key_saved': bool(p.get('encrypted_key'))} for p in list(self.profiles.values())],
                    'diagnostics': dict(self.diagnostics),
                    'credential_storage': 'Windows account encryption' if os.name == 'nt' else 'Memory only on this platform',
                    'events': list(self.events), 'client_seen': self.client_seen, 'upstream': self.upstream}

    def diagnostic(self, identifier, ok, message, **metrics):
        with self.lock:
            self.diagnostics[identifier] = {'ok': ok, 'message': message,
                'time': datetime.now().astimezone().isoformat(timespec='seconds'), **metrics}
            if not ok:
                self.ready_profiles.pop(identifier, None)
            if identifier == self.active:
                self.checked = ok
                self.upstream = message

    def control(self, action, data):
        if any(not isinstance(v, str) for k, v in data.items() if k in ('id', 'name', 'url', 'key', 'model', 'format')):
            raise BridgeError('Configuration fields must be text')
        if action == 'connect':
            with self.lock:
                result = self.mutate('save', data)
                self.activate(result['id'])
                name = self.profiles[result['id']]['name']
            try:
                self.control('prepare', {'name': name})
                return {**result, 'ready': True, 'message': 'Saved and ready for Claude'}
            except BridgeError as exc:
                self.upstream = str(exc)
                self.diagnostic(result['id'], False, str(exc))
                self.record('upstream', str(exc), False, getattr(exc, 'status', None))
                return {**result, 'ready': False, 'message': 'Saved. ' + str(exc)}
        if action == 'test':
            prompt = data.get('prompt', 'Hello. Reply briefly to verify this connection.')
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
                raise BridgeError('Test message must be text, up to 2000 characters')
            with self.lock:
                p = next((p for p in self.profiles.values() if p['name'].casefold() == data.get('name', '').casefold()), None)
                if p is None:
                    raise BridgeError('Saved model name not found. Add it in AnviRoute first.')
                api = API(p['url'], p['key'], p['model'], p['format'])
            started = time.monotonic()
            try:
                if not api.model:
                    models = self.models(api)
                    if not models:
                        raise BridgeError('API returned no models')
                    api.model = models[0]
                result = api.complete({'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 128})
            except BridgeError as exc:
                if self.profiles.get(p['id']) is p:
                    self.diagnostic(p['id'], False, str(exc))
                raise
            elapsed = round(time.monotonic() - started, 2)
            usage = result.get('usage', {})
            with self.lock:
                if self.profiles.get(p['id']) is not p:
                    raise BridgeError('Connection changed during test. Test the updated connection again.')
                self.diagnostic(p['id'], True, 'Test message completed', seconds=elapsed, input_tokens=usage.get('input_tokens', 0), output_tokens=usage.get('output_tokens', 0))
            self.record('upstream', f'Test completed in {elapsed}s; input {usage.get("input_tokens", 0)}, output {usage.get("output_tokens", 0)} tokens', status=200)
            return {'reply': '\n'.join(b.get('text', '') for b in result.get('content', []) if b.get('type') == 'text') or '(No visible text; model may have exhausted the test output budget while thinking)', 'model': api.model, 'seconds': elapsed, 'usage': usage}
        if action == 'prepare':
            with self.lock:
                p = next((p for p in self.profiles.values() if p['name'].casefold() == data.get('name', '').casefold()), None)
                if p is None:
                    raise BridgeError('Saved model name not found. Add it in AnviRoute first.')
                identifier = p['id']
                api = self.ready_profiles.get(identifier)
                if api is None:
                    api = API(p['url'], p['key'], p['model'], p['format'])
            try:
                if identifier in self.ready_profiles:
                    if api.model not in self.models(api):
                        raise BridgeError('Saved model is unavailable. Edit its model ID or leave it blank to detect.')
                else:
                    self.verify(api)
            except BridgeError as exc:
                if self.profiles.get(identifier) is p:
                    self.diagnostic(identifier, False, str(exc))
                raise
            if identifier not in self.ready_profiles:
                with self.lock:
                    if self.profiles.get(identifier) is not p:
                        raise BridgeError('Connection changed during the check. Run the command again.')
                    p.update(model=api.model, format=api.format)
                    self.ready_profiles[identifier] = api
                    if self.active == identifier:
                        self.api, self.model = api, api.model
                        self.checked = True
                        self.upstream = 'Authentication, model and inference OK'
                    self.persist()
                    self.diagnostic(identifier, True, 'Authentication, model and inference OK')
            return {'model': api.model, 'path': '/p/' + identifier, 'ready': True,
                    'context_tokens': p.get('context_tokens', 0)}
        if action in ('save', 'activate', 'remove', 'model'):
            with self.lock:
                return self.mutate(action, data)
        if action == 'logs':
            with self.lock:
                return {'events': list(self.events)}
        with self.lock:
            api, identifier = self.api, self.active
        if api is None:
            raise BridgeError('Add and activate an API connection first')
        if action == 'models':
            return {'models': self.models(api)}
        if action == 'check':
            with self.lock:
                if self.api is api:
                    self.checked = False
            self.record('upstream', 'Checking authentication and model list')
            self.verify(api)
            with self.lock:
                if self.api is api:
                    self.model = api.model
                    self.profiles[identifier].update(model=api.model, format=api.format)
                    self.persist()
                    self.upstream = 'Authentication, model and inference OK'
                    self.checked = True
                    self.ready_profiles[identifier] = api
            self.record('upstream', 'Authentication, model and inference OK', status=200)
            return {'message': 'API and model inference OK', 'model': api.model}
        raise BridgeError('Unknown control action')

    @staticmethod
    def verify(api):
        models = Router.models(api)
        if not models:
            raise BridgeError('API returned no models')
        if api.model and api.model not in models:
            raise BridgeError('Saved model is unavailable. Edit its model ID or leave it blank to detect.')
        if not api.model:
            api.model = models[0]
        api.check()

    @staticmethod
    def models(api):
        result = api.call('/models')
        return [m['id'] for m in result.get('data', []) if isinstance(m, dict) and isinstance(m.get('id'), str)]

    def mutate(self, action, data):
        if action == 'save':
            identifier = data.get('id') or secrets.token_hex(8)
            previous = self.profiles.get(identifier, {})
            raw_context = data.get('context_tokens', previous.get('context_tokens', 0))
            if isinstance(raw_context, bool) or not str(raw_context or 0).isdigit():
                raise BridgeError('Context window must be a whole number of tokens')
            context = int(raw_context or 32768)
            if context and not 1024 <= context <= 2000000:
                raise BridgeError('Context window must be between 1024 and 2000000 tokens')
            name = data.get('name', 'API').strip()[:80]
            if not name or any(p['name'].casefold() == name.casefold() and p['id'] != identifier for p in self.profiles.values()):
                raise BridgeError('Use a unique profile name')
            api = API(data.get('url', ''), data.get('key', '').strip() or previous.get('key', ''),
                      data.get('model', '').strip(), data.get('format', 'openai'))
            if api.format not in ('openai', 'anthropic'):
                raise BridgeError('Unknown API format')
            encrypted_key = seal(api.key)
            self.ready_profiles.pop(identifier, None)
            self.diagnostics.pop(identifier, None)
            self.profiles[identifier] = {'id': identifier, 'name': name,
                'url': api.url, 'key': api.key, 'encrypted_key': encrypted_key, 'model': api.model, 'format': api.format,
                'context_tokens': context}
            if self.active == identifier or self.active is None:
                self.activate(identifier)
            self.persist()
            return {'id': identifier}
        if action == 'activate':
            self.activate(data.get('id'))
            return {'ok': True}
        if action == 'remove':
            identifier = data.get('id')
            self.ready_profiles.pop(identifier, None)
            self.profiles.pop(identifier, None)
            if self.active == identifier:
                self.active, self.api, self.model = None, None, ''
            self.persist()
            return {'ok': True}
        if self.api is None:
            raise BridgeError('Add and activate an API connection first')
        if action == 'model':
            selected = data.get('model', '').strip()
            if not selected:
                raise BridgeError('Choose a model')
            self.profiles[self.active]['model'] = selected
            self.ready_profiles.pop(self.active, None)
            self.activate(self.active)
            return {'ok': True}
        raise BridgeError('Unknown control action')


class DashboardHandler(Handler):
    def route_path(self):
        path = urlsplit(self.path).path
        return '/' + path.split('/', 3)[3] if path.startswith('/p/') and len(path.split('/', 3)) == 4 else path

    def request_api(self):
        path = urlsplit(self.path).path
        if path.startswith('/p/'):
            identifier = path.split('/', 3)[2]
            with self.server.lock:
                p = self.server.profiles.get(identifier)
                return API(p['url'], p['key'], p['model'], p['format']) if p else None
        return self.server.api

    def safe_origin(self):
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:
            send_json(self, 403, {'error': 'Loopback host required'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + host for host in allowed}:
            send_json(self, 403, {'error': 'Same-origin request required'})
            return False
        return True

    def do_GET(self):
        if not self.safe_origin():
            return
        path = urlsplit(self.path).path
        if path in ('/', '/overview', '/connections', '/logs'):
            body = HTML.replace('__TOKEN__', json.dumps(self.server.token)).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            self.wfile.write(body)
        elif path == '/control/status':
            if self.authorized():
                send_json(self, 200, self.server.status())
        else:
            super().do_GET()

    def do_POST(self):
        if not self.safe_origin():
            return
        path = urlsplit(self.path).path
        if path.startswith('/control/'):
            if not self.authorized():
                return
            try:
                data = read_body(self)
                if not isinstance(data, dict):
                    raise BridgeError('Expected JSON object')
                result = self.server.control(path.removeprefix('/control/'), data)
                send_json(self, 200, result)
            except (BridgeError, ValueError, TypeError, KeyError) as exc:
                message = str(exc) if isinstance(exc, BridgeError) else 'Invalid configuration'
                self.server.record('upstream' if path.endswith(('/check', '/models', '/test', '/prepare')) else 'adapter', message, False, getattr(exc, 'status', 400))
                if path.endswith(('/check', '/models', '/test', '/prepare')):
                    self.server.upstream = message
                send_json(self, 400, {'error': message})
        else:
            if not self.authorized():
                return
            self.server.client_seen = datetime.now().strftime('%H:%M:%S')
            self.server.record('client', 'Claude request received')
            api = self.request_api()
            if not api or not api.model:
                send_json(self, 503, {'error': {'type': 'api_error', 'message': 'Configure and check an API in the AnviRoute dashboard'}})
                return
            super().do_POST()
