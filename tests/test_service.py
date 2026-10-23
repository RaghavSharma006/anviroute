import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from anviroute.cli import main
from anviroute.service import Router
from anviroute.runtime import start_server
from kagglelink.common import request, BridgeError


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

    def test_second_terminal_launch_uses_existing_service(self):
        self.control('save', {'name': 'one', 'url': 'https://one.example', 'model': 'test-model'})
        self.router.checked = True
        descriptor = Path(self.temp.name)/'service.json'
        descriptor.write_text(json.dumps({'url': self.url, 'token': self.router.token}))
        with patch('anviroute.cli.data_dir', return_value=Path(self.temp.name)), \
             patch('anviroute.cli.shutil.which', return_value='fake-claude'), \
             patch('anviroute.cli.subprocess.call', return_value=0) as child, \
             patch('builtins.input', side_effect=AssertionError('No connection prompts in terminal 2')):
            self.assertEqual(main(['run', 'claude']), 0)
            self.assertEqual(child.call_args.kwargs['env']['ANTHROPIC_BASE_URL'], self.url)
