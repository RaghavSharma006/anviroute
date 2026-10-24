import shutil
import subprocess
import unittest
from pathlib import Path

class PasteTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed only for dashboard JavaScript tests')
    def test_real_dashboard_parser(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/test_paste.js'], cwd=root, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
