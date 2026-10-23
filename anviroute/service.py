"""Persistent loopback router, dashboard, and multi-provider control plane."""

from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
from urllib.parse import urlsplit

from . import __version__
from .api import API, UpstreamError
from .common import BridgeError, read_body, send_json
from .dashboard import HTML
from .server import Handler, Server


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
        self.events = deque(maxlen=40)
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
            self.profiles = {p['id']: {**p, 'key': ''} for p in saved['providers']}
            self.active = saved.get('active')
        except (OSError, ValueError, KeyError, TypeError):
            pass
        # Initialize directly; no provider is required to start the dashboard.
        from http.server import ThreadingHTTPServer
        ThreadingHTTPServer.__init__(self, ('127.0.0.1', port), DashboardHandler)
        self.address = f'http://127.0.0.1:{self.server_port}'
        self.record('adapter', 'Service started', True)

    def persist(self):
        write_private(self.folder/'providers.json', {'active': self.active, 'providers': [
            {k: v for k, v in p.items() if k != 'key'} for p in list(self.profiles.values())]})

    def record(self, stage, message, ok=True):
        with self.lock:
            self.events.append({'time': datetime.now().strftime('%H:%M:%S'), 'stage': stage, 'message': message, 'ok': ok})

    def report_error(self, status, message):
        super().report_error(status, message)
        stage = 'upstream' if message.startswith('Upstream') or 'connection' in message.lower() else 'adapter'
        self.record(stage, message, False)
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

    def status(self):
        with self.lock:
            return {'product': 'AnviRoute', 'version': __version__, 'address': self.address,
                    'active': self.active, 'model': self.model, 'ready': bool(self.api and self.model and self.checked),
                    'providers': [{k: v for k, v in p.items() if k != 'key'} for p in list(self.profiles.values())],
                    'events': list(self.events), 'client_seen': self.client_seen, 'upstream': self.upstream}

    def control(self, action, data):
        if action == 'save':
            identifier = data.get('id') or secrets.token_hex(8)
            previous = self.profiles.get(identifier, {})
            api = API(data.get('url', ''), data.get('key') or previous.get('key', ''),
                      data.get('model', '').strip(), data.get('format', 'openai'))
            if api.format not in ('openai', 'anthropic'):
                raise BridgeError('Unknown API format')
            self.profiles[identifier] = {'id': identifier, 'name': data.get('name', 'API')[:80],
                'url': api.url, 'key': api.key, 'model': api.model, 'format': api.format}
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
        api = self.api  # Keep a request bound to one provider while the UI can switch.
        if action == 'models':
            result = api.call('/models')
            return {'models': [m['id'] for m in result.get('data', []) if isinstance(m.get('id'), str)]}
        if action == 'model':
            selected = data.get('model', '').strip()
            if not selected:
                raise BridgeError('Choose a model')
            self.profiles[self.active]['model'] = selected
            self.activate(self.active)
            return {'ok': True}
        if action == 'check':
            self.record('upstream', 'Checking authentication and model list')
            models = self.control('models', {})['models']
            if not models:
                raise BridgeError('API returned no models')
            if api.model not in models:
                api.model = models[0]
            api.check()
            if self.api is api:
                self.model = api.model
                self.profiles[self.active].update(model=api.model, format=api.format)
                self.persist()
                self.upstream = 'Authentication, model and inference OK'
                self.checked = True
            self.record('upstream', 'Authentication, model and inference OK')
            return {'message': 'API and model inference OK', 'model': api.model}
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
        if path == '/':
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
                self.server.record('upstream' if path.endswith(('/check', '/models')) else 'adapter', message, False)
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
