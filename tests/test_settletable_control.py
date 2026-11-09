import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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

        # Set up a hermetic mock environment for Docker and Curl
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmppath = Path(cls.tmpdir.name)

        mock_py = cls.tmppath / "mock_cli.py"
        mock_py.write_text(
            '''import sys, os

tool = sys.argv[1]
args = sys.argv[2:]
full = " ".join(args)

if tool == "docker":
    if "info" in args:
        if os.environ.get("MOCK_DOCKER_DOWN") == "1":
            sys.exit(1)
        print("Client: Docker Engine")
        sys.exit(0)

    if "stop" in args:
        if "cloudflared" in args and os.environ.get("MOCK_STOP_TUNNEL_FAIL") == "1":
            sys.exit(1)
        if os.environ.get("MOCK_STOP_ALL_FAIL") == "1":
            sys.exit(1)
        print("Container stopped")
        sys.exit(0)

    if "up" in args:
        if os.environ.get("MOCK_UP_FAIL") == "1":
            sys.exit(1)
        print("Container started")
        sys.exit(0)

    if "ps" in args:
        if os.environ.get("MOCK_PS_FAIL") == "1":
            print("docker ps failed: daemon communication timeout", file=sys.stderr)
            sys.exit(1)
        # Check filter
        running = os.environ.get("MOCK_RUNNING_CONTAINERS", "")
        filter_name = ""
        for i, a in enumerate(args):
            if a.startswith("name="):
                filter_name = a.split("=", 1)[1]
            elif a == "--filter" and i + 1 < len(args) and args[i + 1].startswith("name="):
                filter_name = args[i + 1].split("=", 1)[1]

        if filter_name and running:
            lines = [line.strip() for line in running.splitlines() if filter_name in line]
            if lines:
                print("\\n".join(lines))
        elif running and not filter_name:
            print(running)
        sys.exit(0)

elif tool == "curl":
    if "127.0.0.1:8000" in full:
        code = os.environ.get("MOCK_LOCAL_STATUS", "200")
        print(code, end="")
        sys.exit(0)
    elif "settle.kybuilds.com" in full:
        code = os.environ.get("MOCK_PUBLIC_STATUS", "530")
        print(code, end="")
        sys.exit(0)

sys.exit(0)
''',
            encoding="utf-8",
        )

        is_win = os.name == "nt"
        if is_win:
            cls.mock_docker = cls.tmppath / "docker.cmd"
            cls.mock_docker.write_text(
                f'@echo off\n"{sys.executable}" "{mock_py}" docker %*\n',
                encoding="utf-8",
            )
            cls.mock_curl = cls.tmppath / "curl.cmd"
            cls.mock_curl.write_text(
                f'@echo off\n"{sys.executable}" "{mock_py}" curl %*\n',
                encoding="utf-8",
            )
            mock_preflight_py = cls.tmppath / "mock_preflight.py"
            mock_preflight_py.write_text(
                'import sys, os\n'
                'if os.environ.get("MOCK_PREFLIGHT_FAIL") == "1":\n'
                '    print("Preflight failed mock check")\n'
                '    sys.exit(1)\n'
                'print("Preflight passed mock check")\n'
                'sys.exit(0)\n',
                encoding="utf-8",
            )
            cls.mock_preflight = cls.tmppath / "preflight.cmd"
            cls.mock_preflight.write_text(
                f'@echo off\n"{sys.executable}" "{mock_preflight_py}" %*\n',
                encoding="utf-8",
            )
        else:
            cls.mock_docker = cls.tmppath / "docker.sh"
            cls.mock_docker.write_text(
                f'#!/bin/sh\nexec "{sys.executable}" "{mock_py}" docker "$@"\n',
                encoding="utf-8",
            )
            cls.mock_docker.chmod(0o755)
            cls.mock_curl = cls.tmppath / "curl.sh"
            cls.mock_curl.write_text(
                f'#!/bin/sh\nexec "{sys.executable}" "{mock_py}" curl "$@"\n',
                encoding="utf-8",
            )
            cls.mock_curl.chmod(0o755)
            mock_preflight_py = cls.tmppath / "mock_preflight.py"
            mock_preflight_py.write_text(
                'import sys, os\n'
                'if os.environ.get("MOCK_PREFLIGHT_FAIL") == "1":\n'
                '    print("Preflight failed mock check")\n'
                '    sys.exit(1)\n'
                'print("Preflight passed mock check")\n'
                'sys.exit(0)\n',
                encoding="utf-8",
            )
            cls.mock_preflight = cls.tmppath / "preflight.sh"
            cls.mock_preflight.write_text(
                f'#!/bin/sh\nexec "{sys.executable}" "{mock_preflight_py}" "$@"\n',
                encoding="utf-8",
            )
            cls.mock_preflight.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def run_ps_script(self, args, env_overrides=None, cwd=REPO_ROOT, use_mocks=False, skip_preflight=True):
        cmd = [
            PS_BIN,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
        ]
        if use_mocks:
            cmd.extend([
                "-DockerCmd",
                str(self.mock_docker),
                "-CurlCmd",
                str(self.mock_curl),
            ])
            if skip_preflight:
                cmd.append("-SkipPreflight")
        cmd.extend(args)

        env = os.environ.copy()
        env.setdefault("SETTLETABLE_MAX_PROBE_ATTEMPTS", "2")
        env.setdefault("SETTLETABLE_PROBE_INTERVAL_SEC", "0")
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)

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
        res = self.run_ps_script(["status"], use_mocks=True)
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
        res = self.run_ps_script(["status"], cwd=temp_dir, use_mocks=True)
        self.assertEqual(res.returncode, 0, f"status from external cwd failed: {res.stderr}")
        self.assertIn("SettleTable Environment & Container Status", res.stdout)

    # -----------------------------------------------------------------------
    # Focused Mock Tests: Docker Daemon & Failure Modes
    # -----------------------------------------------------------------------

    def test_docker_unreachable_fails_closed(self):
        res = self.run_ps_script(
            ["status"],
            env_overrides={"MOCK_DOCKER_DOWN": "1"},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Docker daemon is not running or unreachable", res.stdout)

    def test_start_local_fails_if_stop_tunnel_fails(self):
        res = self.run_ps_script(
            ["start-local"],
            env_overrides={"MOCK_STOP_TUNNEL_FAIL": "1"},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Failed to execute docker compose stop cloudflared", res.stdout)

    def test_start_local_fails_if_volume_preflight_fails(self):
        res = self.run_ps_script(
            ["start-local", "-PreflightCmd", str(self.mock_preflight)],
            env_overrides={
                "MOCK_PREFLIGHT_FAIL": "1",
            },
            use_mocks=True,
            skip_preflight=False,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Storage volume pre-flight check failed", res.stdout)

    def test_start_local_fails_if_tunnel_still_running_after_stop(self):
        res = self.run_ps_script(
            ["start-local"],
            env_overrides={"MOCK_RUNNING_CONTAINERS": "settletable_tunnel_id settletable_tunnel"},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Cloudflare tunnel container is still running after stop request", res.stdout)

    def test_start_local_fails_if_local_health_probe_times_out(self):
        res = self.run_ps_script(
            ["start-local"],
            env_overrides={
                "MOCK_LOCAL_STATUS": "000",
                "MOCK_RUNNING_CONTAINERS": "",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("local health check did not return 200 within", res.stdout)

    def test_start_local_succeeds_when_tunnel_stopped_and_app_healthy(self):
        res = self.run_ps_script(
            ["start-local"],
            env_overrides={
                "MOCK_LOCAL_STATUS": "200",
                "MOCK_RUNNING_CONTAINERS": "",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 0, f"start-local failed: {res.stderr}\n{res.stdout}")
        self.assertIn("[SUCCESS] SettleTable Local Server is Active", res.stdout)
        self.assertIn("Public Ingress: STOPPED", res.stdout)

    def test_start_public_fails_if_volume_preflight_fails(self):
        res = self.run_ps_script(
            ["start-public", "-PreflightCmd", str(self.mock_preflight)],
            env_overrides={
                "MOCK_PREFLIGHT_FAIL": "1",
            },
            use_mocks=True,
            skip_preflight=False,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Storage volume pre-flight check failed", res.stdout)

    def test_start_public_fails_if_local_health_probe_fails_and_stops_tunnel(self):
        res = self.run_ps_script(
            ["start-public"],
            env_overrides={
                "MOCK_LOCAL_STATUS": "000",
                "MOCK_RUNNING_CONTAINERS": "settletable_tunnel",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Local application health check failed", res.stdout)
        self.assertIn("Stopping Cloudflare tunnel connector to prevent exposing an unhealthy application", res.stdout)

    def test_start_public_fails_if_tunnel_container_not_running(self):
        res = self.run_ps_script(
            ["start-public"],
            env_overrides={
                "MOCK_LOCAL_STATUS": "200",
                "MOCK_RUNNING_CONTAINERS": "",  # no tunnel running
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Cloudflare tunnel container settletable_tunnel is not running", res.stdout)

    def test_start_public_fails_if_public_edge_probe_fails(self):
        res = self.run_ps_script(
            ["start-public"],
            env_overrides={
                "MOCK_LOCAL_STATUS": "200",
                "MOCK_PUBLIC_STATUS": "530",
                "MOCK_RUNNING_CONTAINERS": "settletable_tunnel",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("public HTTPS endpoint did not return 200 within", res.stdout)

    def test_start_public_succeeds_when_all_probes_healthy(self):
        res = self.run_ps_script(
            ["start-public"],
            env_overrides={
                "MOCK_LOCAL_STATUS": "200",
                "MOCK_PUBLIC_STATUS": "200",
                "MOCK_RUNNING_CONTAINERS": "settletable_tunnel",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 0, f"start-public failed: {res.stderr}\n{res.stdout}")
        self.assertIn("[SUCCESS] SettleTable Live Public Service is Active", res.stdout)
        self.assertIn("https://settle.kybuilds.com", res.stdout)

    def test_stop_public_fails_if_docker_stop_fails(self):
        res = self.run_ps_script(
            ["stop-public"],
            env_overrides={"MOCK_STOP_TUNNEL_FAIL": "1"},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Failed to execute docker compose stop cloudflared", res.stdout)

    def test_stop_public_fails_if_tunnel_still_running_after_stop(self):
        res = self.run_ps_script(
            ["stop-public"],
            env_overrides={"MOCK_RUNNING_CONTAINERS": "settletable_tunnel"},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("settletable_tunnel is still running after stop command", res.stdout)

    def test_stop_public_succeeds_and_distinguishes_edge_status(self):
        res = self.run_ps_script(
            ["stop-public"],
            env_overrides={
                "MOCK_RUNNING_CONTAINERS": "",
                "MOCK_PUBLIC_STATUS": "530",
                "MOCK_LOCAL_STATUS": "200",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 0, f"stop-public failed: {res.stderr}\n{res.stdout}")
        self.assertIn("Host Connector:  STOPPED (settletable_tunnel verified inactive)", res.stdout)
        self.assertIn("HTTP 530 Tunnel Inactive", res.stdout)
        self.assertIn("Local App:       STILL ACTIVE & ACCESSIBLE", res.stdout)

    def test_stop_all_fails_if_docker_stop_fails(self):
        res = self.run_ps_script(
            ["stop-all"],
            env_overrides={"MOCK_STOP_ALL_FAIL": "1"},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Failed to execute docker compose stop", res.stdout)

    def test_stop_all_fails_if_containers_still_running_after_stop(self):
        res = self.run_ps_script(
            ["stop-all"],
            env_overrides={"MOCK_RUNNING_CONTAINERS": "settletable_app"},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("settletable_app is still running", res.stdout)

    def test_stop_all_succeeds_and_is_idempotent(self):
        res = self.run_ps_script(
            ["stop-all"],
            env_overrides={"MOCK_RUNNING_CONTAINERS": ""},
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 0, f"stop-all failed: {res.stderr}\n{res.stdout}")
        self.assertIn("[STATUS] All SettleTable Containers Stopped", res.stdout)
        self.assertIn("Container State: All containers stopped cleanly and verified inactive", res.stdout)
        self.assertIn("encrypted backup procedure to", res.stdout)

    def test_stop_public_fails_if_docker_ps_query_fails(self):
        res = self.run_ps_script(
            ["stop-public"],
            env_overrides={
                "MOCK_STOP_TUNNEL_FAIL": "0",
                "MOCK_PS_FAIL": "1",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Failed to verify container state after stop command", res.stdout)

    def test_stop_all_fails_if_docker_ps_query_fails(self):
        res = self.run_ps_script(
            ["stop-all"],
            env_overrides={
                "MOCK_STOP_ALL_FAIL": "0",
                "MOCK_PS_FAIL": "1",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Failed to verify container state after stop command", res.stdout)

    def test_start_local_fails_if_docker_ps_query_fails(self):
        res = self.run_ps_script(
            ["start-local"],
            env_overrides={
                "MOCK_PS_FAIL": "1",
            },
            use_mocks=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Failed to query Docker container state for settletable_tunnel", res.stdout)

    def test_skip_preflight_rejected_with_production_docker(self):
        res = self.run_ps_script(
            ["start-public", "-SkipPreflight"],
            use_mocks=False,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("-SkipPreflight is a test-only parameter and cannot be used with production Docker", res.stdout)

    def test_preflight_cmd_rejected_with_production_docker(self):
        res = self.run_ps_script(
            ["start-public", "-PreflightCmd", "fake-preflight"],
            use_mocks=False,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("-PreflightCmd is a test-only parameter and cannot be used with production Docker", res.stdout)


if __name__ == "__main__":
    unittest.main()
