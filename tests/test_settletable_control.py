import os
from pathlib import Path
import shutil
import subprocess
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "tools" / "SettleTable-Control.ps1"
PS_BIN = (
    shutil.which("powershell.exe")
    or shutil.which("powershell")
    or shutil.which("pwsh")
)


class SettleTableControlScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT_PATH.exists():
            raise unittest.SkipTest(f"Control script not found at {SCRIPT_PATH}")
        if not PS_BIN:
            raise unittest.SkipTest("PowerShell is not installed on this host")

    def run_ps_script(self, args, cwd=REPO_ROOT):
        cmd = [
            PS_BIN,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            *args,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)

    def test_script_file_exists(self):
        self.assertTrue(SCRIPT_PATH.is_file(), "SettleTable-Control.ps1 must exist")

    def test_help_action_exits_zero(self):
        res = self.run_ps_script(["help"])
        self.assertEqual(res.returncode, 0, f"help failed: {res.stderr}")
        self.assertIn("SettleTable Windows Host Lifecycle Controller", res.stdout)
        self.assertIn("start-local", res.stdout)
        self.assertIn("start-public", res.stdout)
        self.assertIn("stop-public", res.stdout)
        self.assertIn("stop-all", res.stdout)
        self.assertIn("status", res.stdout)

    def test_help_dash_h_exits_zero(self):
        res = self.run_ps_script(["-h"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("SettleTable", res.stdout)

    def test_invalid_action_exits_one(self):
        res = self.run_ps_script(["nonexistent-command"])
        self.assertEqual(res.returncode, 1)
        self.assertIn("Unknown action", res.stdout)
        self.assertIn("Usage:", res.stdout)

    def test_status_action_exits_zero_and_protects_secrets(self):
        res = self.run_ps_script(["status"])
        self.assertEqual(res.returncode, 0, f"status failed: {res.stderr}")
        self.assertIn("SettleTable Environment & Container Status", res.stdout)
        self.assertIn("Endpoint Health Probes:", res.stdout)
        self.assertIn("Local Ingress", res.stdout)
        self.assertIn("Public Edge", res.stdout)
        # Assert no secrets or tokens leaked
        self.assertNotIn("TUNNEL_TOKEN", res.stdout)
        self.assertNotIn("settletable_session", res.stdout)
        self.assertNotIn("eyJhIj", res.stdout)

    def test_script_resolves_root_from_external_cwd(self):
        temp_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", ".")))
        res = self.run_ps_script(["status"], cwd=temp_dir)
        self.assertEqual(res.returncode, 0, f"status from external cwd failed: {res.stderr}")
        self.assertIn("SettleTable Environment & Container Status", res.stdout)


if __name__ == "__main__":
    unittest.main()
