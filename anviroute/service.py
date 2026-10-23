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
from urllib.parse import urlsplit

from . import __version__
from .api import API
from .common import BridgeError, read_body, send_json
from .dashboard import HTML
from .server import Handler, Server
from .vault import seal, unlock


def data_dir():
    return Path(os.environ.get('LOCALAPPDATA', Path.home()/'.config'))/'AnviRoute'


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
        self.last_error = None
        try:
            saved = json.loads((self.folder/'providers.json').read_text())
            for p in saved['providers']:
                try:
                    key = unlock(p.get('encrypted_key'))
                except BridgeError:
                    key = ''
                self.profiles[p['id']] = {**p, 'key': key}
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
            self.activate(self.active)
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
            self.record('upstream', str(exc), False, getattr(exc, 'status', None))

    def status(self):
        with self.lock:
            return {'product': 'AnviRoute', 'version': __version__, 'address': self.address,
                    'active': self.active, 'model': self.model, 'ready': bool(self.api and self.model and self.checked),
                    'providers': [{**{k: v for k, v in p.items() if k not in ('key', 'encrypted_key')}, 'key_saved': bool(p.get('encrypted_key'))} for p in list(self.profiles.values())],
                    'credential_storage': 'Windows account encryption' if os.name == 'nt' else 'Memory only on this platform',
                    'events': list(self.events), 'client_seen': self.client_seen, 'upstream': self.upstream}

    def control(self, action, data):
        if any(not isinstance(v, str) for k, v in data.items() if k in ('id', 'name', 'url', 'key', 'model', 'format')):
            raise BridgeError('Configuration fields must be text')
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
            models = self.models(api)
            if not models:
                raise BridgeError('API returned no models')
            if api.model and api.model not in models:
                raise BridgeError('Saved model is unavailable. Discover models and select an available model.')
            if not api.model:
                api.model = models[0]
            api.check()
            with self.lock:
                if self.api is api:
                    self.model = api.model
                    self.profiles[identifier].update(model=api.model, format=api.format)
                    self.persist()
                    self.upstream = 'Authentication, model and inference OK'
                    self.checked = True
            self.record('upstream', 'Authentication, model and inference OK', status=200)
            return {'message': 'API and model inference OK', 'model': api.model}
        raise BridgeError('Unknown control action')

    @staticmethod
    def models(api):
        result = api.call('/models')
        return [m['id'] for m in result.get('data', []) if isinstance(m, dict) and isinstance(m.get('id'), str)]

    def mutate(self, action, data):
        if action == 'save':
            identifier = data.get('id') or secrets.token_hex(8)
            previous = self.profiles.get(identifier, {})
            name = data.get('name', 'API').strip()[:80]
            if not name or any(p['name'].casefold() == name.casefold() and p['id'] != identifier for p in self.profiles.values()):
                raise BridgeError('Use a unique profile name')
            api = API(data.get('url', ''), data.get('key') or previous.get('key', ''),
                      data.get('model', '').strip(), data.get('format', 'openai'))
            if api.format not in ('openai', 'anthropic'):
                raise BridgeError('Unknown API format')
            self.profiles[identifier] = {'id': identifier, 'name': name,
                'url': api.url, 'key': api.key, 'encrypted_key': seal(api.key), 'model': api.model, 'format': api.format}
            if self.active == identifier or self.active is None:
                self.activate(identifier)
            self.persist()
            return {'id': identifier}
        if action == 'activate':
            self.activate(data.get('id'))
            return {'ok': True}
        if action == 'remove':
            identifier = data.get('id')
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
            self.activate(self.active)
            return {'ok': True}
        raise BridgeError('Unknown control action')


class DashboardHandler(Handler):
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
        if path in ('/', '/connections', '/logs'):
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
                self.server.record('upstream' if path.endswith(('/check', '/models')) else 'adapter', message, False, getattr(exc, 'status', 400))
                if path.endswith(('/check', '/models')):
                    self.server.upstream = message
                send_json(self, 400, {'error': message})
        else:
            if not self.authorized():
                return
            self.server.client_seen = datetime.now().strftime('%H:%M:%S')
            self.server.record('client', 'Claude request received')
            if not self.server.api or not self.server.model:
                send_json(self, 503, {'error': {'type': 'api_error', 'message': 'Configure and check an API in the AnviRoute dashboard'}})
                return
            super().do_POST()
