import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import shutil
import subprocess
from unittest.mock import patch

from cfx_devkit import livecontrol


class ConsoleBufferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.environment = patch.dict(os.environ, {
            "CFX_DEVKIT_DATA_DIR": self.temporary.name,
            "CFX_LIVE_ENABLE": "1", "CFX_LIVE_MODE": "full",
            "CFX_LIVE_TOKEN": "live-secret-" * 4, "CFX_BRIDGE_TOKEN": "bridge-secret-" * 4,
            "CFX_LIVE_SERVER_LOG": "", "CFX_LIVE_CLIENT_LOG": "", "CFX_LIVE_POLICY_FILE": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        with livecontrol._connect() as conn:
            conn.execute("INSERT INTO session VALUES(1,?,?,?)", (int(time.time()), int(time.time()) + 60, "test-fixture"))

    def test_missing_file_uses_authorized_native_buffer_and_redacts_tokens(self):
        value = "other\nERROR " + os.environ["CFX_LIVE_TOKEN"] + "\nerror " + os.environ["CFX_BRIDGE_TOKEN"]
        outcome = {"request": {"status": "done", "result": {"ok": True, "value": value, "error": value}}}
        with patch.object(livecontrol, "submit", return_value={"id": "a" * 32}) as submit, \
             patch.object(livecontrol, "status", return_value=outcome):
            result = livecontrol.tail_log(contains="error", lines=1)
        self.assertEqual(result["source"], "native-console-buffer")
        self.assertEqual(result["lines"], "error [REDACTED_TOKEN]")
        self.assertEqual(result["matched_lines"], 2)
        code = json.loads(submit.call_args.args[1])["code"]
        self.assertIn("GetConsoleBuffer()", code)
        self.assertNotIn("RegisterConsoleListener", code)

    def test_pending_read_is_explicit_and_bounded(self):
        with patch.object(livecontrol, "submit", return_value={"id": "a" * 32}), \
             patch.object(livecontrol, "status", return_value={"request": {"status": "queued"}}), \
             patch.object(livecontrol.time, "monotonic", side_effect=[0, 0, 11]), \
             patch.object(livecontrol.time, "sleep"):
            result = livecontrol.tail_log()
        self.assertTrue(result["pending"])
        self.assertEqual(result["lines"], "")

    def test_failed_native_read_does_not_return_error_payload_as_log(self):
        outcome = {"request": {"status": "done", "result": {"ok": False, "error": "private failure"}}}
        with patch.object(livecontrol, "submit", return_value={"id": "a" * 32}), \
             patch.object(livecontrol, "status", return_value=outcome):
            with self.assertRaisesRegex(ValueError, "console buffer unavailable"):
                livecontrol.tail_log()

    def test_revocation_before_result_prevents_console_return(self):
        def revoked(_):
            livecontrol.disarm()
            return {"request": {"status": "done", "result": {"ok": True, "value": "private output"}}}
        with patch.object(livecontrol, "submit", return_value={"id": "a" * 32}), \
             patch.object(livecontrol, "status", side_effect=revoked):
            with self.assertRaisesRegex(ValueError, "no longer authorized"):
                livecontrol.tail_log()

    def test_unarmed_connection_cannot_queue_console_read(self):
        livecontrol.disarm()
        with patch.object(livecontrol, "submit") as submit:
            with self.assertRaises(ValueError):
                livecontrol.tail_log()
        submit.assert_not_called()

    def test_configured_file_is_preferred_and_client_still_needs_a_source(self):
        path = Path(self.temporary.name) / "console.log"
        path.write_text("configured output\n")
        with patch.dict(os.environ, {"CFX_LIVE_SERVER_LOG": str(path)}), patch.object(livecontrol, "submit") as submit:
            self.assertEqual(livecontrol.tail_log()["lines"], "configured output")
            submit.assert_not_called()
        with self.assertRaisesRegex(ValueError, "CFX_LIVE_CLIENT_LOG"):
            livecontrol.tail_log("client")

    def test_tagged_console_results_are_redacted_everywhere_and_withheld_after_revoke(self):
        token = os.environ["CFX_LIVE_TOKEN"]
        diagnostic = os.environ["CFX_BRIDGE_TOKEN"]
        request = livecontrol.submit("server_lua", json.dumps({"code": "return 'fixture'"}), _console_read=True)
        livecontrol.poll()
        report = {"ok": True, "value": token, "error": diagnostic, "note": {"nested": [token]}}
        livecontrol.accept_result({"id": request["id"], "result": report})
        with livecontrol._connect() as conn:
            stored = conn.execute("SELECT result FROM requests WHERE id=?", (request["id"],)).fetchone()["result"]
            self.assertNotIn(token, stored)
            self.assertNotIn(diagnostic, stored)
            # An older broker may have stored raw data before the upgrade.
            conn.execute("UPDATE requests SET result=? WHERE id=?", (json.dumps(report), request["id"]))
        for result in (livecontrol.status(request["id"]), livecontrol.status()):
            self.assertNotIn(token, json.dumps(result))
            self.assertNotIn(diagnostic, json.dumps(result))
        livecontrol.disarm()
        direct = livecontrol.status(request["id"])["request"]
        self.assertIsNone(direct["result"])
        self.assertTrue(direct["result_withheld"])
        self.assertIsNone(livecontrol.status()["recent"][0]["result"])

    def test_file_read_boundary_does_not_expose_partial_token_line(self):
        token = os.environ["CFX_LIVE_TOKEN"]
        path = Path(self.temporary.name) / "console.log"
        path.write_text("prefix" + token + "\n" + ("x" * (32000 - len(token))) + "\n")
        with patch.dict(os.environ, {"CFX_LIVE_SERVER_LOG": str(path)}):
            result = livecontrol.tail_log(contains=token[8:])
        self.assertEqual(result["lines"], "")
        self.assertTrue(result["truncated_bytes"])

    def test_lua_redacts_before_cutting_and_preserves_utf8(self):
        lua = shutil.which("lua")
        if not lua:
            self.skipTest("Lua runtime unavailable")
        outcome = {"request": {"status": "done", "result": {"ok": True, "value": "fixture"}}}
        with patch.object(livecontrol, "submit", return_value={"id": "a" * 32}) as submit, \
             patch.object(livecontrol, "status", return_value=outcome):
            livecontrol.tail_log()
        code = json.loads(submit.call_args.args[1])["code"]
        script = '''local secret = "S[]%-TOKEN" .. string.rep("x", 40)
local buffer = "prefix" .. secret .. string.rep("z", 2500 - #secret + 1)
function GetConsoleBuffer() return buffer end
function GetConvar(name, fallback)
    if name == 'devkit_live_token' then return secret end
    return fallback
end
local function read()
''' + code + '''
end
local got = read()
assert(not got:find(secret:sub(2), 1, true))
assert(got:find('[REDACTED_TOKEN]', 1, true))
buffer = string.rep(utf8.char(233), 2000) .. 'x'
got = read()
assert(utf8.len(got) ~= nil)
assert(#got <= 2500)
print('PASS')
'''
        path = Path(self.temporary.name) / "console-read.lua"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run([lua, str(path)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
