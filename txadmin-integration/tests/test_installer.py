import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from cfx_devkit import connection

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
