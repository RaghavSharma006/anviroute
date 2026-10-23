import base64
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

from anviroute import __version__

ROOT = Path(__file__).resolve().parents[1]


class LightweightReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_release.py')], check=True, capture_output=True)

    def test_download_and_app_stay_small(self):
        self.assertLess((ROOT / 'dist/AnviRoute.cmd').stat().st_size, 25_000)
        self.assertLess((ROOT / 'dist/anviroute.pyz').stat().st_size, 12_000)

    def test_payload_integrity_and_no_legacy_modules(self):
        text = (ROOT / 'dist/AnviRoute.cmd').read_text()
        encoded = re.search(r'(?ms)^#BEGIN_PAYLOAD\n(.*?)^#END_PAYLOAD', text).group(1)
        app = (ROOT / 'dist/anviroute.pyz').read_bytes()
        self.assertEqual(base64.b64decode(encoded), app)
        self.assertIn(hashlib.sha256(app).hexdigest(), text)
        with zipfile.ZipFile(ROOT / 'dist/anviroute.pyz') as bundle:
            self.assertFalse(any('kagglelink' in name for name in bundle.namelist()))

    def test_zipapp_runs_in_isolation_without_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-I', str(ROOT / 'dist/anviroute.pyz'), '--version'],
                                    cwd=folder, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __version__)

    @unittest.skipUnless(os.name == 'nt', 'Windows single-file installer')
    def test_single_download_installs_without_pip_or_venv(self):
        with tempfile.TemporaryDirectory(prefix='AnviRoute-test-') as folder:
            install = Path(folder) / 'Installed'
            env = {**os.environ, 'ANVIROUTE_INSTALL_ROOT': str(install), 'ANVIROUTE_SKIP_PATH_UPDATE': '1'}
            result = subprocess.run([str(ROOT / 'dist/AnviRoute.cmd'), '--version'], cwd=folder, env=env,
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((install / 'runtime').exists())
            self.assertTrue((install / 'anviroute.pyz').exists())
            check = subprocess.run([str(install / 'bin/anviroute.cmd'), '--version'], cwd=folder, env=env,
                                   capture_output=True, text=True, timeout=15)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(check.stdout.strip(), __version__)


if __name__ == '__main__':
    unittest.main()
