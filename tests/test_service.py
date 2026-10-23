import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from anviroute.cli import main
from anviroute.service import Router
from anviroute.runtime import start_server
from anviroute.common import BridgeError
from helpers import request


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.router = Router(0, self.temp.name)
        start_server(self.router)
        self.url = self.router.address

    def tearDown(self):
        self.router.shutdown()
        self.router.server_close()
        self.temp.cleanup()

    def control(self, action, data):
        return request(self.url + '/control/' + action, self.router.token, data)

    def test_dashboard_and_admin_auth(self):
        with urllib.request.urlopen(self.url) as r:
            self.assertIn(b'Connection path', r.read())
        with self.assertRaisesRegex(BridgeError, '401'):
            request(self.url + '/control/status')

    def test_second_router_cannot_claim_running_port(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OSError):
                Router(self.router.server_port, folder)

    def test_profile_key_not_in_status_or_disk(self):
        self.control('save', {'name': 'Kaggle', 'url': 'https://example.com', 'key': 'private-api-secret'})
        status = request(self.url + '/control/status', self.router.token)
        self.assertNotIn('private-api-secret', json.dumps(status))
        self.assertNotIn('private-api-secret', (Path(self.temp.name)/'providers.json').read_text())
        self.assertFalse(status['ready'])

    def test_model_check_and_switch(self):
        first = self.control('save', {'name': 'one', 'url': 'https://one.example', 'key': 'key1'})['id']
        second = self.control('save', {'name': 'two', 'url': 'https://two.example', 'key': 'key2'})['id']
        with patch.object(self.router.api, 'call', return_value={'data': [{'id': 'model-a'}]}), \
             patch.object(self.router.api, 'check', return_value={'content': []}):
            self.control('check', {})
        self.assertTrue(self.router.status()['ready'])
        self.assertEqual(self.router.model, 'model-a')
        self.control('activate', {'id': second})
        self.assertEqual(self.router.api.key, 'key2')
        self.assertFalse(self.router.status()['ready'])

    def test_cross_origin_admin_write_rejected(self):
        req = urllib.request.Request(self.url + '/control/save', data=b'{}', headers={
            'Authorization': 'Bearer ' + self.router.token, 'Origin': 'https://attacker.example'})
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        self.assertEqual(exc.exception.code, 403)
        exc.exception.close()

    def test_named_profile_and_key_survive_restart(self):
        self.control('save', {'name': 'kaggle-qwen', 'url': 'https://example.com', 'key': 'secret-to-encrypt', 'model': 'qwen'})
        other = Router(0, self.temp.name)
        try:
            other.activate_name('KAGGLE-QWEN')
            self.assertEqual(other.model, 'qwen')
            self.assertEqual(other.api.key, 'secret-to-encrypt' if os.name == 'nt' else '')
            self.assertFalse(other.checked)
            self.assertNotIn('encrypted_key', json.dumps(other.status()))
        finally:
            other.server_close()

    def test_duplicate_profile_name_rejected(self):
        self.control('save', {'name': 'one', 'url': 'https://example.com'})
        with self.assertRaisesRegex(BridgeError, 'unique'):
            self.router.control('save', {'name': 'ONE', 'url': 'https://example.org'})

    def test_logs_are_persistent_bounded_and_redacted(self):
        self.control('save', {'name': 'test', 'url': 'https://example.com', 'key': 'do-not-log-this'})
        self.router.record('upstream', 'Failed do-not-log-this ' + self.router.token, False, 401)
        content = (Path(self.temp.name)/'events.jsonl').read_text()
        self.assertNotIn('do-not-log-this', content)
        self.assertNotIn(self.router.token, content)
        self.assertIn('[redacted]', content)
        other = Router(0, self.temp.name)
        try:
            self.assertTrue(any(e.get('status') == 401 for e in other.events))
            self.assertEqual(other.events.maxlen, 500)
        finally:
            other.server_close()
        with urllib.request.urlopen(self.url + '/logs') as response:
            self.assertIn(b'Export JSON', response.read())

    def test_missing_saved_model_does_not_silently_switch(self):
        self.control('save', {'name': 'one', 'url': 'https://example.com', 'model': 'missing'})
        with patch.object(self.router.api, 'call', return_value={'data': [{'id': 'available'}]}):
            with self.assertRaisesRegex(BridgeError, 'unavailable'):
                self.router.control('check', {})
        self.assertFalse(self.router.checked)

    def test_second_terminal_launch_uses_existing_service(self):
        self.control('save', {'name': 'one', 'url': 'https://one.example', 'model': 'test-model'})
        self.router.checked = True
        descriptor = Path(self.temp.name)/'service.json'
        descriptor.write_text(json.dumps({'url': self.url, 'token': self.router.token}))
        with patch('anviroute.cli.data_dir', return_value=Path(self.temp.name)), \
             patch('anviroute.cli.shutil.which', return_value='fake-claude'), \
             patch('anviroute.cli.subprocess.call', return_value=0) as child, \
             patch('sys.stdout', new=io.TextIOWrapper(io.BytesIO(), encoding='cp1252')), \
             patch('builtins.input', side_effect=AssertionError('No connection prompts in terminal 2')):
            self.assertEqual(main(['run', 'claude']), 0)
            self.assertEqual(child.call_args.kwargs['env']['ANTHROPIC_BASE_URL'], self.url)
