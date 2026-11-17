import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch, Mock

from cfx_devkit import connection
from cfx_devkit import livecontrol, clientlaunch, gameinput, fxserverlaunch
from cfx_devkit import delegation

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "install.py").is_file())
spec = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def fixture(self, folder):
        workspace = folder / "server"
        (workspace / "resources").mkdir(parents=True)
        (workspace / "server.cfg").write_text("# owner configuration\n")
        home = folder / "home"
        home.mkdir()
        return workspace, home

    def test_preview_has_no_side_effects_or_leaked_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, home = self.fixture(root)
            python, changes = installer.prepare(workspace, "freebuff", home=home)
            self.assertFalse((workspace / ".cfx-devkit").exists())
            self.assertFalse((home / ".agents").exists())
            state = next(json.loads(text) for path, text in changes if path.name == "connection.json")
            token = state["env"]["CFX_LIVE_TOKEN"]
            config = json.loads(changes[-1][1])
            self.assertNotIn(token, json.dumps(config))
            self.assertNotIn("CFX_LIVE_TOKEN", config["mcpServers"]["cfx-development"]["env"])
            self.assertIn("CFX_DEVKIT_DATA_DIR", state["env"])

    def test_repeat_setup_preserves_owner_settings_and_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            host = home / ".agents/mcp.json"
            host.parent.mkdir()
            host.write_text(json.dumps({"mcpServers": {"unrelated": {"command": "existing"}}}))
            _, changes = installer.prepare(workspace, "freebuff", home=home)
            for path, text in changes:
                installer.write_private(path, text)
            original = (workspace / ".cfx-devkit/connection.json").read_bytes()
            _, repeated = installer.prepare(workspace, "freebuff", home=home)
            for path, text in repeated:
                installer.write_private(path, text)
            self.assertEqual(original, (workspace / ".cfx-devkit/connection.json").read_bytes())
            self.assertEqual((workspace / "server.cfg").read_text().count(installer.BEGIN), 1)
            self.assertIn("unrelated", json.loads(host.read_text())["mcpServers"])
            self.assertIn("lua54 'yes'", (workspace / "resources/cfx-devkit-live/fxmanifest.lua").read_text())
            self.assertIn("setr devkit_live_client_enabled 0", (workspace / ".cfx-devkit/connection.cfg").read_text())

    def test_ambiguous_server_and_outside_target_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            (workspace / "other").mkdir()
            (workspace / "other/server.cfg").write_text("")
            with self.assertRaises(ValueError):
                installer.prepare(workspace, "freebuff", home=home)
            with self.assertRaises(ValueError):
                installer.prepare(workspace, "freebuff", server_cfg=home / "server.cfg", home=home)
            self.assertFalse((home / ".agents").exists())

    def test_existing_resource_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            resource = workspace / "resources/cfx-devkit-live"
            resource.mkdir()
            (resource / "server.lua").write_text("owner customization")
            with self.assertRaises(ValueError):
                installer.prepare(workspace, "freebuff", home=home)
            self.assertEqual((resource / "server.lua").read_text(), "owner customization")

    def test_failed_write_rolls_back_preceding_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "freebuff", home=home)
            original_write = installer.write_private
            count = 0
            def failing_write(path, content):
                nonlocal count
                count += 1
                if count == 3:
                    raise OSError("simulated disk failure")
                original_write(path, content)
            with patch.object(installer, "write_private", side_effect=failing_write):
                with self.assertRaises(OSError):
                    installer.apply_changes(changes)
            self.assertEqual((workspace / "server.cfg").read_text(), "# owner configuration\n")
            self.assertFalse((workspace / "resources/cfx-devkit-live/server.lua").exists())
            self.assertFalse((home / ".agents/mcp.json").exists())

    def test_codex_configuration_round_trip(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("TOML validation requires Python 3.11+")
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "codex", home=home)
            data = tomllib.loads(changes[-1][1])
            self.assertEqual(len(data["mcp_servers"]), 2)

    def test_settings_reject_arbitrary_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"env": {"PYTHONPATH": "untrusted"}}))
            with self.assertRaises(ValueError):
                connection.load_settings(path)

    def test_connection_starts_broker_without_arming(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"env": {}}))
            broker = Mock()
            with patch("sys.argv", ["connection", "--settings", str(path)]), \
                 patch.object(connection.livecontrol, "make_server", return_value=broker), \
                 patch.object(connection.livecontrol, "arm") as arm, \
                 patch.object(connection.server, "main") as main:
                connection.main()
            arm.assert_not_called()
            main.assert_called_once()
            broker.shutdown.assert_called_once()
            broker.server_close.assert_called_once()

    def test_unattended_opt_in_revocation_and_token_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "freebuff", home=home, unattended=True)
            installer.apply_changes(changes)
            env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
            with patch.dict(os.environ, env):
                state = livecontrol.status()
                self.assertTrue(state["armed"])
                self.assertEqual(state["authorization_mode"], "owner-delegated-until-revoked")
                self.assertIsNone(state["arm_expires_at"])
                self.assertTrue(clientlaunch.permission()["approved"])
                self.assertTrue(gameinput.permission()["approved"])
                request = livecontrol.submit("server_resources")
                self.assertFalse(request["executed"])
                with patch.dict(os.environ, {"CFX_LIVE_TOKEN": "wrong-token" * 5}):
                    self.assertFalse(livecontrol.status()["armed"])
                livecontrol.disarm()
                self.assertFalse(livecontrol.status()["armed"])
                self.assertFalse(clientlaunch.permission()["approved"])
                self.assertFalse(gameinput.permission()["approved"])
                with self.assertRaises(ValueError):
                    livecontrol.submit("server_resources")

    def test_unattended_launch_is_bound_to_selected_server(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "freebuff", home=home, unattended=True, launch_target="a" * 64)
            installer.apply_changes(changes)
            env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
            selected = {"config": str(workspace / "server.cfg"),
                        "executable": str(workspace / "FXServer.exe"), "target_id": "a" * 64}
            with patch.dict(os.environ, env), patch.object(fxserverlaunch, "configuration", return_value={"selected": selected}):
                self.assertTrue(fxserverlaunch.permission()["approved"])
                selected["target_id"] = "b" * 64
                self.assertFalse(fxserverlaunch.permission()["approved"])
                selected["target_id"] = "a" * 64
                selected["config"] = str(workspace / "different-server.cfg")
                self.assertFalse(fxserverlaunch.permission()["approved"])

    def test_default_install_stays_locked_and_preserves_host_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            approvals = home / ".freebuff/mcp.json"
            approvals.parent.mkdir()
            approvals.write_text('{"servers":{"existing":{"enabled":false}}}')
            before = approvals.read_bytes()
            _, changes = installer.prepare(workspace, "freebuff", home=home)
            installer.apply_changes(changes)
            env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
            with patch.dict(os.environ, env):
                self.assertFalse(livecontrol.status()["armed"])
                self.assertFalse(clientlaunch.permission()["approved"])
            self.assertEqual(approvals.read_bytes(), before)

    def test_delegated_client_disarm_revokes_only_that_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "freebuff", home=home, unattended=True)
            installer.apply_changes(changes)
            env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
            with patch.dict(os.environ, env):
                clientlaunch.disarm()
                self.assertFalse(clientlaunch.permission()["approved"])
                self.assertTrue(livecontrol.status()["armed"])

    def test_malformed_policy_roots_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "freebuff", home=home, unattended=True)
            installer.apply_changes(changes)
            env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
            with patch.dict(os.environ, env):
                for value in ([], None, True, "text", 7, {"permissions": [None]}):
                    Path(env["CFX_LIVE_POLICY_FILE"]).write_text(json.dumps(value))
                    self.assertIsNone(delegation.policy())
                    self.assertIsNone(delegation.allows("full-control"))
                    self.assertFalse(delegation.revoke()["revoked"])

    def test_revoke_persists_when_config_missing_or_token_mismatched(self):
        for condition in ("missing-config", "wrong-token", "disabled"):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as temporary:
                workspace, home = self.fixture(Path(temporary))
                _, changes = installer.prepare(workspace, "freebuff", home=home, unattended=True)
                installer.apply_changes(changes)
                env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
                cfg = workspace / "server.cfg"
                original_cfg = cfg.read_bytes()
                policy_path = Path(env["CFX_LIVE_POLICY_FILE"])
                data = json.loads(policy_path.read_text())
                with patch.dict(os.environ, env):
                    if condition == "missing-config":
                        cfg.unlink()
                    elif condition == "wrong-token":
                        os.environ["CFX_LIVE_TOKEN"] = "incorrect-token" * 5
                    else:
                        data["enabled"] = False
                        policy_path.write_text(json.dumps(data))
                    self.assertFalse(livecontrol.status()["armed"])
                    result = livecontrol.disarm()
                    self.assertTrue(result["delegation_revocation"]["revoked"])
                    cfg.write_bytes(original_cfg)
                    os.environ["CFX_LIVE_TOKEN"] = env["CFX_LIVE_TOKEN"]
                    data["enabled"] = True
                    policy_path.write_text(json.dumps(data))
                    self.assertFalse(livecontrol.status()["armed"])

    def test_concurrent_scoped_and_full_revocations_are_monotonic(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "freebuff", home=home, unattended=True)
            installer.apply_changes(changes)
            env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
            with patch.dict(os.environ, env):
                barrier = threading.Barrier(2)
                original = delegation._identity
                def snapshot():
                    value = original()
                    barrier.wait(timeout=5)
                    return value
                with patch.object(delegation, "_identity", side_effect=snapshot), ThreadPoolExecutor(2) as workers:
                    tasks = [workers.submit(delegation.revoke), workers.submit(delegation.revoke, "client-launch")]
                    for task in tasks:
                        task.result(timeout=6)
                self.assertIsNone(delegation.allows("full-control"))
                self.assertIsNone(delegation.allows("client-launch"))

    def test_revoke_cancels_submission_that_checked_authorization_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, home = self.fixture(Path(temporary))
            _, changes = installer.prepare(workspace, "freebuff", home=home, unattended=True)
            installer.apply_changes(changes)
            env = connection.load_settings(workspace / ".cfx-devkit/connection.json")
            with patch.dict(os.environ, env):
                seen, resume = threading.Event(), threading.Event()
                original = livecontrol._active
                data = delegation.policy()
                def paused(conn):
                    value = original(conn)
                    seen.set()
                    if not resume.wait(5):
                        raise AssertionError("Test did not release submission")
                    return value
                with patch.object(livecontrol, "_active", side_effect=paused), ThreadPoolExecutor(2) as workers:
                    enqueue = workers.submit(livecontrol.submit, "server_resources")
                    self.assertTrue(seen.wait(3))
                    revoke = workers.submit(livecontrol.disarm)
                    marker = delegation.marker(data, "_all")
                    try:
                        deadline = time.monotonic() + 3
                        while not marker.exists() and time.monotonic() < deadline:
                            time.sleep(0.01)
                        self.assertTrue(marker.exists())
                    finally:
                        resume.set()
                    request = enqueue.result(timeout=6)
                    revoke.result(timeout=6)
                self.assertEqual(livecontrol.status(request["id"])["request"]["status"], "cancelled")

    @unittest.skipUnless(os.name == "nt", "Windows DACL test")
    def test_windows_private_directory_has_protected_owner_only_acl(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private"
            installer.restrict_private_folder(path)
            script = r'''
$acl = [System.IO.Directory]::GetAccessControl($env:CFX_SETUP_PRIVATE_DIR)
$owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($owner, 'S-1-5-18', 'S-1-5-32-544')
if (-not $acl.AreAccessRulesProtected) { exit 2 }
foreach ($rule in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
    if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $allowed) { exit 3 }
}
'''
            shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                                    env={**os.environ, "CFX_SETUP_PRIVATE_DIR": str(path)}, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
