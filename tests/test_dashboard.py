import shutil
import subprocess
import unittest
from pathlib import Path

class DashboardTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed only for dashboard JavaScript tests')
    def test_dashboard_interactions(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/test_dashboard.js'], cwd=root, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
